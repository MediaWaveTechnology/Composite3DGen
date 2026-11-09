"""MWT1 health-check module with injectable transport.

Probes are capability checks (not just SSH alive). Missing **required**
capabilities fail closed with remediation text. Optional capabilities
(colmap / meshroom) are reported but do not fail the base node by themselves.

Live SSH uses :class:`~composite3dgen.providers.transport.SubprocessSSHTransport`.
Tests inject :class:`~composite3dgen.providers.transport.MockRemoteFSTransport`
or any object implementing :class:`~composite3dgen.providers.transport.RemoteFSTransport`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from composite3dgen.nodes import mwt1 as mwt1_facts
from composite3dgen.nodes.capabilities import (
    BASE_REQUIRED,
    CAPABILITY_ORDER,
    MIN_TRIPOSR_VRAM_GB,
    OPTIONAL_CAPABILITIES,
    PHOTOGRAMMETRY_ANY_OF,
    STAGE_REQUIREMENTS,
    CapabilityName,
    CapabilityStatus,
    StageName,
    remediation_for,
    required_for_stage,
)
from composite3dgen.providers.transport import RemoteFSTransport

# Marker string for facts not verified on the live node (private LAN).
VERIFY_ON_LAN = "verify on LAN"


@dataclass(frozen=True)
class CapabilityResult:
    """Outcome of one capability probe."""

    name: CapabilityName
    ok: bool
    required: bool
    detail: str = ""
    remediation: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "required": self.required,
            "detail": self.detail,
            "remediation": self.remediation,
            "meta": dict(self.meta),
        }


@dataclass
class HealthReport:
    """Full MWT1 capability matrix + selection hints."""

    node: str
    address: str
    user: str
    job_root: str
    reachable: bool
    capabilities: dict[CapabilityName, CapabilityResult] = field(default_factory=dict)
    missing_required: list[CapabilityName] = field(default_factory=list)
    missing_optional: list[CapabilityName] = field(default_factory=list)
    healthy_for_base: bool = False
    stages: dict[str, CapabilityStatus] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    transport_kind: str = "none"

    @property
    def ok(self) -> bool:
        """True when base MWT1-capable stages can run (fail-closed)."""
        return self.healthy_for_base

    def as_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "address": self.address,
            "user": self.user,
            "job_root": self.job_root,
            "reachable": self.reachable,
            "healthy_for_base": self.healthy_for_base,
            "ok": self.ok,
            "missing_required": list(self.missing_required),
            "missing_optional": list(self.missing_optional),
            "capabilities": {k: v.as_dict() for k, v in self.capabilities.items()},
            "stages": dict(self.stages),
            "notes": list(self.notes),
            "facts": dict(self.facts),
            "transport_kind": self.transport_kind,
            "verify_on_lan_marker": VERIFY_ON_LAN,
        }

    def require_stage(self, stage: StageName) -> None:
        """Raise :class:`CapabilityError` if stage requirements are unmet."""
        from composite3dgen.nodes.capabilities import CapabilityError

        missing = [
            name
            for name in required_for_stage(stage)
            if name not in self.capabilities or not self.capabilities[name].ok
        ]
        if stage == "photogrammetry":
            if not any(
                self.capabilities.get(n) and self.capabilities[n].ok
                for n in PHOTOGRAMMETRY_ANY_OF
            ):
                for n in PHOTOGRAMMETRY_ANY_OF:
                    if n not in missing:
                        missing.append(n)
        if missing:
            remediations = tuple(remediation_for(n) for n in missing)
            raise CapabilityError(
                stage=stage,
                missing=tuple(missing),
                remediations=remediations,
            )


@dataclass
class HealthChecker:
    """Run capability probes over an injectable :class:`RemoteFSTransport`."""

    transport: RemoteFSTransport
    job_root: str = field(default_factory=lambda: mwt1_facts.DEFAULT_JOB_ROOT)
    triposr_dir: str = field(default_factory=lambda: mwt1_facts.DEFAULT_TRIPOSR_DIR)
    pin_commit: str = field(default_factory=lambda: mwt1_facts.TRIPOSR_PIN_COMMIT)
    min_vram_gb: float = MIN_TRIPOSR_VRAM_GB
    blender_candidates: Sequence[str] = field(
        default_factory=lambda: list(mwt1_facts.BLENDER_CANDIDATE_PATHS)
    )
    timeout: float = 30.0

    def probe_all(self) -> HealthReport:
        """Probe the full capability matrix and stage readiness."""
        report = HealthReport(
            node=mwt1_facts.host_alias(),
            address=mwt1_facts.host_address(),
            user=mwt1_facts.host_user(),
            job_root=self.job_root,
            reachable=False,
            transport_kind=type(self.transport).__name__,
            facts=_placeholder_facts(
                job_root=self.job_root,
                triposr_dir=self.triposr_dir,
                pin_commit=self.pin_commit,
            ),
        )

        ssh = self._probe_ssh()
        report.capabilities["ssh"] = ssh
        report.reachable = ssh.ok
        if not ssh.ok:
            for name in CAPABILITY_ORDER:
                if name == "ssh":
                    continue
                required = name in BASE_REQUIRED
                report.capabilities[name] = CapabilityResult(
                    name=name,
                    ok=False,
                    required=required,
                    detail="Skipped — SSH unreachable",
                    remediation=remediation_for(
                        "ssh" if required else name
                    ),
                )
            report.notes.append(
                "MWT1 unreachable from this host (likely private LAN / cloud VM). "
                "Controller degraded mode is the fallback; re-run "
                "`composite3dgen doctor --live` on the LAN controller, or place a "
                "follow-up agent on the mwt1 self-hosted worker."
            )
            self._finalize(report)
            return report

        for probe in (
            self._probe_job_root,
            self._probe_ffmpeg,
            self._probe_python_image,
            self._probe_cuda_pytorch,
            self._probe_blender,
            self._probe_triposr,
            self._probe_colmap,
            self._probe_meshroom,
        ):
            result = probe()
            report.capabilities[result.name] = result
            for key, value in result.meta.items():
                if key.endswith("_path") or key in (
                    "vram_gb",
                    "cuda_available",
                    "torch_version",
                    "blender_version",
                    "ffmpeg_version",
                    "git_head",
                    "pin_match",
                    "device_name",
                ):
                    report.facts[key] = value

        self._finalize(report)
        return report

    def _finalize(self, report: HealthReport) -> None:
        report.missing_required = [
            name
            for name in BASE_REQUIRED
            if name not in report.capabilities or not report.capabilities[name].ok
        ]
        report.missing_optional = [
            name
            for name in OPTIONAL_CAPABILITIES
            if name not in report.capabilities or not report.capabilities[name].ok
        ]
        report.healthy_for_base = report.reachable and not report.missing_required

        for stage, reqs in STAGE_REQUIREMENTS.items():
            missing = [
                n
                for n in reqs
                if n not in report.capabilities or not report.capabilities[n].ok
            ]
            if stage == "photogrammetry":
                if not any(
                    report.capabilities.get(n) and report.capabilities[n].ok
                    for n in PHOTOGRAMMETRY_ANY_OF
                ):
                    missing.extend(
                        n
                        for n in PHOTOGRAMMETRY_ANY_OF
                        if n not in missing
                    )
            report.stages[stage] = "ready" if not missing else "blocked"

        if report.healthy_for_base:
            report.notes.append(
                "Base MWT1 capabilities OK for ingest / quality / packs."
            )
        else:
            report.notes.append(
                "Fail closed: missing required capabilities — "
                + (", ".join(report.missing_required) or "ssh")
            )
            for name in report.missing_required:
                cap = report.capabilities.get(name)
                if cap and cap.remediation:
                    report.notes.append(f"remediation[{name}]: {cap.remediation}")

    def _run(self, command: str) -> tuple[int, str, str]:
        return self.transport.run(command, timeout=self.timeout)

    def _probe_ssh(self) -> CapabilityResult:
        try:
            code, out, err = self._run("echo __mwt1_ssh_ok__")
        except Exception as exc:  # noqa: BLE001 — probe must not raise
            return CapabilityResult(
                name="ssh",
                ok=False,
                required=True,
                detail=f"SSH transport error: {exc}",
                remediation=remediation_for("ssh"),
            )
        ok = code == 0 and "__mwt1_ssh_ok__" in out
        return CapabilityResult(
            name="ssh",
            ok=ok,
            required=True,
            detail=out.strip() if ok else (err.strip() or out.strip() or f"exit {code}"),
            remediation=None if ok else remediation_for("ssh"),
        )

    def _probe_job_root(self) -> CapabilityResult:
        marker = f"{self.job_root}/.composite3dgen_write_probe"
        cmd = (
            f"mkdir -p {self.job_root} && "
            f"printf ok > {marker} && "
            f"test -f {marker} && rm -f {marker} && echo writable"
        )
        code, out, err = self._run(cmd)
        ok = code == 0 and "writable" in out
        return CapabilityResult(
            name="job_root_writable",
            ok=ok,
            required=True,
            detail=out.strip() if ok else (err.strip() or out.strip() or f"exit {code}"),
            remediation=None if ok else remediation_for("job_root_writable"),
            meta={"job_root": self.job_root},
        )

    def _probe_ffmpeg(self) -> CapabilityResult:
        code, out, err = self._run(
            "command -v ffmpeg && ffmpeg -version 2>&1 | head -n 1"
        )
        ok = code == 0 and "ffmpeg" in out.lower()
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        path = lines[0] if lines else ""
        version = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
        meta: dict[str, Any] = {}
        if path and not path.lower().startswith("ffmpeg version"):
            meta["ffmpeg_path"] = path
        elif ok:
            meta["ffmpeg_path"] = path or f"<{VERIFY_ON_LAN}>"
        if version:
            meta["ffmpeg_version"] = version
        return CapabilityResult(
            name="ffmpeg",
            ok=ok,
            required=True,
            detail=version or (err.strip() or out.strip() or f"exit {code}"),
            remediation=None if ok else remediation_for("ffmpeg"),
            meta=meta,
        )

    def _probe_python_image(self) -> CapabilityResult:
        cmd = (
            "python3 -c "
            "\"import importlib.util as u; "
            "miss=[m for m in ('PIL',) if u.find_spec(m) is None]; "
            "np=u.find_spec('numpy') is not None; "
            "print('pillow_ok' if not miss else 'pillow_missing:'+','.join(miss)); "
            "print('numpy_ok' if np else 'numpy_missing')\""
        )
        code, out, err = self._run(cmd)
        pillow_ok = code == 0 and "pillow_ok" in out
        numpy_ok = "numpy_ok" in out
        detail = out.strip() if out.strip() else (err.strip() or f"exit {code}")
        if pillow_ok and not numpy_ok:
            detail = f"{detail} (numpy optional warning)"
        return CapabilityResult(
            name="python_image",
            ok=pillow_ok,
            required=True,
            detail=detail,
            remediation=None if pillow_ok else remediation_for("python_image"),
            meta={"pillow": pillow_ok, "numpy": numpy_ok},
        )

    def _probe_cuda_pytorch(self) -> CapabilityResult:
        """Probe GPU PyTorch: MPS (mwt1 Metal, experimental) or CUDA (optional Linux).

        Capability name stays ``cuda_pytorch`` for schema stability; readiness is
        MPS **or** CUDA+VRAM. Fail closed with remediation when neither works.
        """
        cmd = (
            "python3 -c "
            "\"import json;"
            "info={'torch':False,'cuda':False,'mps':False,'vram_gb':None,"
            "'torch_version':None,'error':None,'device_name':None,'backend':None};"
            "try:"
            " import torch;"
            " info['torch']=True;"
            " info['torch_version']=str(torch.__version__);"
            " info['cuda']=bool(torch.cuda.is_available());"
            " info['mps']=bool(getattr(torch.backends,'mps',None) and "
            "torch.backends.mps.is_available());"
            " info.update("
            "{'vram_gb': round(torch.cuda.get_device_properties(0).total_memory/(1024**3),2),"
            " 'device_name': torch.cuda.get_device_properties(0).name,"
            " 'backend':'cuda'}"
            " if info['cuda'] else "
            "({'device_name':'Apple Metal/MPS','backend':'mps'} if info['mps'] else {}));"
            "except Exception as e:"
            " info['error']=str(e);"
            "print(json.dumps(info))\""
        )
        code, out, err = self._run(cmd)
        info: dict[str, Any] = {}
        if code == 0 and out.strip():
            try:
                for line in reversed(out.splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        info = json.loads(line)
                        break
            except json.JSONDecodeError:
                info = {"error": f"unparseable: {out.strip()[:200]}"}
        else:
            info = {"error": err.strip() or out.strip() or f"exit {code}"}

        vram = info.get("vram_gb")
        mps_ok = bool(info.get("torch")) and bool(info.get("mps"))
        cuda_ok = bool(info.get("torch")) and bool(info.get("cuda"))
        vram_ok = isinstance(vram, (int, float)) and float(vram) >= self.min_vram_gb
        # mwt1 policy: MPS sufficient (experimental). CUDA+VRAM remains valid
        # on Linux GPU hosts. Neither → fail closed.
        ok = mps_ok or (cuda_ok and vram_ok)
        detail_parts: list[str] = []
        if info.get("torch_version"):
            detail_parts.append(f"torch={info['torch_version']}")
        if info.get("backend"):
            detail_parts.append(f"backend={info['backend']}")
        if info.get("device_name"):
            detail_parts.append(f"device={info['device_name']}")
        if vram is not None:
            detail_parts.append(f"vram_gb={vram}")
        if mps_ok:
            detail_parts.append("mps_experimental=true")
        if info.get("error"):
            detail_parts.append(f"error={info['error']}")
        if cuda_ok and not vram_ok and not mps_ok:
            detail_parts.append(f"cuda_vram_need>={self.min_vram_gb}GB")
        if bool(info.get("torch")) and not ok:
            detail_parts.append("need_mps_or_cuda")
        return CapabilityResult(
            name="cuda_pytorch",
            ok=ok,
            required=False,
            detail="; ".join(detail_parts) or "pytorch GPU backend unavailable",
            remediation=None if ok else remediation_for("cuda_pytorch"),
            meta={
                "cuda_available": bool(info.get("cuda")),
                "mps_available": bool(info.get("mps")),
                "backend": info.get("backend"),
                "vram_gb": vram,
                "torch_version": info.get("torch_version"),
                "device_name": info.get("device_name"),
                "cuda_device": info.get("device_name")
                if info.get("cuda")
                else f"<{VERIFY_ON_LAN}>",
                "experimental_mps": bool(mps_ok),
            },
        )

    def _probe_blender(self) -> CapabilityResult:
        candidates = " ".join(self.blender_candidates)
        cmd = (
            "BL=;"
            "if command -v blender >/dev/null 2>&1; then BL=$(command -v blender); fi;"
            f"for c in {candidates}; do "
            "if [ -z \"$BL\" ] && [ -x \"$c\" ]; then BL=$c; fi; "
            "done;"
            "if [ -n \"$BL\" ]; then "
            "echo \"path=$BL\"; "
            "\"$BL\" --version 2>&1 | head -n 1; "
            "else echo missing; exit 1; fi"
        )
        code, out, err = self._run(cmd)
        path_match = re.search(r"path=(.+)", out)
        path = path_match.group(1).strip() if path_match else None
        version_line = ""
        for line in out.splitlines():
            if line.strip().lower().startswith("blender"):
                version_line = line.strip()
                break
        ok = code == 0 and bool(path)
        meta: dict[str, Any] = {
            "blender_path": path if path else f"<{VERIFY_ON_LAN}>",
        }
        if version_line:
            meta["blender_version"] = version_line
        return CapabilityResult(
            name="blender",
            ok=ok,
            required=False,
            detail=version_line or (path or err.strip() or out.strip() or f"exit {code}"),
            remediation=None if ok else remediation_for("blender"),
            meta=meta,
        )

    def _probe_triposr(self) -> CapabilityResult:
        pin = self.pin_commit
        directory = self.triposr_dir
        cmd = (
            f"if [ -d {directory} ]; then "
            f"echo dir_ok; "
            f"if [ -f {directory}/run.py ]; then echo run_py_ok; else echo run_py_missing; fi; "
            f"if [ -d {directory}/.git ]; then "
            f"HEAD=$(git -C {directory} rev-parse HEAD 2>/dev/null || echo unknown); "
            f"echo head=$HEAD; "
            f"else echo head=nogit; fi; "
            f"else echo dir_missing; fi"
        )
        code, out, err = self._run(cmd)
        dir_ok = "dir_ok" in out
        run_ok = "run_py_ok" in out
        head_match = re.search(r"head=(\S+)", out)
        head = head_match.group(1) if head_match else None
        pin_match = bool(head) and head not in ("nogit", "unknown") and (
            head.startswith(pin) or pin.startswith(head) or head == pin
        )
        ok = code == 0 and dir_ok and run_ok
        detail = out.strip() or err.strip() or f"exit {code}"
        if ok and head and not pin_match and head not in ("nogit", "unknown"):
            detail = f"{detail}; pin_mismatch expected={pin}"
        return CapabilityResult(
            name="triposr",
            ok=ok,
            required=False,
            detail=detail,
            remediation=None if ok else remediation_for("triposr"),
            meta={
                "triposr_dir": directory,
                "git_head": head or f"<{VERIFY_ON_LAN}>",
                "pin_commit": pin,
                "pin_match": pin_match,
                "run_py": f"{directory}/run.py" if run_ok else f"<{VERIFY_ON_LAN}>",
            },
        )

    def _probe_colmap(self) -> CapabilityResult:
        code, out, err = self._run(
            "if command -v colmap >/dev/null 2>&1; then "
            "echo path=$(command -v colmap); colmap -h 2>&1 | head -n 1; "
            "else echo missing; exit 1; fi"
        )
        path_match = re.search(r"path=(.+)", out)
        path = path_match.group(1).strip() if path_match else None
        ok = code == 0 and bool(path)
        return CapabilityResult(
            name="colmap",
            ok=ok,
            required=False,
            detail=out.strip() if ok else (err.strip() or out.strip() or "missing"),
            remediation=None if ok else remediation_for("colmap"),
            meta={"colmap_path": path if path else f"<{VERIFY_ON_LAN}>"},
        )

    def _probe_meshroom(self) -> CapabilityResult:
        code, out, err = self._run(
            "if command -v meshroom_batch >/dev/null 2>&1; then "
            "echo path=$(command -v meshroom_batch); "
            "elif command -v Meshroom >/dev/null 2>&1; then "
            "echo path=$(command -v Meshroom); "
            "else echo missing; exit 1; fi"
        )
        path_match = re.search(r"path=(.+)", out)
        path = path_match.group(1).strip() if path_match else None
        ok = code == 0 and bool(path)
        return CapabilityResult(
            name="meshroom",
            ok=ok,
            required=False,
            detail=out.strip() if ok else (err.strip() or out.strip() or "missing"),
            remediation=None if ok else remediation_for("meshroom"),
            meta={"meshroom_path": path if path else f"<{VERIFY_ON_LAN}>"},
        )


def _placeholder_facts(
    *,
    job_root: str,
    triposr_dir: str,
    pin_commit: str,
) -> dict[str, Any]:
    return {
        "ssh_host": mwt1_facts.host_alias(),
        "ssh_address": mwt1_facts.host_address(),
        "ssh_user": mwt1_facts.host_user(),
        "job_root": job_root,
        "triposr_dir": triposr_dir,
        "triposr_pin_commit": pin_commit,
        "blender_path": f"<{VERIFY_ON_LAN}>",
        "cuda_device": f"<{VERIFY_ON_LAN}>",
        "ffmpeg_path": f"<{VERIFY_ON_LAN}>",
        "colmap_path": f"<{VERIFY_ON_LAN}>",
        "meshroom_path": f"<{VERIFY_ON_LAN}>",
    }


@dataclass
class _UnreachableTransport:
    """Sentinel transport used only to share finalize helpers."""

    def run(self, command: str, *, timeout: float = 600.0) -> tuple[int, str, str]:
        del command, timeout
        return 255, "", "unreachable"

    def upload(self, local: Any, remote: str) -> None:
        raise RuntimeError("unreachable")

    def download(self, remote: str, local: Any) -> None:
        raise RuntimeError("unreachable")

    def exists(self, remote: str) -> bool:
        return False

    def makedirs(self, remote: str) -> None:
        raise RuntimeError("unreachable")


def run_health_check(
    transport: RemoteFSTransport | None = None,
    *,
    use_live_ssh: bool = False,
    **kwargs: Any,
) -> HealthReport:
    """Run probes. Default: no live SSH unless ``use_live_ssh`` or transport given.

    When neither transport nor ``use_live_ssh`` is set, returns an unreachable
    report with ``verify on LAN`` placeholders (safe for CI / cloud agents).
    """
    allowed = {
        "job_root",
        "triposr_dir",
        "pin_commit",
        "min_vram_gb",
        "blender_candidates",
        "timeout",
    }
    checker_kwargs = {k: v for k, v in kwargs.items() if k in allowed}

    if transport is None and use_live_ssh:
        from composite3dgen.providers.transport import SubprocessSSHTransport

        transport = SubprocessSSHTransport(host=mwt1_facts.host_alias())

    if transport is None:
        job_root = checker_kwargs.get("job_root", mwt1_facts.DEFAULT_JOB_ROOT)
        triposr_dir = checker_kwargs.get("triposr_dir", mwt1_facts.DEFAULT_TRIPOSR_DIR)
        pin_commit = checker_kwargs.get("pin_commit", mwt1_facts.TRIPOSR_PIN_COMMIT)
        report = HealthReport(
            node=mwt1_facts.host_alias(),
            address=mwt1_facts.host_address(),
            user=mwt1_facts.host_user(),
            job_root=job_root,
            reachable=False,
            transport_kind="none",
            notes=[
                "No transport injected and use_live_ssh=False — "
                "skipping live probes (controller/CI safe).",
                f"Expected host facts are placeholders marked <{VERIFY_ON_LAN}>.",
            ],
            facts=_placeholder_facts(
                job_root=job_root,
                triposr_dir=triposr_dir,
                pin_commit=pin_commit,
            ),
        )
        for name in CAPABILITY_ORDER:
            required = name in BASE_REQUIRED
            report.capabilities[name] = CapabilityResult(
                name=name,
                ok=False,
                required=required,
                detail="Not probed (no transport)",
                remediation=remediation_for(name),
            )
        HealthChecker(transport=_UnreachableTransport())._finalize(report)  # noqa: SLF001
        return report

    return HealthChecker(transport=transport, **checker_kwargs).probe_all()


def capability_matrix_fixture(
    *,
    ok: Mapping[CapabilityName, bool] | None = None,
    reachable: bool = True,
) -> HealthReport:
    """Build a synthetic :class:`HealthReport` for tests (no SSH)."""
    flags = dict(ok or {})
    report = HealthReport(
        node=mwt1_facts.host_alias(),
        address=mwt1_facts.host_address(),
        user=mwt1_facts.host_user(),
        job_root=mwt1_facts.DEFAULT_JOB_ROOT,
        reachable=reachable,
        transport_kind="fixture",
        facts={
            "blender_path": f"<{VERIFY_ON_LAN}>",
            "cuda_device": f"<{VERIFY_ON_LAN}>",
        },
        notes=["Synthetic capability matrix fixture"],
    )
    if not reachable:
        for name in CAPABILITY_ORDER:
            report.capabilities[name] = CapabilityResult(
                name=name,
                ok=False,
                required=name in BASE_REQUIRED,
                detail="fixture unreachable",
                remediation=remediation_for(name),
            )
    else:
        for name in CAPABILITY_ORDER:
            is_ok = flags.get(name, name in BASE_REQUIRED)
            report.capabilities[name] = CapabilityResult(
                name=name,
                ok=bool(is_ok),
                required=name in BASE_REQUIRED,
                detail="fixture ok" if is_ok else "fixture missing",
                remediation=None if is_ok else remediation_for(name),
            )
    HealthChecker(transport=_UnreachableTransport())._finalize(report)  # noqa: SLF001
    return report
