"""Resolve Blender binary paths without inventing verified locations.

Live paths come from MWT1 health facts or an explicit override. Until a
LAN / mwt1-worker probe records a path, callers must treat Blender as
``verify on LAN`` (see ``deploy/mwt1/README.md``).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from composite3dgen.nodes.health import VERIFY_ON_LAN
from composite3dgen.nodes.mwt1 import BLENDER_CANDIDATE_PATHS

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
) -> BlenderPathResolution:
    """Resolve Blender path from explicit override, health facts, or local which.

    Order:
    1. ``explicit`` if provided (caller-verified / test inject).
    2. ``health_facts['blender_path']`` when present and not a verify marker.
    3. Optional local ``shutil.which('blender')`` for controller dry/smoke only.
    4. Otherwise unresolved — ``verified=False``, display ``<verify on LAN>``.
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
                    "MWT1 happy path still needs LAN probe."
                ),
            )

    return BlenderPathResolution(
        path=None,
        verified=False,
        source="unresolved",
        candidates=candidates,
        note=(
            f"Blender path {UNVERIFIED}. Run `composite3dgen doctor --live` "
            "on LAN / mwt1 worker, or pass an explicit path. Do not invent paths."
        ),
    )


def package_script_path(name: str = "explode_hub.py") -> Path:
    """Return path to a Blender hub script shipped with the package."""
    path = Path(__file__).resolve().parent / "scripts" / name
    if not path.is_file():
        raise FileNotFoundError(f"Blender script missing: {path}")
    return path


__all__ = [
    "UNVERIFIED",
    "BlenderPathResolution",
    "package_script_path",
    "resolve_blender_path",
]
