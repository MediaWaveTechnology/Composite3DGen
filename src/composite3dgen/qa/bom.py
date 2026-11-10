"""BOM completeness gates (L1 / L2 / leaf) for U7.

AI parts ≠ engineering BOM. This gate checks hierarchy structure + mesh
assignment completeness against the claimed tier. Leaf claims additionally
require an explicit leaf tier and (for RC) CAD/register evidence when
``require_cad_for_leaf`` is set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from composite3dgen.blender.schema import (
    LEVEL_RANK,
    PartsHierarchy,
    PartsHierarchyError,
    load_parts_hierarchy,
    parse_parts_hierarchy,
)

BomTier = Literal["L1", "L2", "leaf"]


@dataclass(frozen=True)
class BomIssue:
    """One BOM completeness finding."""

    code: str
    message: str
    severity: Literal["fail", "warn"] = "fail"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "severity": self.severity}


@dataclass(frozen=True)
class BomCompletenessResult:
    """Outcome of a BOM completeness gate."""

    required_tier: BomTier
    claimed_tier: str | None
    passed: bool
    issues: tuple[BomIssue, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "required_tier": self.required_tier,
            "claimed_tier": self.claimed_tier,
            "passed": self.passed,
            "issues": [i.as_dict() for i in self.issues],
            "counts": dict(self.counts),
            "notes": list(self.notes),
        }


def _collect_mesh_assignments(hierarchy: PartsHierarchy) -> tuple[set[str], set[str], list[str]]:
    """Return (meshes_from_parts, meshes_from_bindings, anonymous_part_ids)."""
    from_parts: set[str] = set()
    anonymous: list[str] = []
    for part in hierarchy.parts:
        if not part.mesh_names:
            anonymous.append(part.part_id)
        for name in part.mesh_names:
            from_parts.add(name)
    from_bindings: set[str] = set()
    for binding in hierarchy.meshes:
        name = binding.get("mesh_name")
        if isinstance(name, str) and name:
            from_bindings.add(name)
    return from_parts, from_bindings, anonymous


def check_bom_completeness(
    hierarchy: PartsHierarchy | Mapping[str, Any] | Path | str,
    *,
    required_tier: BomTier = "L2",
    require_cad_for_leaf: bool = False,
    leaf_cad_allowed: bool | None = None,
    known_scene_meshes: Sequence[str] | None = None,
) -> BomCompletenessResult:
    """Evaluate BOM completeness for ``required_tier``.

    ``known_scene_meshes`` — optional list of mesh object names from a Blender
    scene / dry-run marker. Unassigned meshes fail the gate (anonymous dump).
    """
    notes: list[str] = []
    if isinstance(hierarchy, (Path, str)):
        try:
            hier = load_parts_hierarchy(hierarchy)
        except PartsHierarchyError as exc:
            return BomCompletenessResult(
                required_tier=required_tier,
                claimed_tier=None,
                passed=False,
                issues=(BomIssue(code="load_error", message=str(exc)),),
                notes=("Failed to load parts hierarchy.",),
            )
    elif isinstance(hierarchy, PartsHierarchy):
        hier = hierarchy
    else:
        try:
            hier = parse_parts_hierarchy(hierarchy)
        except PartsHierarchyError as exc:
            return BomCompletenessResult(
                required_tier=required_tier,
                claimed_tier=str(hierarchy.get("tier")) if isinstance(hierarchy, Mapping) else None,
                passed=False,
                issues=(BomIssue(code="parse_error", message=str(exc)),),
            )

    issues: list[BomIssue] = []
    l1 = [p for p in hier.parts if p.level == "L1"]
    l2 = [p for p in hier.parts if p.level == "L2"]
    leaf = [p for p in hier.parts if p.level == "leaf"]
    counts = {
        "parts": len(hier.parts),
        "L1": len(l1),
        "L2": len(l2),
        "leaf": len(leaf),
    }

    required_rank = LEVEL_RANK[required_tier]
    claimed_rank = LEVEL_RANK.get(hier.tier, 0)

    if claimed_rank < required_rank:
        issues.append(
            BomIssue(
                code="tier_too_shallow",
                message=(
                    f"Claimed tier '{hier.tier}' is shallower than required "
                    f"'{required_tier}'."
                ),
            )
        )

    if required_rank >= 1 and not l1:
        issues.append(
            BomIssue(
                code="missing_l1",
                message="No L1 assemblies present — required for L1/L2/leaf gates.",
            )
        )

    if required_rank >= 2 and not l2:
        issues.append(
            BomIssue(
                code="missing_l2",
                message="No L2 sub-assemblies present — required for L2/leaf gates.",
            )
        )

    if required_rank >= 3:
        if not leaf:
            issues.append(
                BomIssue(
                    code="missing_leaf",
                    message="Leaf tier required but no leaf nodes present.",
                )
            )
        if hier.tier != "leaf":
            issues.append(
                BomIssue(
                    code="leaf_tier_flag",
                    message="Leaf completeness requires claimed tier='leaf'.",
                )
            )
        if require_cad_for_leaf and not leaf_cad_allowed:
            issues.append(
                BomIssue(
                    code="leaf_cad_required",
                    message=(
                        "Leaf BOM claims for RC require CAD/dimension-register "
                        "evidence (CadQuery + confirmed dimensions). "
                        "AI parts alone are insufficient."
                    ),
                )
            )

    # Orphan L2 / leaf already caught by schema; still warn on empty mesh maps.
    from_parts, from_bindings, anonymous = _collect_mesh_assignments(hier)
    if anonymous:
        issues.append(
            BomIssue(
                code="empty_mesh_map",
                message=(
                    "Parts with no mesh_names (anonymous dump risk): "
                    + ", ".join(anonymous[:12])
                ),
            )
        )

    if known_scene_meshes is not None:
        known = {str(m) for m in known_scene_meshes}
        assigned = from_parts | from_bindings
        unassigned = sorted(known - assigned)
        if unassigned:
            issues.append(
                BomIssue(
                    code="unassigned_meshes",
                    message=(
                        "Scene meshes not assigned under BOM hierarchy: "
                        + ", ".join(unassigned[:20])
                    ),
                )
            )
        counts["scene_meshes"] = len(known)
        counts["unassigned_meshes"] = len(unassigned)
    else:
        notes.append(
            "No known_scene_meshes provided — mesh assignment checked via "
            "parts.mesh_names / meshes[] only."
        )

    # L2 completeness: every L1 should have ≥1 child when required_tier ≥ L2
    if required_rank >= 2 and l1:
        l1_ids = {p.part_id for p in l1}
        parents_with_kids = {p.parent_id for p in l2 if p.parent_id}
        barren = sorted(l1_ids - parents_with_kids)
        if barren:
            issues.append(
                BomIssue(
                    code="l1_without_l2",
                    message=(
                        "L1 assemblies with no L2 children: " + ", ".join(barren[:12])
                    ),
                    severity="warn" if required_tier == "L1" else "fail",
                )
            )

    fails = [i for i in issues if i.severity == "fail"]
    passed = not fails
    if passed:
        notes.append(f"BOM completeness OK for required_tier={required_tier}.")
    else:
        notes.append(
            "BOM completeness FAIL: " + "; ".join(i.code for i in fails)
        )

    return BomCompletenessResult(
        required_tier=required_tier,
        claimed_tier=hier.tier,
        passed=passed,
        issues=tuple(issues),
        counts=counts,
        notes=tuple(notes),
    )


__all__ = [
    "BomCompletenessResult",
    "BomIssue",
    "BomTier",
    "check_bom_completeness",
]
