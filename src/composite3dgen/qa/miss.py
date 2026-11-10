"""Minimal QA miss reason surface for the U3 cost router.

Full silhouette / BOM ledger lands in **U7**. U3 only needs structured miss
reasons so the router can authorize cloud promote steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

QAMissKind = Literal[
    "angle_coverage",
    "part_fidelity",
    "hard_surface",
    "texture",
    "silhouette",
    "bom_completeness",
    "operator_override",
]


@dataclass(frozen=True)
class QAMiss:
    """One recorded reason local draft/photogrammetry is insufficient."""

    kind: QAMissKind
    detail: str = ""
    stage: str | None = None  # e.g. "triposr", "blender_qa"

    def as_dict(self) -> dict[str, str | None]:
        return {"kind": self.kind, "detail": self.detail, "stage": self.stage}


def summarize_misses(misses: Iterable[QAMiss]) -> list[str]:
    return [f"{m.kind}" + (f": {m.detail}" if m.detail else "") for m in misses]
