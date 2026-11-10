"""Load and validate subject manifests against schema/subject.manifest.schema.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

CARDINAL_ANGLES = ("front", "left", "back", "right")
OPTIONAL_ANGLES = ("top", "iso")
ALL_ANGLES = CARDINAL_ANGLES + OPTIONAL_ANGLES
DEFAULT_REQUIRED = list(CARDINAL_ANGLES)
DEFAULT_OPTIONAL = list(OPTIONAL_ANGLES)


class ManifestError(ValueError):
    """Raised when a subject manifest is missing, invalid, or unreadable."""


def schema_path() -> Path:
    """Resolve the subject manifest JSON Schema on disk.

    Searches the repo ``schema/`` tree relative to this package and CWD so
    editable installs and checked-out worktrees both work.
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "schema" / "subject.manifest.schema.json",  # repo root
        Path.cwd() / "schema" / "subject.manifest.schema.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise ManifestError(
        "Could not locate schema/subject.manifest.schema.json "
        f"(tried: {', '.join(str(p) for p in candidates)})"
    )


def _load_schema() -> dict[str, Any]:
    path = schema_path()
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ManifestError(f"Schema root must be an object: {path}")
    return data


@dataclass(frozen=True)
class SubjectManifest:
    """Validated subject manifest (U2)."""

    schema_version: str
    subject_id: str
    domain: str
    capture: Mapping[str, Any]
    display_name: str | None = None
    units: str = "mm"
    known_dimensions: Mapping[str, Any] = field(default_factory=dict)
    angles_required: tuple[str, ...] = tuple(DEFAULT_REQUIRED)
    angles_optional: tuple[str, ...] = tuple(DEFAULT_OPTIONAL)
    angle_hints: Mapping[str, str] = field(default_factory=dict)
    reuse: Mapping[str, Any] = field(default_factory=dict)
    notes: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def source_type(self) -> str:
        return str(self.capture.get("source_type", "photos"))

    @property
    def media_paths(self) -> list[str]:
        paths = self.capture.get("media_paths") or []
        return [str(p) for p in paths]

    @property
    def frame_fps(self) -> float:
        value = self.capture.get("frame_fps", 2.0)
        return float(value)


def validate_manifest(data: Mapping[str, Any]) -> list[str]:
    """Return a list of validation error messages (empty if valid)."""
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(dict(data)), key=lambda e: list(e.path))
    messages: list[str] = []
    for err in errors:
        path = ".".join(str(p) for p in err.path) or "<root>"
        messages.append(f"{path}: {err.message}")

    # Front is always required regardless of angles.required overrides.
    angles = data.get("angles") or {}
    required = list(angles.get("required") or DEFAULT_REQUIRED)
    if "front" not in required:
        messages.append("angles.required: 'front' must be included (packs reject missing front)")
    return messages


def _from_mapping(data: Mapping[str, Any]) -> SubjectManifest:
    errors = validate_manifest(data)
    if errors:
        raise ManifestError("Invalid subject manifest:\n- " + "\n- ".join(errors))

    angles = data.get("angles") or {}
    required = tuple(angles.get("required") or DEFAULT_REQUIRED)
    optional = tuple(angles.get("optional") or DEFAULT_OPTIONAL)
    hints = dict(angles.get("hints") or {})

    return SubjectManifest(
        schema_version=str(data["schema_version"]),
        subject_id=str(data["subject_id"]),
        domain=str(data["domain"]),
        capture=dict(data["capture"]),
        display_name=data.get("display_name"),
        units=str(data.get("units") or "mm"),
        known_dimensions=dict(data.get("known_dimensions") or {}),
        angles_required=required,
        angles_optional=optional,
        angle_hints=hints,
        reuse=dict(data.get("reuse") or {}),
        notes=data.get("notes"),
        raw=dict(data),
    )


def load_manifest(path: Path | str) -> SubjectManifest:
    """Load and validate a subject manifest JSON file."""
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ManifestError(f"Manifest not found: {manifest_path}")
    try:
        with manifest_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifest JSON parse error in {manifest_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"Manifest root must be a JSON object: {manifest_path}")
    return _from_mapping(data)
