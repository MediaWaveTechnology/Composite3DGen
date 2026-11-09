"""Rodin Gen-2.5 + Custom BANG adapters (Hyper3D-shaped client patterns).

- Gen-2.5 Extreme-High: hard-surface hero when drafts fail QA.
- Custom BANG: cross-provider part split on any GLB (~0.5 cr), strength 1–12.

Live HTTP behind ``--spend``. Secrets: ``RODIN_API_KEY`` / ``HYPER3D_API_KEY``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from composite3dgen.providers.base import (
    JobStatus,
    ProviderJobRequest,
    ProviderJobResult,
    ProviderName,
    new_job_id,
)
from composite3dgen.providers.secrets import MissingSecretError, require_api_key
from composite3dgen.providers.transport import HTTPTransport, UrllibHTTPTransport

DEFAULT_BASE_URL = "https://api.hyper3d.com/api/v2"
RodinOperation = Literal["gen25", "bang"]


@dataclass
class RodinAdapter:
    """Rodin cloud client covering Gen-2.5 generation and Custom BANG split."""

    name: ProviderName = "rodin"
    is_paid: bool = True
    transport: HTTPTransport = field(default_factory=UrllibHTTPTransport)
    base_url: str = DEFAULT_BASE_URL
    environ: Mapping[str, str] | None = None
    _jobs: dict[str, ProviderJobResult] = field(default_factory=dict, repr=False)

    def _headers(self) -> dict[str, str]:
        key = require_api_key("rodin", environ=self.environ)
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _operation(self, request: ProviderJobRequest) -> RodinOperation:
        op = str(request.options.get("operation") or request.inputs.get("operation") or "gen25")
        if op in ("bang", "custom_bang", "split"):
            return "bang"
        return "gen25"

    def _payload(self, request: ProviderJobRequest) -> dict[str, Any]:
        op = self._operation(request)
        if op == "bang":
            strength = int(request.options.get("strength", 6))
            strength = max(1, min(12, strength))
            glb = request.inputs.get("glb") or request.inputs.get("mesh")
            return {
                "operation": "custom_bang",
                "strength": strength,
                "mesh": str(glb) if glb else None,
                "subject_id": request.subject_id,
            }
        images = request.inputs.get("images") or {}
        image_list = []
        for angle in ("front", "left", "back", "right"):
            path = images.get(angle) or request.inputs.get(angle)
            if path:
                image_list.append(str(path))
        if request.inputs.get("image"):
            image_list.insert(0, str(request.inputs["image"]))
        return {
            "operation": "gen25",
            "tier": request.options.get("tier", "extreme-high"),
            "images": image_list,
            "subject_id": request.subject_id,
        }

    async def submit(self, request: ProviderJobRequest) -> ProviderJobResult:
        job_id = new_job_id(self.name)
        out_dir = request.ensure_out_dir()
        record_path = out_dir / f"{job_id}.json"
        payload = self._payload(request)
        op = payload["operation"]

        if request.mode == "dry-run":
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.DRY_RUN,
                mode="dry-run",
                consumed=0.0,
                artifacts={"planned_payload": payload},
                notes=[
                    "Dry-run Rodin virtual job — no HTTP.",
                    (
                        "Custom BANG split (~0.5 cr, strength 1–12)."
                        if op == "custom_bang"
                        else "Gen-2.5 Extreme-High hero reconstruct."
                    ),
                ],
                meta={"base_url": self.base_url, "operation": op},
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
                error=f"Rodin live HTTP requires mode=live (got {request.mode}). Use --spend.",
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

        endpoint = "/bang" if op == "custom_bang" else "/rodin"
        base = request.options.get("base_url", self.base_url)
        resp = self.transport.request(
            "POST",
            f"{base}{endpoint}",
            headers=headers,
            json_body=payload,
        )
        if resp.status >= 400:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode="live",
                error=f"Rodin submit HTTP {resp.status}: {resp.text[:500]}",
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        body = resp.json() or {}
        remote_id = None
        if isinstance(body, dict):
            remote_id = (
                body.get("uuid")
                or body.get("task_uuid")
                or body.get("id")
                or (body.get("data") or {}).get("uuid")
            )
        if not remote_id:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode="live",
                error=f"Rodin submit missing task uuid: {body!r}",
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
            notes=[f"Rodin {op} submitted; poll for completion."],
            meta={"submit": body, "base_url": base, "operation": op},
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
                error=f"Unknown Rodin job_id: {job_id}",
            )
        if current.status in (JobStatus.DRY_RUN, JobStatus.FAILED, JobStatus.BLOCKED, JobStatus.SUCCEEDED):
            return current
        if not current.remote_task_id:
            return current

        headers = self._headers()
        base = (current.meta or {}).get("base_url", self.base_url)
        resp = self.transport.request(
            "POST",
            f"{base}/status",
            headers=headers,
            json_body={"uuid": current.remote_task_id},
        )
        body = resp.json() or {}
        status_raw = ""
        artifacts = dict(current.artifacts)
        consumed = current.consumed
        if isinstance(body, dict):
            status_raw = str(
                body.get("status") or body.get("state") or (body.get("data") or {}).get("status") or ""
            ).lower()
            consumed = body.get("consumed", consumed)
            jobs_list = body.get("list") or body.get("jobs") or []
            if isinstance(jobs_list, list):
                for item in jobs_list:
                    if isinstance(item, dict) and item.get("url"):
                        key = str(item.get("name") or item.get("format") or "artifact")
                        artifacts[key] = item["url"]
            result_block = body.get("result") or {}
            if isinstance(result_block, dict):
                for key in ("glb", "obj", "parts", "bang_glb"):
                    if result_block.get(key):
                        artifacts[key] = result_block[key]

        if status_raw in ("success", "succeeded", "completed", "done", "generate_done"):
            status = JobStatus.SUCCEEDED
        elif status_raw in ("failed", "error", "cancelled"):
            status = JobStatus.FAILED
        elif status_raw in ("running", "processing", "generating", "waiting"):
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
            error=None if status != JobStatus.FAILED else f"Rodin task failed: {body!r}",
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
        provider=data.get("provider", "rodin"),
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
