"""Resolve Blender binary paths without inventing unverified locations.

MWT1 preferred paths (verified in ``internal/mwt1-capability-probe.md``):

- ``/opt/homebrew/bin/blender`` (Blender 5.2.3 LTS via Homebrew)
- ``/Applications/Blender.app/Contents/MacOS/Blender`` (App bundle fallback)

Host is Apple M4 Metal — Blender explode/QA is fine; TripoSR CUDA is separate.
Other hosts / missing probe facts still use ``<verify on LAN>`` until resolved.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from composite3dgen.nodes.health import VERIFY_ON_LAN
from composite3dgen.nodes.mwt1 import (
    BLENDER_CANDIDATE_PATHS,
    MWT1_BLENDER_APP_PATH,
    MWT1_BLENDER_PATH,
    MWT1_BLENDER_PREFERRED,
    MWT1_BLENDER_VERSION,
)

# Marker for unresolved paths — never treat as a real binary.
UNVERIFIED = f"<{VERIFY_ON_LAN}>"


@dataclass(frozen=True)
class BlenderPathResolution:
    """Outcome of resolving a Blender binary for explode / QA jobs."""

    path: str | None
    verified: bool
    source: str
    candidates: tuple[str, ...]
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "verified": self.verified,
            "source": self.source,
            "candidates": list(self.candidates),
            "note": self.note,
            "display": self.path if self.verified and self.path else UNVERIFIED,
        }


def resolve_blender_path(
    *,
    explicit: str | Path | None = None,
    health_facts: Mapping[str, Any] | None = None,
    prefer_local_which: bool = False,
    prefer_mwt1_documented: bool = False,
) -> BlenderPathResolution:
    """Resolve Blender path from explicit override, health facts, or MWT1 docs.

    Order:
    1. ``explicit`` if provided (caller-verified / test inject).
    2. ``health_facts['blender_path']`` when present and not a verify marker.
    3. ``prefer_mwt1_documented`` → Homebrew then App bundle (probe-verified).
    4. Optional local ``shutil.which('blender')`` for controller dry/smoke only.
    5. Otherwise unresolved — ``verified=False``, display ``<verify on LAN>``.
    """
    candidates = tuple(BLENDER_CANDIDATE_PATHS)

    if explicit is not None:
        path = str(explicit)
        return BlenderPathResolution(
            path=path,
            verified=True,
            source="explicit",
            candidates=candidates,
            note="Caller-supplied Blender path (tests / operator override).",
        )

    if health_facts:
        raw = health_facts.get("blender_path")
        if isinstance(raw, str) and raw and VERIFY_ON_LAN not in raw and not raw.startswith("<"):
            return BlenderPathResolution(
                path=raw,
                verified=True,
                source="health_facts",
                candidates=candidates,
                note="From MWT1 health probe facts (LAN / mwt1 worker).",
            )

    if prefer_mwt1_documented:
        # Documented probe preference — Homebrew first, App bundle second.
        return BlenderPathResolution(
            path=MWT1_BLENDER_PATH,
            verified=True,
            source="mwt1_probe_docs",
            candidates=candidates,
            note=(
                f"MWT1 documented Blender {MWT1_BLENDER_VERSION}: "
                f"{MWT1_BLENDER_PATH} (prefer); fallback {MWT1_BLENDER_APP_PATH}. "
                "Apple M4 Metal — explode/QA OK; TripoSR CUDA is separate."
            ),
        )

    if prefer_local_which:
        found = shutil.which("blender")
        if found:
            return BlenderPathResolution(
                path=found,
                verified=True,
                source="local_which",
                candidates=candidates,
                note=(
                    "Local `which blender` — controller smoke only; "
                    "MWT1 happy path prefers Homebrew/App paths from probe."
                ),
            )

    return BlenderPathResolution(
        path=None,
        verified=False,
        source="unresolved",
        candidates=candidates,
        note=(
            f"Blender path {UNVERIFIED}. For MWT1 use "
            f"{MWT1_BLENDER_PATH} or {MWT1_BLENDER_APP_PATH} "
            f"(probe-verified {MWT1_BLENDER_VERSION}), or pass --live health facts."
        ),
    )


def package_script_path(name: str = "explode_hub.py") -> Path:
    """Return path to a Blender hub script shipped with the package."""
    path = Path(__file__).resolve().parent / "scripts" / name
    if not path.is_file():
        raise FileNotFoundError(f"Blender script missing: {path}")
    return path


__all__ = [
    "MWT1_BLENDER_APP_PATH",
    "MWT1_BLENDER_PATH",
    "MWT1_BLENDER_PREFERRED",
    "MWT1_BLENDER_VERSION",
    "UNVERIFIED",
    "BlenderPathResolution",
    "package_script_path",
    "resolve_blender_path",
]
