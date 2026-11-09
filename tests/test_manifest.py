"""Subject manifest schema + loader tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from composite3dgen.manifest import ManifestError, load_manifest, validate_manifest


def test_schema_path_exists() -> None:
    from composite3dgen.manifest import schema_path

    assert schema_path().is_file()


def test_load_valid_manifest(tmp_path: Path) -> None:
    path = tmp_path / "subject.manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "subject_id": "demo",
                "domain": "glm",
                "capture": {"source_type": "photos", "media_paths": ["photos"]},
            }
        ),
        encoding="utf-8",
    )
    manifest = load_manifest(path)
    assert manifest.subject_id == "demo"
    assert manifest.domain == "glm"
    assert "front" in manifest.angles_required


def test_reject_missing_front_in_required(tmp_path: Path) -> None:
    data = {
        "schema_version": "1.0.0",
        "subject_id": "demo",
        "domain": "generic",
        "capture": {"source_type": "frames"},
        "angles": {"required": ["left", "back", "right"]},
    }
    errors = validate_manifest(data)
    assert any("front" in e for e in errors)


def test_load_invalid_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": "1.0.0"}), encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)
