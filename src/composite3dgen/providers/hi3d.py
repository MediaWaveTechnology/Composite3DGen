"""Hi3D submit/poll adapter (multi-view quality/master tiers).

Live HTTP behind ``--spend``. Secrets: ``HI3D_API_KEY``. Tests use MockHTTPTransport.
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
from composite3dgen.providers.transport import HTTPTransport, UrllibHTTPTransport

DEFAULT_BASE_URL = "https://api.hi3d.example/v1"  # placeholder host; override via options/env


@dataclass
class Hi3DAdapter:
    """Hi3D v3.0 multi-view client patterns (submit → poll → artifact URLs)."""

    name: ProviderName = "hi3d"
    is_paid: bool = True
    transport: HTTPTransport = field(default_factory=UrllibHTTPTransport)
    base_url: str = DEFAULT_BASE_URL
    environ: Mapping[str, str] | None = None
    _jobs: dict[str, ProviderJobResult] = field(default_factory=dict, repr=False)

    def _headers(self) -> dict[str, str]:
        key = require_api_key("hi3d", environ=self.environ)
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ProviderJobRequest) -> dict[str, Any]:
        quality = request.options.get("quality", "2048quality")
        images = request.inputs.get("images") or {}
        views = []
        for angle in ("front", "left", "back", "right"):
            path = images.get(angle) or request.inputs.get(angle)
            if path:
                views.append({"view": angle, "path": str(path)})
        return {
            "model": "hi3d-v3",
            "quality": quality,
            "views": views,
            "split": bool(request.options.get("split", False)),
            "subject_id": request.subject_id,
        }

    async def submit(self, request: ProviderJobRequest) -> ProviderJobResult:
        job_id = new_job_id(self.name)
        out_dir = request.ensure_out_dir()
        record_path = out_dir / f"{job_id}.json"
        payload = self._payload(request)

        if request.mode == "dry-run":
            cost_hint = 0.90 if payload["quality"] == "2048quality" else 2.90
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.DRY_RUN,
                mode="dry-run",
                consumed=0.0,
                artifacts={"planned_payload": payload, "estimated_cost_usd": cost_hint},
                notes=[
                    "Dry-run Hi3D virtual job — no HTTP.",
                    f"Quality tier: {payload['quality']} (ballpark ${cost_hint}).",
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
                error=f"Hi3D live HTTP requires mode=live (got {request.mode}). Use --spend.",
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

        base = request.options.get("base_url", self.base_url)
        resp = self.transport.request(
            "POST",
            f"{base}/jobs",
            headers=headers,
            json_body=payload,
        )
        if resp.status >= 400:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode="live",
                error=f"Hi3D submit HTTP {resp.status}: {resp.text[:500]}",
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        body = resp.json() or {}
        remote_id = None
        if isinstance(body, dict):
            remote_id = body.get("id") or body.get("job_id") or (body.get("data") or {}).get("id")
        if not remote_id:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode="live",
                error=f"Hi3D submit missing job id: {body!r}",
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
            notes=["Hi3D job submitted; poll for completion."],
            meta={"submit": body, "base_url": base},
        )
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
                error=f"Unknown Hi3D job_id: {job_id}",
            )
        if current.status in (JobStatus.DRY_RUN, JobStatus.FAILED, JobStatus.BLOCKED, JobStatus.SUCCEEDED):
            return current
        if not current.remote_task_id:
            return current

        headers = self._headers()
        base = (current.meta or {}).get("base_url", self.base_url)
        resp = self.transport.request(
            "GET",
            f"{base}/jobs/{current.remote_task_id}",
            headers=headers,
        )
        body = resp.json() or {}
        status_raw = ""
        artifacts = dict(current.artifacts)
        consumed = current.consumed
        if isinstance(body, dict):
            status_raw = str(body.get("status") or body.get("state") or "").lower()
            consumed = body.get("consumed", consumed)
            outputs = body.get("outputs") or body.get("result") or {}
            if isinstance(outputs, dict):
                for key in ("glb", "obj", "texture", "split_glb"):
                    if outputs.get(key):
                        artifacts[key] = outputs[key]

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
            consumed=float(consumed) if consumed is not None else None,
            remote_task_id=current.remote_task_id,
            error=None if status != JobStatus.FAILED else f"Hi3D job failed: {body!r}",
            notes=list(current.notes) + [f"poll_status={status_raw or 'unknown'}"],
            meta={**current.meta, "poll": body},
        )
        self._jobs[job_id] = result
        if job_dir is not None:
            _write_record(Path(job_dir) / "out" / self.name / f"{job_id}.json", result)
        return result

    async def run(self, request: ProviderJobRequest) -> ProviderJobResult:
        submitted = await self.submit(request)
        if submitted.status in (JobStatus.DRY_RUN, JobStatus.FAILED, JobStatus.BLOCKED, JobStatus.SUCCEEDED):
            return submitted
        return await self.poll(submitted.job_id, job_dir=request.job_dir)


def _write_record(path: Path, result: ProviderJobResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_record(), indent=2) + "\n", encoding="utf-8")


def _result_from_record(data: dict[str, Any]) -> ProviderJobResult:
    return ProviderJobResult(
        provider=data.get("provider", "hi3d"),
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
