"""MWT1 node contract: SSH host facts, job staging, health probe wiring.

Host (playbook): ``ssh mwt1`` → ``192.168.50.212``, user ``davethompson``.
Job root: ``~/composite3dgen/jobs/``.

Live capability paths (Blender, CUDA device, COLMAP) must be verified on the
LAN or via the mwt1 self-hosted worker — cloud VMs cannot reach the private
LAN. See ``deploy/mwt1/README.md`` and
``internal/mwt1-capability-probe.md`` (store) for verified facts when present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from composite3dgen.nodes.capabilities import CapabilityError, StageName

# --- Host facts (expected; live paths marked verify-on-LAN until probed) ---

HOST_ALIAS = "mwt1"
HOST_ADDRESS = "192.168.50.212"
HOST_USER = "davethompson"
DEFAULT_JOB_ROOT = "~/composite3dgen/jobs"
DEFAULT_REMOTE_ROOT = "~/composite3dgen"
DEFAULT_TRIPOSR_DIR = "~/composite3dgen/vendor/TripoSR"
DEFAULT_RUN_PY = f"{DEFAULT_TRIPOSR_DIR}/run.py"

# Upstream pin for VAST-AI-Research/TripoSR (main as of U3b docs).
# Checkout on MWT1 still needs LAN verification — see deploy/mwt1/README.md.
TRIPOSR_PIN_COMMIT = "107cefdc244c39106fa830359024f6a2f1c78871"
TRIPOSR_REPO_URL = "https://github.com/VAST-AI-Research/TripoSR.git"
TRIPOSR_WEIGHTS = "stabilityai/TripoSR"

# Candidate Blender locations to *search* during probes — never treat as verified.
BLENDER_CANDIDATE_PATHS: tuple[str, ...] = (
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/snap/bin/blender",
    "~/blender/blender",
    "/Applications/Blender.app/Contents/MacOS/Blender",
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
    """Remote job staging directory on MWT1."""
    return DEFAULT_JOB_ROOT


def remote_job_path(subject_id: str, job_id: str | None = None) -> str:
    """Build ``~/composite3dgen/jobs/<subject>[/<job_id>]`` remote path."""
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
            "remote_root": self.remote_root,
            "triposr_dir": self.triposr_dir,
            "triposr_pin": self.triposr_pin,
            "triposr_repo": self.triposr_repo,
            "triposr_weights": self.triposr_weights,
            "blender_candidates": list(BLENDER_CANDIDATE_PATHS),
            "note": (
                "Live blender/cuda/colmap paths are verify-on-LAN until "
                "recorded from mwt1-capability-probe.md or doctor --live."
            ),
        }


def node_contract() -> MWT1NodeContract:
    """Return the static MWT1 contract (no live probe)."""
    return MWT1NodeContract()


__all__ = [
    "BLENDER_CANDIDATE_PATHS",
    "DEFAULT_JOB_ROOT",
    "DEFAULT_REMOTE_ROOT",
    "DEFAULT_RUN_PY",
    "DEFAULT_TRIPOSR_DIR",
    "HOST_ADDRESS",
    "HOST_ALIAS",
    "HOST_USER",
    "HealthProbe",
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
    "node_contract",
    "remote_job_path",
    "set_default_transport",
    "set_health_probe",
]
