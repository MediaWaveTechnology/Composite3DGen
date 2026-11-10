"""parts.hierarchy schema validation + loader tests (U4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from composite3dgen.blender.schema import (
    SCHEMA_VERSION,
    PartsHierarchyError,
    build_l1_l2_example,
    load_parts_hierarchy,
    parse_parts_hierarchy,
    schema_path,
    validate_parts_hierarchy,
    write_parts_hierarchy,
)


def test_schema_path_exists() -> None:
    path = schema_path()
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["title"] == "PartsHierarchy"
    assert data["properties"]["schema_version"]["const"] == SCHEMA_VERSION


def test_l1_l2_example_validates() -> None:
    hier = build_l1_l2_example("qm1")
    assert hier.tier == "L2"
    assert any(p.level == "L1" for p in hier.parts)
    assert any(p.level == "L2" for p in hier.parts)
    errors = validate_parts_hierarchy(hier.as_dict())
    assert errors == []


def test_leaf_supported_in_schema() -> None:
    data = build_l1_l2_example("rc1").as_dict()
    data["tier"] = "leaf"
    data["parts"].append(
        {
            "part_id": "bolt_01",
            "label": "Bolt 01",
            "level": "leaf",
            "parent_id": "sub_a1",
            "mesh_names": ["bolt_01_mesh"],
            "explode_offset": [0.0, 0.0, 0.1],
        }
    )
    data["meshes"].append({"mesh_name": "bolt_01_mesh", "part_id": "bolt_01"})
    hier = parse_parts_hierarchy(data)
    assert hier.tier == "leaf"
    assert any(p.level == "leaf" for p in hier.parts)


def test_reject_l2_without_parent() -> None:
    data = {
        "schema_version": SCHEMA_VERSION,
        "subject_id": "bad",
        "tier": "L2",
        "parts": [
            {
                "part_id": "orphan",
                "label": "Orphan",
                "level": "L2",
                "parent_id": None,
            }
        ],
    }
    errors = validate_parts_hierarchy(data)
    assert any("parent_id" in e for e in errors)


def test_reject_unknown_parent() -> None:
    data = {
        "schema_version": SCHEMA_VERSION,
        "subject_id": "bad",
        "tier": "L2",
        "parts": [
            {
                "part_id": "a",
                "label": "A",
                "level": "L1",
                "parent_id": None,
            },
            {
                "part_id": "b",
                "label": "B",
                "level": "L2",
                "parent_id": "missing",
            },
        ],
    }
    errors = validate_parts_hierarchy(data)
    assert any("missing" in e for e in errors)


def test_reject_tier_shallower_than_parts() -> None:
    data = build_l1_l2_example("x").as_dict()
    data["tier"] = "L1"
    errors = validate_parts_hierarchy(data)
    assert any("shallower" in e for e in errors)


def test_roundtrip_write_load(tmp_path: Path) -> None:
    hier = build_l1_l2_example("roundtrip")
    path = write_parts_hierarchy(tmp_path / "parts.json", hier)
    loaded = load_parts_hierarchy(path)
    assert loaded.subject_id == "roundtrip"
    assert loaded.tier == "L2"
    assert len(loaded.parts) == len(hier.parts)


def test_load_invalid_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8")
    with pytest.raises(PartsHierarchyError):
        load_parts_hierarchy(path)
