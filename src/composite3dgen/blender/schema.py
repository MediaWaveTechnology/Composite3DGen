"""Load and validate parts.hierarchy documents (U4 BOM schema)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

SCHEMA_VERSION = "1.0.0"
TIERS = ("L1", "L2", "leaf")
LEVEL_RANK = {"L1": 1, "L2": 2, "leaf": 3}


class PartsHierarchyError(ValueError):
    """Raised when a parts hierarchy document is missing or invalid."""


def schema_path() -> Path:
    """Resolve ``schema/parts.hierarchy.schema.json`` on disk."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "schema" / "parts.hierarchy.schema.json",
        Path.cwd() / "schema" / "parts.hierarchy.schema.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise PartsHierarchyError(
        "Could not locate schema/parts.hierarchy.schema.json "
        f"(tried: {', '.join(str(p) for p in candidates)})"
    )


def _load_schema() -> dict[str, Any]:
    path = schema_path()
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise PartsHierarchyError(f"Schema root must be an object: {path}")
    return data


def validate_parts_hierarchy(data: Mapping[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty when valid)."""
    validator = Draft202012Validator(_load_schema())
    errors = sorted(validator.iter_errors(dict(data)), key=lambda e: list(e.path))
    messages = [f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}" for err in errors]
    messages.extend(_semantic_errors(data))
    return messages


def _semantic_errors(data: Mapping[str, Any]) -> list[str]:
    """Extra checks beyond JSON Schema (parent links, tier consistency)."""
    msgs: list[str] = []
    parts = data.get("parts")
    if not isinstance(parts, list):
        return msgs

    ids: dict[str, dict[str, Any]] = {}
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        pid = part.get("part_id")
        if not isinstance(pid, str):
            continue
        if pid in ids:
            msgs.append(f"parts[{i}]: duplicate part_id '{pid}'")
        ids[pid] = part

    claimed = data.get("tier")
    deepest = 0
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        level = part.get("level")
        parent_id = part.get("parent_id", None)
        pid = part.get("part_id")
        if level in LEVEL_RANK:
            deepest = max(deepest, LEVEL_RANK[level])

        if level == "L1" and parent_id not in (None,):
            msgs.append(f"parts[{i}] ({pid}): L1 nodes must have parent_id null")
        if level in ("L2", "leaf") and parent_id is None:
            msgs.append(f"parts[{i}] ({pid}): {level} nodes require parent_id")
        if isinstance(parent_id, str) and parent_id not in ids:
            msgs.append(f"parts[{i}] ({pid}): parent_id '{parent_id}' not in parts")
        if isinstance(parent_id, str) and parent_id in ids:
            parent_level = ids[parent_id].get("level")
            if level == "L2" and parent_level != "L1":
                msgs.append(f"parts[{i}] ({pid}): L2 parent must be L1 (got {parent_level})")
            if level == "leaf" and parent_level not in ("L1", "L2"):
                msgs.append(
                    f"parts[{i}] ({pid}): leaf parent must be L1 or L2 (got {parent_level})"
                )

    meshes = data.get("meshes") or []
    if isinstance(meshes, list):
        for i, binding in enumerate(meshes):
            if not isinstance(binding, dict):
                continue
            part_id = binding.get("part_id")
            if isinstance(part_id, str) and part_id not in ids:
                msgs.append(f"meshes[{i}]: part_id '{part_id}' not in parts")

    if claimed in LEVEL_RANK and deepest and LEVEL_RANK[claimed] < deepest:
        msgs.append(
            f"tier '{claimed}' is shallower than deepest part level "
            f"({[k for k, v in LEVEL_RANK.items() if v == deepest][0]})"
        )
    if claimed in LEVEL_RANK and deepest and LEVEL_RANK[claimed] > deepest:
        msgs.append(
            f"tier '{claimed}' claims deeper than any part "
            f"(deepest present: {[k for k, v in LEVEL_RANK.items() if v == deepest][0]})"
        )
    return msgs


@dataclass(frozen=True)
class PartNode:
    """One BOM hierarchy node."""

    part_id: str
    label: str
    level: str
    parent_id: str | None = None
    mesh_names: tuple[str, ...] = ()
    explode_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    provider_part_ref: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "part_id": self.part_id,
            "label": self.label,
            "level": self.level,
            "parent_id": self.parent_id,
            "mesh_names": list(self.mesh_names),
            "explode_offset": list(self.explode_offset),
        }
        if self.provider_part_ref:
            doc["provider_part_ref"] = self.provider_part_ref
        if self.notes:
            doc["notes"] = self.notes
        return doc


@dataclass(frozen=True)
class PartsHierarchy:
    """Validated parts hierarchy document."""

    schema_version: str
    subject_id: str
    tier: str
    parts: tuple[PartNode, ...]
    source: str = "blender"
    units: str = "blender"
    explode: Mapping[str, Any] = field(default_factory=dict)
    meshes: tuple[dict[str, str], ...] = ()
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    notes: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "tier": self.tier,
            "source": self.source,
            "units": self.units,
            "parts": [p.as_dict() for p in self.parts],
        }
        if self.explode:
            doc["explode"] = dict(self.explode)
        if self.meshes:
            doc["meshes"] = [dict(m) for m in self.meshes]
        if self.artifacts:
            doc["artifacts"] = dict(self.artifacts)
        if self.notes:
            doc["notes"] = self.notes
        return doc


def _parse_part(raw: Mapping[str, Any]) -> PartNode:
    offset = raw.get("explode_offset") or [0.0, 0.0, 0.0]
    meshes = raw.get("mesh_names") or []
    return PartNode(
        part_id=str(raw["part_id"]),
        label=str(raw["label"]),
        level=str(raw["level"]),
        parent_id=raw.get("parent_id"),
        mesh_names=tuple(str(m) for m in meshes),
        explode_offset=(float(offset[0]), float(offset[1]), float(offset[2])),
        provider_part_ref=raw.get("provider_part_ref"),
        notes=raw.get("notes"),
    )


def parse_parts_hierarchy(data: Mapping[str, Any]) -> PartsHierarchy:
    """Validate and parse a parts hierarchy mapping."""
    errors = validate_parts_hierarchy(data)
    if errors:
        raise PartsHierarchyError(
            "Invalid parts hierarchy:\n- " + "\n- ".join(errors)
        )
    parts = tuple(_parse_part(p) for p in data["parts"])  # type: ignore[index]
    meshes_raw = data.get("meshes") or []
    meshes = tuple(
        {"mesh_name": str(m["mesh_name"]), "part_id": str(m["part_id"])}
        for m in meshes_raw
        if isinstance(m, dict)
    )
    return PartsHierarchy(
        schema_version=str(data["schema_version"]),
        subject_id=str(data["subject_id"]),
        tier=str(data["tier"]),
        parts=parts,
        source=str(data.get("source") or "blender"),
        units=str(data.get("units") or "blender"),
        explode=dict(data.get("explode") or {}),
        meshes=meshes,
        artifacts=dict(data.get("artifacts") or {}),
        notes=data.get("notes"),
        raw=dict(data),
    )


def load_parts_hierarchy(path: Path | str) -> PartsHierarchy:
    """Load and validate a parts.json / hierarchy document from disk."""
    path = Path(path)
    if not path.is_file():
        raise PartsHierarchyError(f"Parts hierarchy not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PartsHierarchyError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PartsHierarchyError(f"Parts hierarchy root must be an object: {path}")
    return parse_parts_hierarchy(data)


def write_parts_hierarchy(path: Path | str, hierarchy: PartsHierarchy | Mapping[str, Any]) -> Path:
    """Write a validated hierarchy document to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(hierarchy, PartsHierarchy):
        doc = hierarchy.as_dict()
    else:
        doc = dict(hierarchy)
        parse_parts_hierarchy(doc)  # validate
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def build_l1_l2_example(
    subject_id: str,
    *,
    l1: Sequence[tuple[str, str]] | None = None,
    l2: Sequence[tuple[str, str, str]] | None = None,
) -> PartsHierarchy:
    """Build a minimal L1/L2 hierarchy for dry-run / fixtures.

    ``l1``: ``(part_id, label)``; ``l2``: ``(part_id, label, parent_id)``.
    """
    l1_nodes = list(l1) if l1 is not None else [
        ("assembly_a", "Assembly A"),
        ("assembly_b", "Assembly B"),
    ]
    l2_nodes = list(l2) if l2 is not None else [
        ("sub_a1", "Sub A1", "assembly_a"),
        ("sub_b1", "Sub B1", "assembly_b"),
    ]
    parts: list[PartNode] = []
    for i, (pid, label) in enumerate(l1_nodes):
        ox = float((i + 1) * 0.5)
        parts.append(
            PartNode(
                part_id=pid,
                label=label,
                level="L1",
                parent_id=None,
                mesh_names=(f"{pid}_mesh",),
                explode_offset=(ox, 0.0, 0.0),
            )
        )
    for i, (pid, label, parent) in enumerate(l2_nodes):
        oy = float((i + 1) * 0.25)
        parts.append(
            PartNode(
                part_id=pid,
                label=label,
                level="L2",
                parent_id=parent,
                mesh_names=(f"{pid}_mesh",),
                explode_offset=(0.0, oy, 0.0),
            )
        )
    meshes = [
        {"mesh_name": name, "part_id": p.part_id}
        for p in parts
        for name in p.mesh_names
    ]
    return PartsHierarchy(
        schema_version=SCHEMA_VERSION,
        subject_id=subject_id,
        tier="L2",
        parts=tuple(parts),
        source="blender",
        units="blender",
        explode={"factor": 1.0, "mode": "offset"},
        meshes=tuple(meshes),
        artifacts={},
        notes="Synthetic L1/L2 hierarchy for dry-run / tests.",
    )


__all__ = [
    "LEVEL_RANK",
    "SCHEMA_VERSION",
    "TIERS",
    "PartNode",
    "PartsHierarchy",
    "PartsHierarchyError",
    "build_l1_l2_example",
    "load_parts_hierarchy",
    "parse_parts_hierarchy",
    "schema_path",
    "validate_parts_hierarchy",
    "write_parts_hierarchy",
]
