"""Photogrammetry adapter — COLMAP / Meshroom on MWT1 (U6).

Happy path: stage frames to MWT1, run COLMAP (preferred) or Meshroom batch
when capability probes pass. Missing binaries → structured dry-run with
next steps (never invent dense meshes). Probe 2026-11-09: neither tool
installed on MWT1 — see ``deploy/mwt1/photogrammetry.md``.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

from composite3dgen.nodes.capabilities import PHOTOGRAMMETRY_ANY_OF, remediation_for
from composite3dgen.nodes.executor import (
    ExecutorName,
    ExecutorSelection,
    select_executor,
)
from composite3dgen.nodes import mwt1 as mwt1_mod
from composite3dgen.nodes.health import run_health_check
from composite3dgen.providers.base import (
    JobStatus,
    ProviderJobRequest,
    ProviderJobResult,
    ProviderName,
    new_job_id,
)
from composite3dgen.providers.transport import RemoteFSTransport

PhotoTool = Literal["colmap", "meshroom"]
PhotoMode = Literal["mwt1", "local", "dry-run"]


@dataclass(frozen=True)
class PhotoToolProbe:
    """Availability of COLMAP and/or Meshroom."""

    colmap_path: str | None
    meshroom_path: str | None
    preferred: PhotoTool | None
    where: Literal["mwt1", "local", "none"]
    detail: str

    @property
    def available(self) -> bool:
        return self.preferred is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "colmap_path": self.colmap_path,
            "meshroom_path": self.meshroom_path,
            "preferred": self.preferred,
            "available": self.available,
            "where": self.where,
            "detail": self.detail,
        }


@dataclass
class PhotogrammetryResult:
    """Outcome of a photogrammetry job (live or missing-binary dry-run)."""

    job_dir: Path
    out_dir: Path
    mode: PhotoMode
    executor: ExecutorSelection
    probe: PhotoToolProbe
    provider_result: ProviderJobResult
    next_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    remote_job: str | None = None
    stage_ready: bool = False

    @property
    def ok(self) -> bool:
        return self.provider_result.status in (
            JobStatus.SUCCEEDED,
            JobStatus.DRY_RUN,
            JobStatus.PENDING,
        ) and self.provider_result.error is None

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "executor": self.executor.name,
            "executor_reason": self.executor.reason,
            "stage_ready": self.stage_ready,
            "probe": self.probe.as_dict(),
            "job": self.provider_result.to_record(),
            "out_dir": str(self.out_dir),
            "next_steps": list(self.next_steps),
            "notes": list(self.notes),
            "remote_job": self.remote_job,
        }


def missing_binary_next_steps(*, subject_id: str | None = None) -> list[str]:
    """Structured remediation when COLMAP and Meshroom are both missing."""
    job = subject_id or "<subject-id>"
    return [
        "COLMAP and Meshroom were not found (MWT1 probe 2026-11-09: both missing).",
        "Install COLMAP on MWT1 (Homebrew): `brew install colmap` "
        "— then `command -v colmap && colmap -h | head -n 1`.",
        "Or install Meshroom: download from AliceVision releases into "
        "`/Volumes/AlanTBrain/composite3dgen/tools/Meshroom` and ensure "
        "`meshroom_batch` is on PATH (see deploy/mwt1/photogrammetry.md).",
        f"Stage orbit frames under "
        f"`/Volumes/AlanTBrain/composite3dgen/jobs/{job}/frames/` "
        "(prefer AlanTBrain; home disk is tight).",
        "Re-run `composite3dgen doctor --live` on LAN / mwt1 worker; "
        "photogrammetry stage becomes ready when ssh + job_root + "
        "(colmap OR meshroom) pass.",
        "Then: `composite3dgen photogrammetry <job_dir>` (or "
        "`run --stage photogrammetry`).",
        "Prefer this $0 local metric lane before Tripo multiview when "
        "orbit coverage is real.",
    ]


def probe_local_tools() -> PhotoToolProbe:
    """Probe COLMAP / Meshroom on the controller."""
    colmap = shutil.which("colmap")
    meshroom = (
        shutil.which("meshroom_batch")
        or shutil.which("Meshroom")
        or shutil.which("meshroom")
    )
    preferred: PhotoTool | None = None
    if colmap:
        preferred = "colmap"
    elif meshroom:
        preferred = "meshroom"
    detail = (
        f"colmap={colmap or 'missing'}; meshroom={meshroom or 'missing'}"
    )
    return PhotoToolProbe(
        colmap_path=colmap,
        meshroom_path=meshroom,
        preferred=preferred,
        where="local" if preferred else "none",
        detail=detail,
    )


def probe_from_health_caps(
    *,
    colmap_ok: bool,
    meshroom_ok: bool,
    colmap_path: str | None,
    meshroom_path: str | None,
    where: Literal["mwt1", "local", "none"] = "mwt1",
) -> PhotoToolProbe:
    """Build a probe from health-check capability flags."""
    preferred: PhotoTool | None = None
    if colmap_ok:
        preferred = "colmap"
    elif meshroom_ok:
        preferred = "meshroom"
    return PhotoToolProbe(
        colmap_path=colmap_path if colmap_ok else None,
        meshroom_path=meshroom_path if meshroom_ok else None,
        preferred=preferred,
        where=where if preferred else "none",
        detail=(
            f"colmap={'ok' if colmap_ok else 'missing'}; "
            f"meshroom={'ok' if meshroom_ok else 'missing'}"
        ),
    )


def _frames_dir(job_dir: Path, inputs: dict[str, Any] | None) -> Path | None:
    if inputs:
        for key in ("frames_dir", "images_dir", "image_dir"):
            raw = inputs.get(key)
            if raw:
                p = Path(str(raw))
                if p.is_dir():
                    return p
        images = inputs.get("images")
        if isinstance(images, dict) and images:
            first = Path(str(next(iter(images.values()))))
            if first.is_file():
                return first.parent
    for candidate in (
        job_dir / "frames",
        job_dir / "media" / "frames",
        job_dir / "build_packs" / "triposr",
    ):
        if candidate.is_dir() and any(candidate.glob("*.*")):
            return candidate
    return None


@dataclass
class PhotogrammetryAdapter:
    """Provider-shaped adapter for COLMAP / Meshroom (local / MWT1)."""

    name: ProviderName = "colmap"
    is_paid: bool = False
    transport: RemoteFSTransport | None = None
    tool_preference: PhotoTool | None = None
    _jobs: dict[str, ProviderJobResult] = field(default_factory=dict, repr=False)

    async def submit(self, request: ProviderJobRequest) -> ProviderJobResult:
        return await self.run(request)

    async def poll(self, job_id: str, *, job_dir: Path | None = None) -> ProviderJobResult:
        del job_dir
        if job_id in self._jobs:
            return self._jobs[job_id]
        return ProviderJobResult(
            provider=self.name,
            job_id=job_id,
            status=JobStatus.FAILED,
            mode="dry-run",
            error=f"Unknown photogrammetry job_id: {job_id}",
        )

    async def run(self, request: ProviderJobRequest) -> ProviderJobResult:
        # Prefer the run_photogrammetry helper for executor selection; this
        # path supports runner integration with dry-run / local modes.
        result = run_photogrammetry(
            request.job_dir,
            subject_id=request.subject_id,
            inputs=request.inputs,
            mode_hint=request.mode,
            transport=self.transport,
            tool_preference=self.tool_preference,
            prefer_mwt1=True,
            force_executor=None,
        )
        self.name = result.provider_result.provider
        self._jobs[result.provider_result.job_id] = result.provider_result
        return result.provider_result


def run_photogrammetry(
    job_dir: Path | str,
    *,
    subject_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    mode_hint: str | None = None,
    prefer_mwt1: bool = True,
    force_executor: ExecutorName | None = None,
    transport: RemoteFSTransport | None = None,
    tool_preference: PhotoTool | None = None,
    allow_local: bool = True,
) -> PhotogrammetryResult:
    """Execute photogrammetry on MWT1 when capable; else structured dry-run."""
    job = Path(job_dir)
    selection = select_executor(prefer_mwt1=prefer_mwt1, force=force_executor)
    notes: list[str] = [
        "Photogrammetry is the free local metric multi-view lane ($0).",
        "Prefer before Tripo multiview when orbit coverage is real.",
    ]

    remote = transport if transport is not None else mwt1_mod.get_default_transport()
    stage_ready = False
    probe: PhotoToolProbe

    if selection.name == "mwt1" and remote is not None:
        health = run_health_check(transport=remote)
        try:
            health.require_stage("photogrammetry")
            stage_ready = True
        except Exception as exc:  # noqa: BLE001 — CapabilityError or similar
            notes.append(f"photogrammetry stage blocked: {exc}")
            stage_ready = False
        colmap_cap = health.capabilities.get("colmap")
        meshroom_cap = health.capabilities.get("meshroom")
        colmap_ok = bool(colmap_cap and colmap_cap.ok)
        meshroom_ok = bool(meshroom_cap and meshroom_cap.ok)
        colmap_path = None
        meshroom_path = None
        if colmap_cap:
            colmap_path = colmap_cap.meta.get("colmap_path")
        if meshroom_cap:
            meshroom_path = meshroom_cap.meta.get("meshroom_path")
        probe = probe_from_health_caps(
            colmap_ok=colmap_ok,
            meshroom_ok=meshroom_ok,
            colmap_path=str(colmap_path) if colmap_path else None,
            meshroom_path=str(meshroom_path) if meshroom_path else None,
            where="mwt1",
        )
        if tool_preference == "meshroom" and meshroom_ok:
            probe = PhotoToolProbe(
                colmap_path=probe.colmap_path,
                meshroom_path=probe.meshroom_path,
                preferred="meshroom",
                where="mwt1",
                detail=probe.detail + "; preference=meshroom",
            )
        mode: PhotoMode = "mwt1" if probe.available and stage_ready else "dry-run"
    elif selection.name == "mwt1" and remote is None:
        local = probe_local_tools() if allow_local else PhotoToolProbe(
            colmap_path=None,
            meshroom_path=None,
            preferred=None,
            where="none",
            detail="no transport; local probe skipped",
        )
        if local.available and allow_local:
            probe = local
            mode = "local"
            notes.append(
                "MWT1 selected but no SSH transport — using local "
                "COLMAP/Meshroom (degraded)."
            )
        else:
            probe = PhotoToolProbe(
                colmap_path=None,
                meshroom_path=None,
                preferred=None,
                where="none",
                detail=(
                    "MWT1 preferred but no transport; local tools also missing. "
                    "Probe 2026-11-09: colmap/meshroom not found on MWT1."
                ),
            )
            mode = "dry-run"
            notes.append(
                "Inject RemoteFSTransport or run `doctor --live` on LAN / "
                "mwt1 worker for photogrammetry execution."
            )
        for name in PHOTOGRAMMETRY_ANY_OF:
            notes.append(f"remediation[{name}]: {remediation_for(name)}")
    else:
        probe = probe_local_tools() if allow_local else PhotoToolProbe(
            colmap_path=None,
            meshroom_path=None,
            preferred=None,
            where="none",
            detail="local probe skipped",
        )
        if tool_preference and (
            (tool_preference == "colmap" and probe.colmap_path)
            or (tool_preference == "meshroom" and probe.meshroom_path)
        ):
            probe = PhotoToolProbe(
                colmap_path=probe.colmap_path,
                meshroom_path=probe.meshroom_path,
                preferred=tool_preference,
                where=probe.where,
                detail=probe.detail + f"; preference={tool_preference}",
            )
        mode = "local" if probe.available else "dry-run"
        stage_ready = probe.available

    if mode_hint == "dry-run":
        mode = "dry-run"

    provider: ProviderName = "colmap"
    if probe.preferred == "meshroom":
        provider = "meshroom"
    job_id = new_job_id(provider)
    out_dir = job / "out" / provider
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = subject_id or job.name
    frames = _frames_dir(job, inputs)

    if mode == "dry-run" or not probe.available:
        next_steps = missing_binary_next_steps(subject_id=sid)
        if frames is None:
            next_steps.insert(
                0,
                "No frames/ directory found — add orbit stills before COLMAP.",
            )
        provider_result = ProviderJobResult(
            provider=provider,
            job_id=job_id,
            status=JobStatus.DRY_RUN,
            mode="dry-run",
            consumed=0.0,
            artifacts={
                "planned_sparse": str(out_dir / "sparse"),
                "planned_dense": str(out_dir / "dense"),
                "planned_mesh": str(out_dir / "mesh.ply"),
                "frames_dir": str(frames) if frames else None,
                "tool": probe.preferred,
            },
            notes=[
                "Dry-run photogrammetry — binaries missing or stage not ready.",
                *notes,
            ],
            meta={
                "stage": "photogrammetry",
                "probe": probe.as_dict(),
                "next_steps": next_steps,
                "executor": selection.name,
            },
        )
        _write_record(out_dir, provider_result)
        return PhotogrammetryResult(
            job_dir=job,
            out_dir=out_dir,
            mode="dry-run",
            executor=selection,
            probe=probe,
            provider_result=provider_result,
            next_steps=next_steps,
            notes=notes,
            stage_ready=stage_ready,
        )

    # Live / local execution
    if mode == "mwt1" and remote is not None:
        remote_job = mwt1_mod.remote_job_path(sid, job_id)
        remote.makedirs(f"{remote_job}/images")
        remote.makedirs(f"{remote_job}/sparse")
        remote.makedirs(f"{remote_job}/dense")
        uploaded = 0
        if frames is not None:
            for img in sorted(frames.iterdir()):
                if img.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
                    remote.upload(img, f"{remote_job}/images/{img.name}")
                    uploaded += 1
        tool_bin = probe.colmap_path if provider == "colmap" else probe.meshroom_path
        if provider == "colmap":
            # Automatic reconstruction pipeline (feature → match → mapper).
            cmd = (
                f"{tool_bin} automatic_reconstructor "
                f"--workspace_path {remote_job} "
                f"--image_path {remote_job}/images"
            )
        else:
            cmd = (
                f"{tool_bin} --input {remote_job}/images "
                f"--output {remote_job}/dense"
            )
        code, out, err = remote.run(cmd, timeout=3600.0)
        if code != 0:
            provider_result = ProviderJobResult(
                provider=provider,
                job_id=job_id,
                status=JobStatus.FAILED,
                mode="local",
                consumed=0.0,
                error=err.strip() or out.strip() or f"exit {code}",
                notes=notes,
                meta={"stage": "photogrammetry", "remote_job": remote_job},
            )
            _write_record(out_dir, provider_result)
            return PhotogrammetryResult(
                job_dir=job,
                out_dir=out_dir,
                mode="mwt1",
                executor=selection,
                probe=probe,
                provider_result=provider_result,
                next_steps=missing_binary_next_steps(subject_id=sid),
                notes=notes,
                remote_job=remote_job,
                stage_ready=stage_ready,
            )
        provider_result = ProviderJobResult(
            provider=provider,
            job_id=job_id,
            status=JobStatus.SUCCEEDED,
            mode="local",
            consumed=0.0,
            artifacts={
                "remote_workspace": remote_job,
                "images_uploaded": uploaded,
                "tool": provider,
                "tool_bin": tool_bin,
            },
            notes=[
                f"Photogrammetry executed on MWT1 via {provider}.",
                *notes,
            ],
            meta={"stage": "photogrammetry", "remote_job": remote_job},
        )
        _write_record(out_dir, provider_result)
        return PhotogrammetryResult(
            job_dir=job,
            out_dir=out_dir,
            mode="mwt1",
            executor=selection,
            probe=probe,
            provider_result=provider_result,
            notes=notes,
            remote_job=remote_job,
            stage_ready=stage_ready,
        )

    # Local binary path
    tool_bin = probe.colmap_path if provider == "colmap" else probe.meshroom_path
    if frames is None:
        provider_result = ProviderJobResult(
            provider=provider,
            job_id=job_id,
            status=JobStatus.FAILED,
            mode="local",
            consumed=0.0,
            error="Photogrammetry requires a frames/ directory with images.",
            notes=notes,
        )
        _write_record(out_dir, provider_result)
        return PhotogrammetryResult(
            job_dir=job,
            out_dir=out_dir,
            mode="local",
            executor=selection,
            probe=probe,
            provider_result=provider_result,
            next_steps=[
                "Add orbit frames under job_dir/frames/ then re-run.",
                *missing_binary_next_steps(subject_id=sid),
            ],
            notes=notes,
            stage_ready=True,
        )

    workspace = out_dir / "workspace"
    images_link = workspace / "images"
    workspace.mkdir(parents=True, exist_ok=True)
    if not images_link.exists():
        try:
            images_link.symlink_to(frames.resolve(), target_is_directory=True)
        except OSError:
            images_link.mkdir(parents=True, exist_ok=True)
            for img in frames.iterdir():
                if img.is_file():
                    target = images_link / img.name
                    if not target.exists():
                        target.write_bytes(img.read_bytes())

    if provider == "colmap":
        cmd = (
            f"{tool_bin} automatic_reconstructor "
            f"--workspace_path {workspace} "
            f"--image_path {images_link}"
        )
    else:
        cmd = f"{tool_bin} --input {images_link} --output {workspace / 'dense'}"

    import subprocess

    proc = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        provider_result = ProviderJobResult(
            provider=provider,
            job_id=job_id,
            status=JobStatus.FAILED,
            mode="local",
            consumed=0.0,
            error=(proc.stderr or proc.stdout or f"exit {proc.returncode}")[:2000],
            notes=notes,
            meta={"command": cmd},
        )
        _write_record(out_dir, provider_result)
        return PhotogrammetryResult(
            job_dir=job,
            out_dir=out_dir,
            mode="local",
            executor=selection,
            probe=probe,
            provider_result=provider_result,
            next_steps=missing_binary_next_steps(subject_id=sid),
            notes=notes,
            stage_ready=True,
        )

    provider_result = ProviderJobResult(
        provider=provider,
        job_id=job_id,
        status=JobStatus.SUCCEEDED,
        mode="local",
        consumed=0.0,
        artifacts={
            "workspace": str(workspace),
            "tool": provider,
            "tool_bin": tool_bin,
        },
        notes=[f"Photogrammetry executed locally via {provider}.", *notes],
        meta={"stage": "photogrammetry"},
    )
    _write_record(out_dir, provider_result)
    return PhotogrammetryResult(
        job_dir=job,
        out_dir=out_dir,
        mode="local",
        executor=selection,
        probe=probe,
        provider_result=provider_result,
        notes=notes,
        stage_ready=True,
    )


def _write_record(out_dir: Path, result: ProviderJobResult) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.job_id}.json"
    path.write_text(json.dumps(result.to_record(), indent=2) + "\n", encoding="utf-8")
    # Also write a stable summary name for dry-run assertions.
    summary = out_dir / "photogrammetry_job.json"
    summary.write_text(json.dumps(result.to_record(), indent=2) + "\n", encoding="utf-8")
    return path
