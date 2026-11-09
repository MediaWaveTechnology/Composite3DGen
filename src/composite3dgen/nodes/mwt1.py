"""MWT1 node contract: SSH host facts, job staging, health probe wiring.

Host (playbook): ``ssh mwt1`` → ``192.168.50.212``, user ``davethompson``.

**Preferred storage (user decision):** ``/Volumes/AlanTBrain/composite3dgen/``
for jobs, media, and heavy installs (home disk ~13 GiB free — too tight).
Probe noted AlanTBrain listing may return Operation not permitted — mount
and ACL must be fixed on node; path layout is still the contract default.

**TripoSR GPU path (user decision):** try **PyTorch MPS / Metal** on Apple M4
(experimental). CUDA is optional (Linux GPU hosts), not required on mwt1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from composite3dgen.nodes.capabilities import CapabilityError, StageName

# --- Host facts ---

HOST_ALIAS = "mwt1"
HOST_ADDRESS = "192.168.50.212"
HOST_USER = "davethompson"

# Preferred volume for jobs / media / heavy installs (user decision).
ALANTBRAIN_VOLUME = "/Volumes/AlanTBrain"
ALANTBRAIN_ROOT = f"{ALANTBRAIN_VOLUME}/composite3dgen"

# Contract defaults — AlanTBrain when mounted. Home bootstrap from the live
# probe (`~/composite3dgen/jobs`) is fallback only; do not use home for heavy data.
DEFAULT_REMOTE_ROOT = ALANTBRAIN_ROOT
DEFAULT_JOB_ROOT = f"{ALANTBRAIN_ROOT}/jobs"
DEFAULT_MEDIA_ROOT = f"{ALANTBRAIN_ROOT}/media"
DEFAULT_VENDOR_ROOT = f"{ALANTBRAIN_ROOT}/vendor"
DEFAULT_TRIPOSR_DIR = f"{DEFAULT_VENDOR_ROOT}/TripoSR"
DEFAULT_RUN_PY = f"{DEFAULT_TRIPOSR_DIR}/run.py"

# Verified-writable bootstrap created during probe (home) — not the happy path.
HOME_BOOTSTRAP_JOB_ROOT = "/Users/davethompson/composite3dgen/jobs"

# Upstream pin for VAST-AI-Research/TripoSR.
TRIPOSR_PIN_COMMIT = "107cefdc244c39106fa830359024f6a2f1c78871"
TRIPOSR_REPO_URL = "https://github.com/VAST-AI-Research/TripoSR.git"
TRIPOSR_WEIGHTS = "stabilityai/TripoSR"
# mwt1: Metal/MPS experimental; CUDA optional on Linux GPU nodes only.
TRIPOSR_DEVICE_POLICY = "mps_preferred_on_mwt1"

# Candidate Blender locations to *search* during probes.
# Verified on MWT1: Homebrew PATH + app bundle.
BLENDER_CANDIDATE_PATHS: tuple[str, ...] = (
    "/opt/homebrew/bin/blender",
    "/Applications/Blender.app/Contents/MacOS/Blender",
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


def remote_job_path(subject_id: str, job_id: str | None = None) -> str:
    """Build ``…/composite3dgen/jobs/<subject>[/<job_id>]`` remote path."""
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
    """Probe MWT1 base capabilities via injected or live-SSH transport."""
    from composite3dgen.nodes.health import run_health_check

    if _DEFAULT_TRANSPORT is not None:
        report = run_health_check(transport=_DEFAULT_TRANSPORT)  # type: ignore[arg-type]
        return report.ok
    report = run_health_check(use_live_ssh=True)
    return report.ok


def is_healthy(probe: HealthProbe | None = None) -> bool:
    """Return whether MWT1 looks usable for base MWT1-capable stages.

    Fail closed: exceptions and missing probes that cannot reach the node
    return ``False`` so the selector uses controller-local degraded mode.
    """
    active = probe if probe is not None else _DEFAULT_PROBE
    if active is None:
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
    remote_root: str = DEFAULT_REMOTE_ROOT
    media_root: str = DEFAULT_MEDIA_ROOT
    vendor_root: str = DEFAULT_VENDOR_ROOT
    triposr_dir: str = DEFAULT_TRIPOSR_DIR
    triposr_pin: str = TRIPOSR_PIN_COMMIT
    triposr_repo: str = TRIPOSR_REPO_URL
    triposr_weights: str = TRIPOSR_WEIGHTS
    triposr_device_policy: str = TRIPOSR_DEVICE_POLICY
    alantbrain_volume: str = ALANTBRAIN_VOLUME
    home_bootstrap_job_root: str = HOME_BOOTSTRAP_JOB_ROOT

    def as_dict(self) -> dict:
        return {
            "alias": self.alias,
            "address": self.address,
            "user": self.user,
            "job_root": self.job_root,
            "remote_root": self.remote_root,
            "media_root": self.media_root,
            "vendor_root": self.vendor_root,
            "triposr_dir": self.triposr_dir,
            "triposr_pin": self.triposr_pin,
            "triposr_repo": self.triposr_repo,
            "triposr_weights": self.triposr_weights,
            "triposr_device_policy": self.triposr_device_policy,
            "alantbrain_volume": self.alantbrain_volume,
            "home_bootstrap_job_root": self.home_bootstrap_job_root,
            "blender_candidates": list(BLENDER_CANDIDATE_PATHS),
            "note": (
                "Prefer /Volumes/AlanTBrain/composite3dgen for jobs/media/vendor. "
                "TripoSR on mwt1 uses experimental PyTorch MPS (Metal); CUDA optional."
            ),
        }


def node_contract() -> MWT1NodeContract:
    """Return the static MWT1 contract (no live probe)."""
    return MWT1NodeContract()


__all__ = [
    "ALANTBRAIN_ROOT",
    "ALANTBRAIN_VOLUME",
    "BLENDER_CANDIDATE_PATHS",
    "DEFAULT_JOB_ROOT",
    "DEFAULT_MEDIA_ROOT",
    "DEFAULT_REMOTE_ROOT",
    "DEFAULT_RUN_PY",
    "DEFAULT_TRIPOSR_DIR",
    "DEFAULT_VENDOR_ROOT",
    "HOME_BOOTSTRAP_JOB_ROOT",
    "HOST_ADDRESS",
    "HOST_ALIAS",
    "HOST_USER",
    "HealthProbe",
    "MWT1NodeContract",
    "TRIPOSR_DEVICE_POLICY",
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
    "node_contract",
    "remote_job_path",
    "set_default_transport",
    "set_health_probe",
]
