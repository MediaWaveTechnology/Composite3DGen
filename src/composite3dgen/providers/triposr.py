"""TripoSR remote adapter — stage image → MWT1 → pinned run.py → pull GLB/OBJ.

TripoSR is **local single-image** draft reconstruct ($0). It is not Tripo cloud
multiview. Full CUDA/path capability probes are **U3b**; this adapter takes an
injectable :class:`RemoteFSTransport`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from composite3dgen.providers.base import (
    JobStatus,
    ProviderJobRequest,
    ProviderJobResult,
    ProviderName,
    new_job_id,
)
from composite3dgen.providers.transport import MockRemoteFSTransport, RemoteFSTransport

# Pin documented for deploy/mwt1 — U3b verifies the checkout exists on node.
TRIPOSR_PIN_COMMIT = "2c5d0e1"  # placeholder pin token; replace with real SHA in U3b
DEFAULT_REMOTE_ROOT = "~/composite3dgen"
DEFAULT_TRIPOSR_DIR = "~/composite3dgen/vendor/TripoSR"
DEFAULT_RUN_PY = f"{DEFAULT_TRIPOSR_DIR}/run.py"


@dataclass
class TripoSRAdapter:
    """Remote TripoSR job runner via injectable SSH/FS transport."""

    name: ProviderName = "triposr"
    is_paid: bool = False
    transport: RemoteFSTransport | None = None
    remote_root: str = DEFAULT_REMOTE_ROOT
    run_py: str = DEFAULT_RUN_PY
    pin_commit: str = TRIPOSR_PIN_COMMIT
    _jobs: dict[str, ProviderJobResult] = field(default_factory=dict, repr=False)

    def _transport(self) -> RemoteFSTransport:
        if self.transport is None:
            # Default is intentionally not live SSH — U3b wires SubprocessSSHTransport
            # after capability probes. Callers/tests must inject a transport for local/live.
            raise RuntimeError(
                "TripoSRAdapter requires an injected RemoteFSTransport. "
                "U3b wires SubprocessSSHTransport after MWT1 capability probes. "
                "Tests should use MockRemoteFSTransport."
            )
        return self.transport

    async def submit(self, request: ProviderJobRequest) -> ProviderJobResult:
        job_id = new_job_id(self.name)
        out_dir = request.ensure_out_dir()
        image = _resolve_image(request)
        record_path = out_dir / f"{job_id}.json"

        if request.mode == "dry-run":
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.DRY_RUN,
                mode="dry-run",
                consumed=0.0,
                artifacts={
                    "virtual_image": str(image) if image else None,
                    "planned_remote_run_py": self.run_py,
                    "pin_commit": self.pin_commit,
                },
                notes=[
                    "Dry-run TripoSR virtual job — no SSH/FS executed.",
                    "TripoSR is single-image draft; not multi-view fusion.",
                ],
                meta={"pin_commit": self.pin_commit},
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        if image is None or not Path(image).is_file():
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode=request.mode,
                consumed=0.0,
                error="TripoSR requires inputs.image (path to a JPEG/PNG).",
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        try:
            fs = self._transport()
        except RuntimeError as exc:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode=request.mode,
                consumed=0.0,
                error=str(exc),
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        remote_job = f"{self.remote_root}/jobs/{request.subject_id or 'job'}/{job_id}"
        remote_input = f"{remote_job}/input.png"
        remote_out = f"{remote_job}/output"
        fs.makedirs(remote_job)
        fs.makedirs(remote_out)
        fs.upload(Path(image), remote_input)

        # Pinned run.py invocation shape — U3b confirms flags/weights on MWT1.
        cmd = (
            f"cd {self.remote_root}/vendor/TripoSR && "
            f"python {self.run_py} {remote_input} --output-dir {remote_out}"
        )
        code, stdout, stderr = fs.run(cmd)
        if code != 0:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode=request.mode,
                consumed=0.0,
                error=f"TripoSR remote run failed (exit {code}): {stderr or stdout}",
                notes=[f"command: {cmd}"],
                meta={"stdout": stdout, "stderr": stderr, "pin_commit": self.pin_commit},
            )
            _write_record(record_path, result)
            self._jobs[job_id] = result
            return result

        local_glb = out_dir / f"{job_id}.glb"
        local_obj = out_dir / f"{job_id}.obj"
        artifacts: dict[str, Any] = {}
        pulled = False
        for remote_name, local_path, key in (
            (f"{remote_out}/mesh.glb", local_glb, "glb"),
            (f"{remote_out}/mesh.obj", local_obj, "obj"),
            (f"{remote_out}/0/mesh.glb", local_glb, "glb"),
            (f"{remote_out}/0/mesh.obj", local_obj, "obj"),
        ):
            if key in artifacts:
                continue
            if fs.exists(remote_name):
                fs.download(remote_name, local_path)
                artifacts[key] = str(local_path)
                pulled = True

        if not pulled:
            # Mock-friendly: if transport wrote known outputs, accept them.
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode=request.mode,
                consumed=0.0,
                error="TripoSR finished but no GLB/OBJ found under remote output.",
                notes=[f"remote_out={remote_out}"],
                meta={"pin_commit": self.pin_commit},
            )
        else:
            result = ProviderJobResult(
                provider=self.name,
                job_id=job_id,
                status=JobStatus.SUCCEEDED,
                mode=request.mode,
                consumed=0.0,
                artifacts=artifacts,
                notes=[
                    "TripoSR local draft pulled from MWT1.",
                    "Not multi-view — promote to Tripo/Hi3D/photogrammetry on QA miss.",
                ],
                meta={"pin_commit": self.pin_commit, "remote_job": remote_job},
            )
        _write_record(record_path, result)
        self._jobs[job_id] = result
        return result

    async def poll(self, job_id: str, *, job_dir: Path | None = None) -> ProviderJobResult:
        if job_id in self._jobs:
            return self._jobs[job_id]
        if job_dir is not None:
            path = Path(job_dir) / "out" / self.name / f"{job_id}.json"
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                return _result_from_record(data)
        return ProviderJobResult(
            provider=self.name,
            job_id=job_id,
            status=JobStatus.FAILED,
            mode="local",
            error=f"Unknown TripoSR job_id: {job_id}",
        )

    async def run(self, request: ProviderJobRequest) -> ProviderJobResult:
        submitted = await self.submit(request)
        if submitted.status in (JobStatus.DRY_RUN, JobStatus.FAILED, JobStatus.BLOCKED, JobStatus.SUCCEEDED):
            return submitted
        return await self.poll(submitted.job_id, job_dir=request.job_dir)


def _resolve_image(request: ProviderJobRequest) -> Path | None:
    raw = request.inputs.get("image") or request.inputs.get("front")
    if raw is None:
        # Fall back to build pack front.jpg
        pack = Path(request.job_dir) / "build_packs" / "triposr" / "front.jpg"
        if pack.is_file():
            return pack
        return None
    return Path(raw)


def _write_record(path: Path, result: ProviderJobResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_record(), indent=2) + "\n", encoding="utf-8")


def _result_from_record(data: dict[str, Any]) -> ProviderJobResult:
    return ProviderJobResult(
        provider=data.get("provider", "triposr"),
        job_id=data.get("job_id", "unknown"),
        status=JobStatus(data.get("status", "failed")),
        mode=data.get("mode", "local"),
        artifacts=dict(data.get("artifacts") or {}),
        consumed=data.get("consumed"),
        error=data.get("error"),
        notes=list(data.get("notes") or []),
        remote_task_id=data.get("remote_task_id"),
        meta=dict(data.get("meta") or {}),
    )


def make_mock_adapter(root: Path, **kwargs: Any) -> TripoSRAdapter:
    """Test helper: TripoSR adapter with MockRemoteFSTransport under ``root``."""
    return TripoSRAdapter(transport=MockRemoteFSTransport(root=root), **kwargs)
