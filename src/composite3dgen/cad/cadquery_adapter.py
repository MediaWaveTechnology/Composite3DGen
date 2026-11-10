"""CadQuery adapter for RC leaf fitment (prefer MWT1).

Missing CadQuery binary/module → structured dry-run with next steps
(never invent STEP/STL bytes). Fusion GUI stays on the licensed
workstation — see ``docs/playbook/FUSION_HANDOFF.md``. 3ds Max is
later-phase, not U6.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

from composite3dgen.cad.register import (
    DimensionRegister,
    DimensionRegisterError,
    load_dimension_register,
    parse_dimension_register,
)
from composite3dgen.nodes.executor import (
    ExecutorName,
    ExecutorSelection,
    select_executor,
)
from composite3dgen.nodes import mwt1 as mwt1_mod
from composite3dgen.providers.transport import RemoteFSTransport

CadMode = Literal["mwt1", "local", "dry-run"]


@dataclass(frozen=True)
class CadQueryProbe:
    """Local or remote CadQuery availability."""

    available: bool
    import_ok: bool
    cq_cli: str | None
    detail: str
    where: Literal["local", "mwt1", "none"] = "none"

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "import_ok": self.import_ok,
            "cq_cli": self.cq_cli,
            "detail": self.detail,
            "where": self.where,
        }


@dataclass
class CadQueryResult:
    """Outcome of a CadQuery stage (live or missing-binary dry-run)."""

    job_dir: Path
    out_dir: Path
    mode: CadMode
    executor: ExecutorSelection
    register: DimensionRegister | None
    probe: CadQueryProbe
    status: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    next_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    remote_job: str | None = None

    @property
    def ok(self) -> bool:
        """Dry-run with structured next steps counts as success for CI."""
        if self.error:
            return False
        return self.status in ("succeeded", "dry_run_missing_binary", "dry_run")

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "status": self.status,
            "executor": self.executor.name,
            "executor_reason": self.executor.reason,
            "out_dir": str(self.out_dir),
            "probe": self.probe.as_dict(),
            "register": self.register.summary() if self.register else None,
            "artifacts": {
                k: str(v) if isinstance(v, Path) else v
                for k, v in self.artifacts.items()
            },
            "next_steps": list(self.next_steps),
            "notes": list(self.notes),
            "error": self.error,
            "remote_job": self.remote_job,
            "leaf_fitment_allowed": (
                self.register.leaf_fitment_allowed() if self.register else False
            ),
        }


def probe_cadquery_local() -> CadQueryProbe:
    """Probe CadQuery on the controller process."""
    cq_cli = shutil.which("cq-cli") or shutil.which("cq")
    import_ok = False
    detail_parts: list[str] = []
    try:
        import importlib.util

        import_ok = importlib.util.find_spec("cadquery") is not None
        detail_parts.append("import cadquery: ok" if import_ok else "import cadquery: missing")
    except Exception as exc:  # noqa: BLE001
        detail_parts.append(f"import probe error: {exc}")
    if cq_cli:
        detail_parts.append(f"cli={cq_cli}")
    else:
        detail_parts.append("cq-cli: missing")
    available = import_ok or bool(cq_cli)
    return CadQueryProbe(
        available=available,
        import_ok=import_ok,
        cq_cli=cq_cli,
        detail="; ".join(detail_parts),
        where="local" if available else "none",
    )


def probe_cadquery_remote(transport: RemoteFSTransport, *, timeout: float = 30.0) -> CadQueryProbe:
    """Probe CadQuery on MWT1 via injectable transport."""
    cmd = (
        "CQ=;"
        "if command -v cq-cli >/dev/null 2>&1; then CQ=$(command -v cq-cli); fi;"
        "if [ -z \"$CQ\" ] && command -v cq >/dev/null 2>&1; then CQ=$(command -v cq); fi;"
        "python3 -c \"import importlib.util as u; "
        "print('import_ok' if u.find_spec('cadquery') else 'import_missing')\" 2>/dev/null; "
        "if [ -n \"$CQ\" ]; then echo \"cli=$CQ\"; else echo cli_missing; fi"
    )
    try:
        code, out, err = transport.run(cmd, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return CadQueryProbe(
            available=False,
            import_ok=False,
            cq_cli=None,
            detail=f"remote probe error: {exc}",
            where="none",
        )
    import_ok = "import_ok" in out
    cli = None
    for line in out.splitlines():
        if line.startswith("cli=") and not line.endswith("cli_missing"):
            cli = line.split("=", 1)[1].strip() or None
    available = code == 0 and (import_ok or bool(cli))
    return CadQueryProbe(
        available=available,
        import_ok=import_ok,
        cq_cli=cli,
        detail=out.strip() or err.strip() or f"exit {code}",
        where="mwt1" if available else "none",
    )


def missing_binary_next_steps(
    *,
    prefer_mwt1: bool,
    register_path: Path | None,
    subject_id: str | None,
) -> list[str]:
    """Structured remediation when CadQuery is not installed."""
    job_hint = subject_id or "<subject-id>"
    steps = [
        (
            "Install CadQuery on MWT1 (preferred) into a venv under AlanTBrain: "
            "`python3 -m venv /Volumes/AlanTBrain/composite3dgen/tools/cadquery-venv && "
            "source /Volumes/AlanTBrain/composite3dgen/tools/cadquery-venv/bin/activate && "
            "pip install cadquery`"
        ),
        (
            "Confirm import: "
            "`/Volumes/AlanTBrain/composite3dgen/tools/cadquery-venv/bin/python "
            "-c 'import cadquery as cq; print(cq.__version__)'`"
        ),
        (
            "Optional CLI: `pip install cadquery-ocp` / ensure `cq-cli` on PATH "
            "when scripting headless exports."
        ),
        (
            f"Stage dimension register under "
            f"`/Volumes/AlanTBrain/composite3dgen/jobs/{job_hint}/cad/` "
            "and re-run `composite3dgen cad <job_dir>` from a LAN controller "
            "or mwt1 worker (`doctor --live` first)."
        ),
        (
            "Export STEP/STL from CadQuery for Fusion import on the licensed "
            "workstation — see docs/playbook/FUSION_HANDOFF.md. "
            "Do not use 3ds Max for v1 (later phase)."
        ),
        (
            "Controller degraded fallback: install CadQuery locally and pass "
            "`--executor local` only when MWT1 is unreachable."
        ),
    ]
    if register_path is not None:
        steps.insert(
            0,
            f"Dimension register ready at {register_path} — CadQuery binary/module missing.",
        )
    if not prefer_mwt1:
        steps.append(
            "prefer_mwt1 disabled — local CadQuery still required; "
            "missing module keeps this stage in dry-run."
        )
    return steps


def _resolve_register(
    *,
    register_path: Path | None,
    register: DimensionRegister | Mapping[str, Any] | None,
    job_dir: Path,
) -> tuple[DimensionRegister | None, Path | None]:
    if register is not None:
        if isinstance(register, DimensionRegister):
            return register, register_path
        return parse_dimension_register(register), register_path
    candidates: list[Path] = []
    if register_path is not None:
        candidates.append(Path(register_path))
    candidates.extend(
        [
            Path(job_dir) / "cad" / "dimension-register.json",
            Path(job_dir) / "manifests" / "dimension-register.json",
            Path(job_dir) / "dimension-register.json",
        ]
    )
    for path in candidates:
        if path.is_file():
            return load_dimension_register(path), path
    return None, None


def _write_dry_record(
    out_dir: Path,
    *,
    summary: dict[str, Any],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "cadquery_job.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return path


def run_cadquery(
    job_dir: Path | str,
    *,
    register_path: Path | None = None,
    register: DimensionRegister | Mapping[str, Any] | None = None,
    script_path: Path | None = None,
    prefer_mwt1: bool = True,
    force_executor: ExecutorName | None = None,
    transport: RemoteFSTransport | None = None,
    allow_local: bool = True,
) -> CadQueryResult:
    """Run CadQuery against a dimension register (prefer MWT1).

    When CadQuery is missing, returns ``status=dry_run_missing_binary`` with
    structured ``next_steps`` — suitable for CI assertions (U6).
    """
    job = Path(job_dir)
    out_dir = job / "out" / "cadquery"
    out_dir.mkdir(parents=True, exist_ok=True)

    selection = select_executor(
        prefer_mwt1=prefer_mwt1,
        force=force_executor,
    )

    reg: DimensionRegister | None
    reg_path: Path | None
    try:
        reg, reg_path = _resolve_register(
            register_path=register_path, register=register, job_dir=job
        )
    except DimensionRegisterError as exc:
        probe = CadQueryProbe(
            available=False,
            import_ok=False,
            cq_cli=None,
            detail="register invalid — CadQuery not attempted",
            where="none",
        )
        result = CadQueryResult(
            job_dir=job,
            out_dir=out_dir,
            mode="dry-run",
            executor=selection,
            register=None,
            probe=probe,
            status="failed",
            error=str(exc),
            next_steps=[
                "Fix dimension register schema errors, then re-run.",
                "See schema/dimension.register.schema.json and "
                "fixtures/rc-dex410/dimension-register.json.",
            ],
        )
        _write_dry_record(out_dir, summary=result.summary())
        return result

    notes: list[str] = [
        "CadQuery stage is $0 local compute; Fusion GUI stays on licensed workstation.",
        "3ds Max is later-phase — not invoked in U6.",
    ]
    if reg is not None:
        notes.append(
            f"Register: confirmed={reg.confirmed_count} inferred={reg.inferred_count} "
            f"leaf_fitment_allowed={reg.leaf_fitment_allowed()}"
        )
    else:
        notes.append(
            "No dimension-register.json found under job; dry-run will still "
            "emit install next steps."
        )

    # Probe remote first when MWT1 selected.
    remote = transport if transport is not None else mwt1_mod.get_default_transport()
    probe: CadQueryProbe
    mode: CadMode

    if selection.name == "mwt1" and remote is not None:
        probe = probe_cadquery_remote(remote)
        mode = "mwt1" if probe.available else "dry-run"
    elif selection.name == "mwt1" and remote is None:
        # Prefer MWT1 but no transport — fall through to local probe then dry-run.
        local_probe = probe_cadquery_local() if allow_local else CadQueryProbe(
            available=False,
            import_ok=False,
            cq_cli=None,
            detail="local probe skipped",
            where="none",
        )
        if local_probe.available and allow_local:
            probe = local_probe
            mode = "local"
            notes.append(
                "MWT1 selected but no SSH transport — using local CadQuery "
                "(degraded). Inject RemoteFSTransport or run doctor --live."
            )
        else:
            probe = CadQueryProbe(
                available=False,
                import_ok=False,
                cq_cli=None,
                detail=(
                    "MWT1 preferred but no transport; local CadQuery also missing"
                    if not local_probe.available
                    else local_probe.detail
                ),
                where="none",
            )
            mode = "dry-run"
            notes.append(
                "MWT1 CadQuery transport unavailable — dry-run with next steps. "
                "Run `composite3dgen doctor --live` on LAN / mwt1 worker."
            )
    else:
        probe = probe_cadquery_local() if allow_local else CadQueryProbe(
            available=False,
            import_ok=False,
            cq_cli=None,
            detail="local probe skipped",
            where="none",
        )
        mode = "local" if probe.available else "dry-run"

    subject_id = reg.subject_id if reg else job.name
    if not probe.available:
        next_steps = missing_binary_next_steps(
            prefer_mwt1=prefer_mwt1,
            register_path=reg_path,
            subject_id=subject_id,
        )
        result = CadQueryResult(
            job_dir=job,
            out_dir=out_dir,
            mode="dry-run",
            executor=selection,
            register=reg,
            probe=probe,
            status="dry_run_missing_binary",
            artifacts={
                "planned_step": str(out_dir / "fitment.step"),
                "planned_stl": str(out_dir / "fitment.stl"),
                "register_path": str(reg_path) if reg_path else None,
                "script_path": str(script_path) if script_path else None,
            },
            next_steps=next_steps,
            notes=notes,
        )
        record = _write_dry_record(out_dir, summary=result.summary())
        result.artifacts["job_record"] = str(record)
        return result

    # Live path: only attempt a minimal export when CadQuery imports locally.
    # Remote live execution stages a placeholder command for MWT1 (no paid cloud).
    if mode == "mwt1" and remote is not None:
        remote_job = mwt1_mod.remote_job_path(subject_id, "cadquery")
        remote.makedirs(remote_job)
        if reg_path is not None and reg_path.is_file():
            remote.upload(reg_path, f"{remote_job}/dimension-register.json")
        if script_path is not None and script_path.is_file():
            remote.upload(script_path, f"{remote_job}/script.py")
            code, out, err = remote.run(
                f"cd {remote_job} && python3 script.py",
                timeout=600.0,
            )
            if code != 0:
                result = CadQueryResult(
                    job_dir=job,
                    out_dir=out_dir,
                    mode="mwt1",
                    executor=selection,
                    register=reg,
                    probe=probe,
                    status="failed",
                    error=err.strip() or out.strip() or f"exit {code}",
                    next_steps=missing_binary_next_steps(
                        prefer_mwt1=True,
                        register_path=reg_path,
                        subject_id=subject_id,
                    ),
                    notes=notes,
                    remote_job=remote_job,
                )
                _write_dry_record(out_dir, summary=result.summary())
                return result
        else:
            notes.append(
                "CadQuery available on MWT1 but no script_path — recorded staging "
                "only. Pass --script for parametric export."
            )
        result = CadQueryResult(
            job_dir=job,
            out_dir=out_dir,
            mode="mwt1",
            executor=selection,
            register=reg,
            probe=probe,
            status="succeeded" if script_path else "dry_run",
            artifacts={
                "remote_job": remote_job,
                "register_path": str(reg_path) if reg_path else None,
            },
            next_steps=(
                []
                if script_path
                else [
                    "Provide a CadQuery script via --script to export STEP/STL on MWT1.",
                    "Then import STEP into Fusion per docs/playbook/FUSION_HANDOFF.md.",
                ]
            ),
            notes=notes,
            remote_job=remote_job,
        )
        _write_dry_record(out_dir, summary=result.summary())
        return result

    # Local CadQuery available — emit a tiny box from envelope when possible.
    artifacts: dict[str, Any] = {}
    try:
        import cadquery as cq  # type: ignore[import-not-found]

        length = 10.0
        width = 10.0
        height = 5.0
        if reg and reg.envelope:
            for key, attr in (("length", "length"), ("width", "width"), ("height", "height")):
                block = reg.envelope.get(key)
                if isinstance(block, dict) and isinstance(block.get("value"), (int, float)):
                    if attr == "length":
                        length = float(block["value"])
                    elif attr == "width":
                        width = float(block["value"])
                    else:
                        height = float(block["value"])
        # Keep demo solids small if values look like full vehicle mm.
        if length > 200:
            length, width, height = length / 20.0, width / 20.0, max(height / 20.0, 1.0)
        solid = cq.Workplane("XY").box(length, width, height)
        stl_path = out_dir / "fitment_envelope.stl"
        step_path = out_dir / "fitment_envelope.step"
        cq.exporters.export(solid, str(stl_path))
        try:
            cq.exporters.export(solid, str(step_path))
            artifacts["step"] = str(step_path)
        except Exception as exc:  # noqa: BLE001 — STEP optional
            notes.append(f"STEP export skipped: {exc}")
        artifacts["stl"] = str(stl_path)
        artifacts["cadquery_version"] = getattr(cq, "__version__", "unknown")
        status = "succeeded"
        next_steps = [
            "Import STEP/STL into Fusion on the licensed workstation "
            "(docs/playbook/FUSION_HANDOFF.md).",
            "Refine mates using confirmed dimension-register entries only.",
        ]
    except Exception as exc:  # noqa: BLE001
        return CadQueryResult(
            job_dir=job,
            out_dir=out_dir,
            mode="local",
            executor=selection,
            register=reg,
            probe=probe,
            status="failed",
            error=f"CadQuery local export failed: {exc}",
            next_steps=missing_binary_next_steps(
                prefer_mwt1=prefer_mwt1,
                register_path=reg_path,
                subject_id=subject_id,
            ),
            notes=notes,
        )

    result = CadQueryResult(
        job_dir=job,
        out_dir=out_dir,
        mode="local",
        executor=selection,
        register=reg,
        probe=probe,
        status=status,
        artifacts=artifacts,
        next_steps=next_steps,
        notes=notes,
    )
    record = _write_dry_record(out_dir, summary=result.summary())
    result.artifacts["job_record"] = str(record)
    return result


def default_register_fixture() -> Path:
    """Path to the curated RC DEX410 dimension-register fixture."""
    here = Path(__file__).resolve()
    return here.parents[3] / "fixtures" / "rc-dex410" / "dimension-register.json"


# Silence unused import lint for sys in some environments.
_ = sys
