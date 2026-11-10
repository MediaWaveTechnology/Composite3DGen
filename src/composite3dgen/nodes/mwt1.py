"""MWT1 node contract: SSH host facts, job staging, health probe wiring.

Host (playbook): ``ssh mwt1`` → ``192.168.50.212``, user ``davethompson``.
Jobs/media prefer ``/Volumes/AlanTBrain/composite3dgen/`` (not home).

Blender paths are probe-verified (Homebrew + App bundle; Apple M4 Metal).
TripoSR CUDA remains separate. See ``deploy/mwt1/README.md`` and store
``internal/mwt1-capability-probe.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from composite3dgen.nodes.capabilities import CapabilityError, StageName

# --- Host facts ---

HOST_ALIAS = "mwt1"
HOST_ADDRESS = "192.168.50.212"
HOST_USER = "davethompson"

# Prefer AlanTBrain for jobs/media (home volume is tight; probe: ~13 GiB free).
# Fallback home path kept only as a degraded note — do not stage large media there.
ALANTBRAIN_ROOT = "/Volumes/AlanTBrain/composite3dgen"
DEFAULT_REMOTE_ROOT = ALANTBRAIN_ROOT
DEFAULT_JOB_ROOT = f"{ALANTBRAIN_ROOT}/jobs"
DEFAULT_MEDIA_ROOT = f"{ALANTBRAIN_ROOT}/media"
DEFAULT_TRIPOSR_DIR = f"{ALANTBRAIN_ROOT}/vendor/TripoSR"
DEFAULT_RUN_PY = f"{DEFAULT_TRIPOSR_DIR}/run.py"
# Legacy home paths (probe created jobs here once) — prefer AlanTBrain above.
HOME_FALLBACK_ROOT = "~/composite3dgen"
HOME_FALLBACK_JOB_ROOT = "~/composite3dgen/jobs"

# Upstream pin for VAST-AI-Research/TripoSR (main as of U3b docs).
# Checkout on MWT1 still needs LAN verification — see deploy/mwt1/README.md.
TRIPOSR_PIN_COMMIT = "107cefdc244c39106fa830359024f6a2f1c78871"
TRIPOSR_REPO_URL = "https://github.com/VAST-AI-Research/TripoSR.git"
TRIPOSR_WEIGHTS = "stabilityai/TripoSR"

# Verified on MWT1 via internal/mwt1-capability-probe.md (Blender 5.2.3 LTS).
# Prefer Homebrew PATH shim; App bundle is the fallback binary on the same host.
# Host is Apple M4 Metal — Blender explode/QA is fine; TripoSR CUDA is separate.
MWT1_BLENDER_PATH = "/opt/homebrew/bin/blender"
MWT1_BLENDER_APP_PATH = "/Applications/Blender.app/Contents/MacOS/Blender"
MWT1_BLENDER_VERSION = "5.2.3 LTS"
MWT1_BLENDER_PREFERRED: tuple[str, ...] = (
    MWT1_BLENDER_PATH,
    MWT1_BLENDER_APP_PATH,
)

# Probe search order: preferred MWT1 paths first, then generic candidates.
BLENDER_CANDIDATE_PATHS: tuple[str, ...] = (
    *MWT1_BLENDER_PREFERRED,
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/snap/bin/blender",
    "~/blender/blender",
)

HealthProbe = Callable[[], bool]

_DEFAULT_PROBE: HealthProbe | None = None
_DEFAULT_TRANSPORT = None  # set via set_default_transport


def host_alias() -> str:
    """SSH Host alias for the primary local compute node."""
    return HOST_ALIAS


def host_address() -> str:
    """LAN address recorded in the playbook."""
    return HOST_ADDRESS


def host_user() -> str:
    """Expected SSH user on MWT1."""
    return HOST_USER


def job_root() -> str:
    """Remote job staging directory on MWT1 (AlanTBrain preferred)."""
    return DEFAULT_JOB_ROOT


def media_root() -> str:
    """Remote media directory on MWT1 (AlanTBrain preferred)."""
    return DEFAULT_MEDIA_ROOT


def remote_job_path(subject_id: str, job_id: str | None = None) -> str:
    """Build ``/Volumes/AlanTBrain/composite3dgen/jobs/<subject>[/<job_id>]``."""
    base = f"{DEFAULT_JOB_ROOT.rstrip('/')}/{subject_id}"
    if job_id:
        return f"{base}/{job_id}"
    return base


def set_health_probe(probe: HealthProbe | None) -> None:
    """Install or clear the injectable MWT1 health probe (tests / CLI)."""
    global _DEFAULT_PROBE
    _DEFAULT_PROBE = probe


def set_default_transport(transport: object | None) -> None:
    """Install default RemoteFSTransport used by :func:`default_health_probe`."""
    global _DEFAULT_TRANSPORT
    _DEFAULT_TRANSPORT = transport


def get_default_transport() -> object | None:
    """Return the installed default transport (if any)."""
    return _DEFAULT_TRANSPORT


def default_health_probe() -> bool:
    """Probe MWT1 base capabilities via injected or live-SSH transport.

    - If a custom probe was set via :func:`set_health_probe`, that wins.
    - Else if a default transport is installed, run health against it.
    - Else attempt live SSH once (may fail from cloud — returns False).
    """
    from composite3dgen.nodes.health import run_health_check

    if _DEFAULT_TRANSPORT is not None:
        report = run_health_check(transport=_DEFAULT_TRANSPORT)  # type: ignore[arg-type]
        return report.ok
    # Live attempt — fail closed when unreachable (typical from cloud VMs).
    report = run_health_check(use_live_ssh=True)
    return report.ok


def is_healthy(probe: HealthProbe | None = None) -> bool:
    """Return whether MWT1 looks usable for base MWT1-capable stages.

    Fail closed: exceptions and missing probes that cannot reach the node
    return ``False`` so the selector uses controller-local degraded mode.
    """
    active = probe if probe is not None else _DEFAULT_PROBE
    if active is None:
        # No explicit probe: try default transport / live SSH, else unhealthy.
        if _DEFAULT_TRANSPORT is not None:
            active = default_health_probe
        else:
            return False
    try:
        return bool(active())
    except Exception:  # noqa: BLE001 — health checks must not raise to callers
        return False


def ensure_stage(stage: StageName, *, transport: object | None = None) -> None:
    """Fail closed if ``stage`` requirements are unmet on the probed node."""
    from composite3dgen.nodes.health import run_health_check

    report = run_health_check(
        transport=transport or _DEFAULT_TRANSPORT,  # type: ignore[arg-type]
        use_live_ssh=transport is None and _DEFAULT_TRANSPORT is None,
    )
    report.require_stage(stage)


def make_ssh_transport(*, host: str | None = None):
    """Build a :class:`SubprocessSSHTransport` aimed at MWT1."""
    from composite3dgen.providers.transport import SubprocessSSHTransport

    return SubprocessSSHTransport(host=host or HOST_ALIAS)


@dataclass(frozen=True)
class MWT1NodeContract:
    """Serializable summary of the MWT1 contract for doctor / docs."""

    alias: str = HOST_ALIAS
    address: str = HOST_ADDRESS
    user: str = HOST_USER
    job_root: str = DEFAULT_JOB_ROOT
    media_root: str = DEFAULT_MEDIA_ROOT
    remote_root: str = DEFAULT_REMOTE_ROOT
    triposr_dir: str = DEFAULT_TRIPOSR_DIR
    triposr_pin: str = TRIPOSR_PIN_COMMIT
    triposr_repo: str = TRIPOSR_REPO_URL
    triposr_weights: str = TRIPOSR_WEIGHTS

    def as_dict(self) -> dict:
        return {
            "alias": self.alias,
            "address": self.address,
            "user": self.user,
            "job_root": self.job_root,
            "media_root": self.media_root,
            "remote_root": self.remote_root,
            "triposr_dir": self.triposr_dir,
            "triposr_pin": self.triposr_pin,
            "triposr_repo": self.triposr_repo,
            "triposr_weights": self.triposr_weights,
            "home_fallback_job_root": HOME_FALLBACK_JOB_ROOT,
            "blender_path": MWT1_BLENDER_PATH,
            "blender_app_path": MWT1_BLENDER_APP_PATH,
            "blender_version": MWT1_BLENDER_VERSION,
            "blender_candidates": list(BLENDER_CANDIDATE_PATHS),
            "note": (
                "Jobs/media prefer /Volumes/AlanTBrain/composite3dgen/ (not home). "
                "Blender 5.2.3 LTS verified (Homebrew + App bundle; Apple M4 Metal). "
                "TripoSR/CUDA/COLMAP remain separate — see deploy/mwt1/README.md."
            ),
        }


def node_contract() -> MWT1NodeContract:
    """Return the static MWT1 contract (no live probe)."""
    return MWT1NodeContract()


__all__ = [
    "ALANTBRAIN_ROOT",
    "BLENDER_CANDIDATE_PATHS",
    "DEFAULT_JOB_ROOT",
    "DEFAULT_MEDIA_ROOT",
    "DEFAULT_REMOTE_ROOT",
    "DEFAULT_RUN_PY",
    "DEFAULT_TRIPOSR_DIR",
    "HOME_FALLBACK_JOB_ROOT",
    "HOME_FALLBACK_ROOT",
    "HOST_ADDRESS",
    "HOST_ALIAS",
    "HOST_USER",
    "HealthProbe",
    "MWT1_BLENDER_APP_PATH",
    "MWT1_BLENDER_PATH",
    "MWT1_BLENDER_PREFERRED",
    "MWT1_BLENDER_VERSION",
    "MWT1NodeContract",
    "TRIPOSR_PIN_COMMIT",
    "TRIPOSR_REPO_URL",
    "TRIPOSR_WEIGHTS",
    "CapabilityError",
    "default_health_probe",
    "ensure_stage",
    "get_default_transport",
    "host_address",
    "host_alias",
    "host_user",
    "is_healthy",
    "job_root",
    "make_ssh_transport",
    "media_root",
    "node_contract",
    "remote_job_path",
    "set_default_transport",
    "set_health_probe",
]
