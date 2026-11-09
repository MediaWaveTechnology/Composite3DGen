"""Run Blender explode / hierarchy / QA jobs on MWT1 or local dry paths.

Happy path: stage mesh + hierarchy + hub script to MWT1, invoke headless
Blender when the ``blender_explode`` / ``qa_renders`` stage capabilities pass.
Without Blender / without MWT1: dry-run writes schema-valid ``parts.json`` and
planned artifact paths — never invents a verified Blender binary path.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from composite3dgen.blender.paths import (
    UNVERIFIED,
    BlenderPathResolution,
    package_script_path,
    resolve_blender_path,
)
from composite3dgen.blender.schema import (
    PartsHierarchy,
    PartsHierarchyError,
    build_l1_l2_example,
    load_parts_hierarchy,
    parse_parts_hierarchy,
    write_parts_hierarchy,
)
from composite3dgen.nodes.executor import (
    ExecutorName,
    ExecutorSelection,
    MWT1Executor,
    select_executor,
)
from composite3dgen.nodes import mwt1 as mwt1_mod
from composite3dgen.providers.transport import RemoteFSTransport

JobMode = Literal["mwt1", "local-blender", "dry-run"]


@dataclass
class BlenderExplodeResult:
    """Outcome of a Blender explode / QA job."""

    job_dir: Path
    out_dir: Path
    mode: JobMode
    executor: ExecutorSelection
    blender: BlenderPathResolution
    parts_path: Path | None
    glb_path: Path | None
    verification: list[str] = field(default_factory=list)
    hierarchy: PartsHierarchy | None = None
    notes: list[str] = field(default_factory=list)
    remote_job: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.parts_path is not None

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "executor": self.executor.name,
            "executor_reason": self.executor.reason,
            "blender": self.blender.as_dict(),
            "out_dir": str(self.out_dir),
            "parts_path": str(self.parts_path) if self.parts_path else None,
            "glb_path": str(self.glb_path) if self.glb_path else None,
            "verification": list(self.verification),
            "remote_job": self.remote_job,
            "notes": list(self.notes),
            "error": self.error,
            "tier": self.hierarchy.tier if self.hierarchy else None,
            "subject_id": self.hierarchy.subject_id if self.hierarchy else None,
        }


def _resolve_hierarchy(
    *,
    subject_id: str,
    hierarchy_path: Path | None,
    hierarchy: PartsHierarchy | Mapping[str, Any] | None,
) -> PartsHierarchy:
    if hierarchy is not None:
        if isinstance(hierarchy, PartsHierarchy):
            return hierarchy
        return parse_parts_hierarchy(hierarchy)
    if hierarchy_path is not None:
        return load_parts_hierarchy(hierarchy_path)
    # Dry/default: synthetic L1/L2 so schema + export path can be exercised.
    return build_l1_l2_example(subject_id)


def _blender_cmd(
    blender_bin: str,
    script: Path,
    *,
    input_mesh: str,
    hierarchy: str,
    out_dir: str,
    subject_id: str,
    explode_factor: float | None,
    skip_stills: bool,
    prefix: str,
) -> str:
    args = [
        blender_bin,
        "--background",
        "--python",
        str(script),
        "--",
        "--input",
        input_mesh,
        "--hierarchy",
        hierarchy,
        "--out-dir",
        out_dir,
        "--subject-id",
        subject_id,
        "--prefix",
        prefix,
    ]
    if explode_factor is not None:
        args.extend(["--explode-factor", str(explode_factor)])
    if skip_stills:
        args.append("--skip-stills")
    return " ".join(shlex.quote(a) for a in args)


def _write_dry_artifacts(
    out_dir: Path,
    hierarchy: PartsHierarchy,
    *,
    prefix: str,
) -> tuple[Path, list[str], PartsHierarchy]:
    """Write schema-valid parts.json + planned verification names (no Blender)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    verification_dir = out_dir / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    stills = [
        f"verification/{prefix}-exploded-l1-front.png",
        f"verification/{prefix}-exploded-l1-side.png",
        f"verification/{prefix}-exploded-l2-front.png",
        f"verification/{prefix}-silhouette-front.png",
    ]
    # Marker files so dry-run is inspectable without pretending renders ran.
    for rel in stills:
        marker = out_dir / rel
        marker.write_text(
            f"# dry-run placeholder — render on MWT1 with Blender\n# planned: {rel}\n",
            encoding="utf-8",
        )

    artifacts = {
        "glb": "exploded.glb",
        "parts_json": "parts.json",
        "verification": stills,
    }
    updated = PartsHierarchy(
        schema_version=hierarchy.schema_version,
        subject_id=hierarchy.subject_id,
        tier=hierarchy.tier,
        parts=hierarchy.parts,
        source=hierarchy.source,
        units=hierarchy.units,
        explode=dict(hierarchy.explode) or {"factor": 1.0, "mode": "offset"},
        meshes=hierarchy.meshes,
        artifacts=artifacts,
        notes=(
            (hierarchy.notes or "")
            + (" | " if hierarchy.notes else "")
            + "Dry-run: GLB/stills not rendered; parts.json schema-valid."
        ).strip(" |"),
        raw=hierarchy.raw,
    )
    parts_path = write_parts_hierarchy(out_dir / "parts.json", updated)
    # Planned GLB path only — do not fabricate binary mesh bytes.
    glb_plan = out_dir / "exploded.glb.dry-run"
    glb_plan.write_text(
        "# dry-run: exploded.glb would be written by Blender on MWT1\n",
        encoding="utf-8",
    )
    return parts_path, stills, updated


def run_blender_explode(
    job_dir: Path,
    *,
    subject_id: str | None = None,
    input_mesh: Path | None = None,
    hierarchy_path: Path | None = None,
    hierarchy: PartsHierarchy | Mapping[str, Any] | None = None,
    prefer_mwt1: bool = True,
    force_executor: ExecutorName | None = None,
    mwt1_probe: Any | None = None,
    transport: RemoteFSTransport | None = None,
    blender_path: str | Path | None = None,
    health_facts: Mapping[str, Any] | None = None,
    explode_factor: float | None = None,
    skip_stills: bool = False,
    prefix: str = "local",
    allow_local_blender: bool = False,
) -> BlenderExplodeResult:
    """Run explode/hierarchy/QA: MWT1 Blender when capable, else dry-run.

    Remesh/UV/bake are intentionally not invoked here (local Blender-only ops
    when an operator runs them on MWT1 separately — never cloud).
    """
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    out_dir = job_dir / "out" / "blender"
    out_dir.mkdir(parents=True, exist_ok=True)

    selection = select_executor(
        prefer_mwt1=prefer_mwt1,
        force=force_executor,
        mwt1_probe=mwt1_probe,
    )

    sid = subject_id
    if sid is None:
        # Best-effort from hierarchy or job dirname.
        sid = job_dir.name

    try:
        hier = _resolve_hierarchy(
            subject_id=sid,
            hierarchy_path=hierarchy_path,
            hierarchy=hierarchy,
        )
        if subject_id:
            # Rebuild with explicit subject if hierarchy came from file with other id.
            if hier.subject_id != subject_id:
                data = hier.as_dict()
                data["subject_id"] = subject_id
                hier = parse_parts_hierarchy(data)
                sid = subject_id
        else:
            sid = hier.subject_id
    except PartsHierarchyError as exc:
        blender = resolve_blender_path(explicit=blender_path, health_facts=health_facts)
        return BlenderExplodeResult(
            job_dir=job_dir,
            out_dir=out_dir,
            mode="dry-run",
            executor=selection,
            blender=blender,
            parts_path=None,
            glb_path=None,
            error=str(exc),
            notes=["Hierarchy validation failed before Blender invoke."],
        )

    # Persist input hierarchy for the job (and remote staging).
    input_hier_path = out_dir / "hierarchy.input.json"
    write_parts_hierarchy(input_hier_path, hier)

    blender = resolve_blender_path(
        explicit=blender_path,
        health_facts=health_facts,
        prefer_local_which=allow_local_blender and selection.name == "local",
    )

    notes: list[str] = [
        f"executor={selection.name}: {selection.reason}",
        f"blender_resolution={blender.source} display={blender.as_dict()['display']}",
    ]

    # --- Path A: MWT1 remote Blender ---
    if selection.name == "mwt1":
        fs = transport or mwt1_mod.get_default_transport()
        # Fail closed on stage capabilities unless caller supplied an explicit
        # Blender path (tests / operator override after LAN verify).
        explicit_override = blender_path is not None and blender.verified
        try:
            if isinstance(selection.executor, MWT1Executor) and not explicit_override:
                if transport is not None:
                    from composite3dgen.nodes.health import run_health_check

                    report = run_health_check(transport=transport)
                    report.require_stage("blender_explode")
                    if not skip_stills:
                        report.require_stage("qa_renders")
                    if not blender.verified:
                        blender = resolve_blender_path(
                            explicit=blender_path,
                            health_facts=report.facts,
                        )
                else:
                    selection.executor.ensure_stage("blender_explode")
            elif explicit_override:
                notes.append(
                    "Explicit blender_path override — skipping live ensure_stage "
                    "(operator/test verified path)."
                )
        except Exception as exc:  # noqa: BLE001 — CapabilityError or probe miss
            notes.append(f"MWT1 blender stage blocked: {exc}")
            parts_path, stills, updated = _write_dry_artifacts(
                out_dir, hier, prefix=prefix
            )
            return BlenderExplodeResult(
                job_dir=job_dir,
                out_dir=out_dir,
                mode="dry-run",
                executor=selection,
                blender=blender,
                parts_path=parts_path,
                glb_path=None,
                verification=stills,
                hierarchy=updated,
                notes=[
                    *notes,
                    "Fell back to dry-run — MWT1 Blender stage capabilities missing "
                    f"or unreachable. Path stays {UNVERIFIED} until LAN probe.",
                ],
                error=None,
            )

        if fs is None:
            notes.append(
                "No RemoteFSTransport for MWT1 Blender; dry-run artifacts only. "
                "Inject transport or run doctor --live on LAN / mwt1 worker."
            )
            parts_path, stills, updated = _write_dry_artifacts(
                out_dir, hier, prefix=prefix
            )
            return BlenderExplodeResult(
                job_dir=job_dir,
                out_dir=out_dir,
                mode="dry-run",
                executor=selection,
                blender=blender,
                parts_path=parts_path,
                glb_path=None,
                verification=stills,
                hierarchy=updated,
                notes=notes,
            )

        if not blender.verified or not blender.path:
            notes.append(
                f"Blender binary unresolved ({UNVERIFIED}); refusing remote invoke."
            )
            parts_path, stills, updated = _write_dry_artifacts(
                out_dir, hier, prefix=prefix
            )
            return BlenderExplodeResult(
                job_dir=job_dir,
                out_dir=out_dir,
                mode="dry-run",
                executor=selection,
                blender=blender,
                parts_path=parts_path,
                glb_path=None,
                verification=stills,
                hierarchy=updated,
                notes=notes,
            )

        remote_job = mwt1_mod.remote_job_path(sid, "blender-explode")
        remote_in = f"{remote_job}/input"
        remote_out = f"{remote_job}/out"
        fs.makedirs(remote_in)
        fs.makedirs(remote_out)

        script_local = package_script_path("explode_hub.py")
        remote_script = f"{remote_job}/explode_hub.py"
        remote_hier = f"{remote_in}/hierarchy.json"
        fs.upload(script_local, remote_script)
        fs.upload(input_hier_path, remote_hier)

        remote_mesh = f"{remote_in}/mesh.glb"
        mesh_arg = "-"
        if input_mesh is not None and Path(input_mesh).is_file():
            fs.upload(Path(input_mesh), remote_mesh)
            mesh_arg = remote_mesh
        else:
            notes.append(
                "No input mesh — remote Blender will keep scene empty unless "
                "operator stages a mesh; dry hierarchy still exported."
            )

        cmd = _blender_cmd(
            blender.path,
            Path(remote_script),
            input_mesh=mesh_arg,
            hierarchy=remote_hier,
            out_dir=remote_out,
            subject_id=sid,
            explode_factor=explode_factor,
            skip_stills=skip_stills,
            prefix=prefix,
        )
        code, stdout, stderr = fs.run(cmd, timeout=1800.0)
        notes.append(f"remote_exit={code}")
        if stdout.strip():
            notes.append(f"stdout_tail={stdout.strip()[-500:]}")
        if code != 0:
            parts_path, stills, updated = _write_dry_artifacts(
                out_dir, hier, prefix=prefix
            )
            return BlenderExplodeResult(
                job_dir=job_dir,
                out_dir=out_dir,
                mode="mwt1",
                executor=selection,
                blender=blender,
                parts_path=parts_path,
                glb_path=None,
                verification=stills,
                hierarchy=updated,
                notes=notes,
                remote_job=remote_job,
                error=f"Remote Blender failed (exit {code}): {stderr[-800:]}",
            )

        # Pull artifacts
        local_parts = out_dir / "parts.json"
        local_glb = out_dir / "exploded.glb"
        try:
            fs.download(f"{remote_out}/parts.json", local_parts)
        except Exception as exc:  # noqa: BLE001
            return BlenderExplodeResult(
                job_dir=job_dir,
                out_dir=out_dir,
                mode="mwt1",
                executor=selection,
                blender=blender,
                parts_path=None,
                glb_path=None,
                notes=notes,
                remote_job=remote_job,
                error=f"Failed to download parts.json: {exc}",
            )
        glb_ok = False
        try:
            if fs.exists(f"{remote_out}/exploded.glb"):
                fs.download(f"{remote_out}/exploded.glb", local_glb)
                glb_ok = True
        except Exception as exc:  # noqa: BLE001
            notes.append(f"GLB download skipped/failed: {exc}")

        try:
            updated = load_parts_hierarchy(local_parts)
        except PartsHierarchyError as exc:
            return BlenderExplodeResult(
                job_dir=job_dir,
                out_dir=out_dir,
                mode="mwt1",
                executor=selection,
                blender=blender,
                parts_path=local_parts,
                glb_path=local_glb if glb_ok else None,
                notes=notes,
                remote_job=remote_job,
                error=f"Downloaded parts.json failed schema validation: {exc}",
            )

        stills = list((updated.artifacts or {}).get("verification") or [])
        # Best-effort pull stills
        for rel in stills:
            try:
                fs.download(f"{remote_out}/{rel}", out_dir / rel)
            except Exception:  # noqa: BLE001
                notes.append(f"still not pulled: {rel}")

        return BlenderExplodeResult(
            job_dir=job_dir,
            out_dir=out_dir,
            mode="mwt1",
            executor=selection,
            blender=blender,
            parts_path=local_parts,
            glb_path=local_glb if glb_ok else None,
            verification=stills,
            hierarchy=updated,
            notes=notes,
            remote_job=remote_job,
        )

    # --- Path B: local Blender (optional controller smoke) ---
    if allow_local_blender and blender.verified and blender.path:
        script = package_script_path("explode_hub.py")
        mesh_arg = str(input_mesh) if input_mesh and Path(input_mesh).is_file() else "-"
        cmd = _blender_cmd(
            blender.path,
            script,
            input_mesh=mesh_arg,
            hierarchy=str(input_hier_path),
            out_dir=str(out_dir),
            subject_id=sid,
            explode_factor=explode_factor,
            skip_stills=skip_stills,
            prefix=prefix,
        )
        import subprocess

        proc = subprocess.run(  # noqa: S602 — local optional smoke
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        notes.append(f"local_blender_exit={proc.returncode}")
        if proc.returncode == 0 and (out_dir / "parts.json").is_file():
            updated = load_parts_hierarchy(out_dir / "parts.json")
            stills = list((updated.artifacts or {}).get("verification") or [])
            glb = out_dir / "exploded.glb"
            return BlenderExplodeResult(
                job_dir=job_dir,
                out_dir=out_dir,
                mode="local-blender",
                executor=selection,
                blender=blender,
                parts_path=out_dir / "parts.json",
                glb_path=glb if glb.is_file() else None,
                verification=stills,
                hierarchy=updated,
                notes=notes,
            )
        notes.append(
            f"Local Blender failed or missing; falling back to dry-run. "
            f"stderr={proc.stderr[-400:] if proc.stderr else ''}"
        )

    # --- Path C: dry-run (default without Blender) ---
    notes.append(
        "Dry-run path: no Blender invoke. Schema-valid parts.json + planned "
        f"verification markers. Blender display={UNVERIFIED} until LAN probe."
    )
    parts_path, stills, updated = _write_dry_artifacts(out_dir, hier, prefix=prefix)
    return BlenderExplodeResult(
        job_dir=job_dir,
        out_dir=out_dir,
        mode="dry-run",
        executor=selection,
        blender=blender,
        parts_path=parts_path,
        glb_path=None,
        verification=stills,
        hierarchy=updated,
        notes=notes,
    )


__all__ = [
    "BlenderExplodeResult",
    "JobMode",
    "run_blender_explode",
]
