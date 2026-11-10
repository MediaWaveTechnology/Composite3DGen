"""Tripo cloud API client patterns (H3.1 multiview + generate_parts).

Live HTTP is gated by router/CLI ``--spend``. Secrets from env only
(``TRIPO_API_KEY``). No live paid calls in tests — inject MockHTTPTransport.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from composite3dgen.providers.base import (
    JobStatus,
    ProviderJobRequest,
    ProviderJobResult,
    ProviderName,
    new_job_id,
)
from composite3dgen.providers.secrets import MissingSecretError, require_api_key
from composite3dgen.providers.transport import HTTPResponse, HTTPTransport, UrllibHTTPTransport

DEFAULT_BASE_URL = "https://api.tripo3d.ai/v2/openapi"


@dataclass
class TripoAdapter:
    """Tripo OpenAPI-shaped client (submit task → poll → download URL)."""

    name: ProviderName = "tripo"
    is_paid: bool = True
    transport: HTTPTransport = field(default_factory=UrllibHTTPTransport)
    base_url: str = DEFAULT_BASE_URL
    environ: Mapping[str, str] | None = None
    _jobs: dict[str, ProviderJobResult] = field(default_factory=dict, repr=False)
    _remote_to_local: dict[str, str] = field(default_factory=dict, repr=False)

    def _headers(self) -> dict[str, str]:
        key = require_api_key("tripo", environ=self.environ)
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ProviderJobRequest) -> dict[str, Any]:
        opts = request.options
        model_version = opts.get("model_version", "v2.5-20250123")  # H3.1-class token
        images = request.inputs.get("images") or {}
        files = []
        for angle in ("front", "left", "back", "right"):
            path = images.get(angle) or request.inputs.get(angle)
            if path:
                files.append({"angle": angle, "path": str(path)})
        return {
            "type": opts.get("type", "multiview_to_model"),
            "model_version": model_version,
            "generate_parts": bool(opts.get("generate_parts", True)),
            "files": files,
            "subject_id": request.subject_id,
        }

    async def submit(self, request: ProviderJobRequest) -> ProviderJobResult:
        job_id = new_job_id(self.name)
        out_dir = request.ensure_out_dir()
        record_path = out_dir / f"{job_id}.json"

        if request.mode == "dry-run":
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.DRY_RUN,
                mode="dry-run",
                consumed=0.0,
                artifacts={"planned_payload": self._payload(request)},
                notes=[
                    "Dry-run Tripo virtual job — no HTTP.",
                    "Default path: H3.1-class multiview + generate_parts (~$0.40–$0.70).",
                ],
                meta={"base_url": self.base_url},
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        if request.mode != "live":
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.BLOCKED,
                mode=request.mode,
                error=f"Tripo live HTTP requires mode=live (got {request.mode}). Use --spend.",
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        try:
            headers = self._headers()
        except MissingSecretError as exc:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.BLOCKED,
                mode="live",
                error=str(exc),
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        payload = self._payload(request)
        # Pattern: POST /task — response carries task_id. File upload omitted in
        # unit-testable client; live path expects pre-staged file tokens in options.
        if "file_tokens" in request.options:
            payload["file_tokens"] = request.options["file_tokens"]

        resp = self.transport.request(
            "POST",
            f"{self.base_url}/task",
            headers=headers,
            json_body=payload,
        )
        if resp.status >= 400:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode="live",
                error=f"Tripo submit HTTP {resp.status}: {resp.text[:500]}",
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        body = resp.json() or {}
        data = body.get("data") if isinstance(body, dict) else None
        remote_id = None
        if isinstance(data, dict):
            remote_id = data.get("task_id") or data.get("id")
        remote_id = remote_id or (body.get("task_id") if isinstance(body, dict) else None)
        if not remote_id:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode="live",
                error=f"Tripo submit missing task_id: {body!r}",
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        result = ProviderJobResult(
            provider=self.name,
            job_id=job_id,
            status=JobStatus.QUEUED,
            mode="live",
            remote_task_id=str(remote_id),
            notes=["Tripo task submitted; poll for completion."],
            meta={"submit": body},
        )
        self._remote_to_local[str(remote_id)] = job_id
        _write_record(record_path, result)
        self._jobs[job_id] = result
        return result

    async def poll(self, job_id: str, *, job_dir: Path | None = None) -> ProviderJobResult:
        current = self._jobs.get(job_id)
        if current is None and job_dir is not None:
            path = Path(job_dir) / "out" / self.name / f"{job_id}.json"
            if path.is_file():
                current = _result_from_record(json.loads(path.read_text(encoding="utf-8")))
                self._jobs[job_id] = current
        if current is None:
            return ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode="live",
                error=f"Unknown Tripo job_id: {job_id}",
            )
        if current.status in (JobStatus.DRY_RUN, JobStatus.FAILED, JobStatus.BLOCKED, JobStatus.SUCCEEDED):
            return current
        if not current.remote_task_id:
            return current

        headers = self._headers()
        resp = self.transport.request(
            "GET",
            f"{self.base_url}/task/{current.remote_task_id}",
            headers=headers,
        )
        body = resp.json() or {}
        data = body.get("data") if isinstance(body, dict) else body
        status_raw = ""
        if isinstance(data, dict):
            status_raw = str(data.get("status") or data.get("state") or "").lower()
        consumed = None
        artifacts: dict[str, Any] = dict(current.artifacts)
        if isinstance(data, dict):
            consumed = data.get("consumed") or data.get("credit") 
            output = data.get("output") or data.get("result") or {}
            if isinstance(output, dict):
                if output.get("model"):
                    artifacts["model_url"] = output["model"]
                if output.get("pbr_model"):
                    artifacts["pbr_model_url"] = output["pbr_model"]

        if status_raw in ("success", "succeeded", "completed", "done"):
            status = JobStatus.SUCCEEDED
        elif status_raw in ("failed", "error", "cancelled"):
            status = JobStatus.FAILED
        elif status_raw in ("running", "processing"):
            status = JobStatus.RUNNING
        else:
            status = JobStatus.QUEUED

        result = ProviderJobResult(
            provider=self.name,
            job_id=job_id,
            status=status,
            mode=current.mode,
            artifacts=artifacts,
            consumed=float(consumed) if consumed is not None else current.consumed,
            remote_task_id=current.remote_task_id,
            error=None if status != JobStatus.FAILED else f"Tripo task failed: {body!r}",
            notes=list(current.notes) + [f"poll_status={status_raw or 'unknown'}"],
            meta={"poll": body},
        )
        self._jobs[job_id] = result
        if job_dir is not None:
            _write_record(Path(job_dir) / "out" / self.name / f"{job_id}.json", result)
        return result

    async def run(self, request: ProviderJobRequest) -> ProviderJobResult:
        submitted = await self.submit(request)
        if submitted.status in (JobStatus.DRY_RUN, JobStatus.FAILED, JobStatus.BLOCKED, JobStatus.SUCCEEDED):
            return submitted
        # Single poll step — callers may loop; keeps tests deterministic.
        return await self.poll(submitted.job_id, job_dir=request.job_dir)


def _write_record(path: Path, result: ProviderJobResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_record(), indent=2) + "\n", encoding="utf-8")


def _result_from_record(data: dict[str, Any]) -> ProviderJobResult:
    return ProviderJobResult(
        provider=data.get("provider", "tripo"),
        job_id=data.get("job_id", "unknown"),
        status=JobStatus(data.get("status", "failed")),
        mode=data.get("mode", "dry-run"),
        artifacts=dict(data.get("artifacts") or {}),
        consumed=data.get("consumed"),
        error=data.get("error"),
        notes=list(data.get("notes") or []),
        remote_task_id=data.get("remote_task_id"),
        meta=dict(data.get("meta") or {}),
    )


# Silence unused import warning in type checkers that don't see Protocol use
_ = HTTPResponse
