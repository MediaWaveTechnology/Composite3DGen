"""U6: dimension-register schema + RC DEX410 fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from composite3dgen.cad.register import (
    DimensionRegisterError,
    load_dimension_register,
    parse_dimension_register,
    schema_path,
    validate_dimension_register,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "rc-dex410" / "dimension-register.json"


def test_schema_file_exists() -> None:
    path = schema_path()
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["title"] == "DimensionRegister"
    assert data["properties"]["schema_version"]["const"] == "1.0.0"


def test_dex410_fixture_validates() -> None:
    assert FIXTURE.is_file()
    reg = load_dimension_register(FIXTURE)
    assert reg.subject_id == "rc-dex410"
    assert reg.domain == "rc"
    assert reg.profile == "dex410"
    assert reg.confirmed_count >= 1
    assert reg.leaf_fitment_allowed() is True
    assert any(m.mate_type for m in reg.mate_chain)


def test_confirmed_vs_inferred_required() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for entry in raw["entries"]:
        entry["confidence"] = "inferred"
    errors = validate_dimension_register(raw)
    assert any("inferred" in e and "confirmed" in e for e in errors)


def test_mate_dim_ref_must_exist() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["mate_chain"][0]["dim_ids"] = ["does-not-exist"]
    errors = validate_dimension_register(raw)
    assert any("does-not-exist" in e for e in errors)


def test_duplicate_dim_id_rejected() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["entries"].append(dict(raw["entries"][0]))
    with pytest.raises(DimensionRegisterError):
        parse_dimension_register(raw)


def test_handoff_notes_exclude_3ds_max_as_v1() -> None:
    """Preferences: Fusion-only for v1; 3ds Max later phase."""
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    notes = (raw.get("handoff") or {}).get("notes", "")
    assert "Fusion" in json.dumps(raw["handoff"])
    assert "3ds Max" in notes
    assert "later" in notes.lower()
