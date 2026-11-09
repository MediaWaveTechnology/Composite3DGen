"""Capability names, stage matrix, and fail-closed remediations for MWT1.

U3b: probes live in :mod:`composite3dgen.nodes.health`. This module is the
contract surface — which stages need which capabilities, and what to tell the
operator when a required probe fails.
"""

from __future__ import annotations

from typing import Literal

CapabilityName = Literal[
    "ssh",
    "job_root_writable",
    "ffmpeg",
    "python_image",
    "cuda_pytorch",
    "blender",
    "triposr",
    "colmap",
    "meshroom",
]

StageName = Literal[
    "ingest_ffmpeg",
    "quality_composites",
    "triposr",
    "photogrammetry",
    "blender_explode",
    "qa_renders",
]

CapabilityStatus = Literal["ready", "blocked"]

# Ordered for doctor / report output.
CAPABILITY_ORDER: tuple[CapabilityName, ...] = (
    "ssh",
    "job_root_writable",
    "ffmpeg",
    "python_image",
    "cuda_pytorch",
    "blender",
    "triposr",
    "colmap",
    "meshroom",
)

# Required for preferring MWT1 over controller-local for U2 packs.
BASE_REQUIRED: tuple[CapabilityName, ...] = (
    "ssh",
    "job_root_writable",
    "ffmpeg",
    "python_image",
)

OPTIONAL_CAPABILITIES: frozenset[CapabilityName] = frozenset(
    {"colmap", "meshroom"}
)

# Stage → required capabilities (fail closed when any are missing).
STAGE_REQUIREMENTS: dict[StageName, tuple[CapabilityName, ...]] = {
    "ingest_ffmpeg": ("ssh", "job_root_writable", "ffmpeg"),
    "quality_composites": ("ssh", "job_root_writable", "python_image"),
    "triposr": ("ssh", "job_root_writable", "cuda_pytorch", "triposr"),
    "photogrammetry": ("ssh", "job_root_writable"),  # needs colmap OR meshroom
    "blender_explode": ("ssh", "job_root_writable", "blender"),
    "qa_renders": ("ssh", "job_root_writable", "blender", "python_image"),
}

# Photogrammetry needs at least one of these optional tools.
PHOTOGRAMMETRY_ANY_OF: tuple[CapabilityName, ...] = ("colmap", "meshroom")

MIN_TRIPOSR_VRAM_GB = 6.0

REMEDIATIONS: dict[CapabilityName, str] = {
    "ssh": (
        "Cannot reach MWT1 over SSH. From a LAN controller: "
        "`ssh mwt1` (Host mwt1 → 192.168.50.212, user davethompson). "
        "Cloud VMs cannot reach the private LAN — place a follow-up agent on "
        "the mwt1 self-hosted worker, or run `composite3dgen doctor --live` "
        "from the controller. Until then, use controller degraded mode "
        "(`--executor local`)."
    ),
    "job_root_writable": (
        "Job root not writable. Prefer AlanTBrain (not home): "
        "`mkdir -p /Volumes/AlanTBrain/composite3dgen/jobs "
        "/Volumes/AlanTBrain/composite3dgen/media && "
        "touch /Volumes/AlanTBrain/composite3dgen/jobs/.write_test && "
        "rm /Volumes/AlanTBrain/composite3dgen/jobs/.write_test`. "
        "Ensure `/Volumes/AlanTBrain` is mounted for user `davethompson`."
    ),
    "ffmpeg": (
        "ffmpeg missing on MWT1. Install (apt/brew) so `command -v ffmpeg` "
        "succeeds; required for video frame extract on the happy path."
    ),
    "python_image": (
        "Python image stack incomplete on MWT1. Need python3 with Pillow "
        "(`python3 -c 'from PIL import Image'`). Optional: numpy. "
        "Install into the node env used for quality/composites."
    ),
    "cuda_pytorch": (
        "CUDA/PyTorch unavailable or VRAM < ~6GB for TripoSR. On MWT1 verify: "
        "`python3 -c \"import torch; print(torch.cuda.is_available(), "
        "torch.cuda.get_device_properties(0).total_memory/(1024**3))\"`. "
        "Install a CUDA-matched PyTorch wheel; TripoSR needs ~6GB+ VRAM."
    ),
    "blender": (
        "Blender not found on PATH or candidate paths. On MWT1 prefer "
        "`/opt/homebrew/bin/blender` then "
        "`/Applications/Blender.app/Contents/MacOS/Blender` "
        "(probe-verified Blender 5.2.3 LTS; Apple M4 Metal — explode/QA OK). "
        "Re-run `composite3dgen doctor --live` if the install moved."
    ),
    "triposr": (
        "Pinned TripoSR checkout missing. On MWT1 (AlanTBrain preferred): "
        "`mkdir -p /Volumes/AlanTBrain/composite3dgen/vendor && "
        "git clone https://github.com/VAST-AI-Research/TripoSR.git "
        "/Volumes/AlanTBrain/composite3dgen/vendor/TripoSR && "
        "cd /Volumes/AlanTBrain/composite3dgen/vendor/TripoSR && "
        "git checkout 107cefdc244c39106fa830359024f6a2f1c78871` "
        "(see deploy/mwt1/README.md). Confirm `run.py` exists. "
        "Note: MWT1 is Apple M4 Metal — TripoSR CUDA is a separate issue."
    ),
    "colmap": (
        "COLMAP optional — install when orbit coverage needs local metric "
        "multi-view (U6). Missing COLMAP alone does not block base MWT1 packs."
    ),
    "meshroom": (
        "Meshroom optional — alternative to COLMAP for photogrammetry (U6). "
        "Missing Meshroom alone does not block base MWT1 packs."
    ),
}


class CapabilityError(RuntimeError):
    """Raised when a stage is requested but required capabilities are missing."""

    def __init__(
        self,
        *,
        stage: StageName,
        missing: tuple[CapabilityName, ...],
        remediations: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.missing = missing
        self.remediations = remediations
        msg = (
            f"MWT1 cannot run stage '{stage}': missing {', '.join(missing)}. "
            "Fail closed — see remediation notes."
        )
        if remediations:
            msg = msg + "\n" + "\n".join(remediations)
        super().__init__(msg)


def remediation_for(name: CapabilityName) -> str:
    """Return operator remediation text for a capability."""
    return REMEDIATIONS[name]


def required_for_stage(stage: StageName) -> tuple[CapabilityName, ...]:
    """Return hard-required capabilities for a pipeline stage."""
    return STAGE_REQUIREMENTS[stage]


def probe_stub() -> dict:
    """Backward-compatible stub used by older call sites; prefer health.probe."""
    from composite3dgen.nodes.health import run_health_check

    return run_health_check().as_dict()
