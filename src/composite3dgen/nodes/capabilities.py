"""Capability probe surface.

U2 exposes a lightweight healthy-check hook via :func:`probe_stub`.
Full capability matrix (ffmpeg, CUDA, Blender, COLMAP, …) lands in **U3b**.
"""

from __future__ import annotations

from typing import Any

from composite3dgen.nodes import mwt1


def probe_stub() -> dict[str, Any]:
    """Return a placeholder capability report (U3b fills real probes)."""
    healthy = mwt1.is_healthy()
    return {
        "node": mwt1.host_alias(),
        "address": mwt1.host_address(),
        "status": "healthy" if healthy else "unreachable_or_unimplemented",
        "capabilities": {
            # U3b: ssh, job_root_writable, ffmpeg, python_image, cuda, blender, colmap
        },
        "notes": (
            "U2 selection interface only. Full MWT1 SSH capability probes "
            "and remediation text land in U3b."
        ),
    }
