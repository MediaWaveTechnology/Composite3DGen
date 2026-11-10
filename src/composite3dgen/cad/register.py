"""Load and validate dimension.register documents (U6 RC domain profile)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

SCHEMA_VERSION = "1.0.0"
CONFIDENCE = ("confirmed", "inferred")


class DimensionRegisterError(ValueError):
    """Raised when a dimension register document is missing or invalid."""


def schema_path() -> Path:
    """Resolve ``schema/dimension.register.schema.json`` on disk."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "schema" / "dimension.register.schema.json",
        Path.cwd() / "schema" / "dimension.register.schema.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise DimensionRegisterError(
        "Could not locate schema/dimension.register.schema.json "
        f"(tried: {', '.join(str(p) for p in candidates)})"
    )


def _load_schema() -> dict[str, Any]:
    path = schema_path()
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise DimensionRegisterError(f"Schema root must be an object: {path}")
    return data


def validate_dimension_register(data: Mapping[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty when valid)."""
    validator = Draft202012Validator(_load_schema())
    errors = sorted(validator.iter_errors(dict(data)), key=lambda e: list(e.path))
    messages = [
        f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in errors
    ]
    messages.extend(_semantic_errors(data))
    return messages


def _semantic_errors(data: Mapping[str, Any]) -> list[str]:
    """Extra checks: unique ids, mate dim refs, leaf-claim guard."""
    msgs: list[str] = []
    entries = data.get("entries")
    if not isinstance(entries, list):
        return msgs

    dim_ids: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        dim_id = entry.get("dim_id")
        if isinstance(dim_id, str):
            if dim_id in dim_ids:
                msgs.append(f"entries[{i}]: duplicate dim_id '{dim_id}'")
            dim_ids.add(dim_id)
        conf = entry.get("confidence")
        if conf not in CONFIDENCE and conf is not None:
            msgs.append(f"entries[{i}]: confidence must be confirmed|inferred")

    mates = data.get("mate_chain") or []
    mate_ids: set[str] = set()
    if isinstance(mates, list):
        for i, mate in enumerate(mates):
            if not isinstance(mate, dict):
                continue
            mid = mate.get("mate_id")
            if isinstance(mid, str):
                if mid in mate_ids:
                    msgs.append(f"mate_chain[{i}]: duplicate mate_id '{mid}'")
                mate_ids.add(mid)
            for dim_ref in mate.get("dim_ids") or []:
                if isinstance(dim_ref, str) and dim_ref not in dim_ids:
                    msgs.append(
                        f"mate_chain[{i}]: dim_ids ref '{dim_ref}' not in entries"
                    )
            if mate.get("from_part") == mate.get("to_part"):
                msgs.append(
                    f"mate_chain[{i}]: from_part and to_part must differ"
                )

    # Guard: cannot claim leaf fitment if every dimension is inferred.
    if entries and all(
        isinstance(e, dict) and e.get("confidence") == "inferred" for e in entries
    ):
        msgs.append(
            "all entries are inferred — leaf fitment claims require at least "
            "one confirmed dimension (measure or datasheet)"
        )
    return msgs


@dataclass(frozen=True)
class DimensionEntry:
    dim_id: str
    label: str
    value: float
    confidence: str
    units: str | None = None
    axis: str = "other"
    part_ids: tuple[str, ...] = ()
    evidence: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class MateLink:
    mate_id: str
    from_part: str
    to_part: str
    mate_type: str
    confidence: str
    offset: float | None = None
    units: str | None = None
    dim_ids: tuple[str, ...] = ()
    notes: str | None = None


@dataclass
class DimensionRegister:
    """Parsed dimension register used by CadQuery / Fusion handoff."""

    schema_version: str
    subject_id: str
    domain: str
    units: str
    entries: list[DimensionEntry] = field(default_factory=list)
    mate_chain: list[MateLink] = field(default_factory=list)
    profile: str | None = None
    envelope: dict[str, Any] = field(default_factory=dict)
    bom_refs: list[dict[str, Any]] = field(default_factory=list)
    handoff: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def confirmed_count(self) -> int:
        return sum(1 for e in self.entries if e.confidence == "confirmed")

    @property
    def inferred_count(self) -> int:
        return sum(1 for e in self.entries if e.confidence == "inferred")

    def leaf_fitment_allowed(self) -> bool:
        """True when at least one confirmed dimension exists (U6 gate hint)."""
        return self.confirmed_count > 0

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "domain": self.domain,
            "units": self.units,
            "profile": self.profile,
            "entries": len(self.entries),
            "confirmed": self.confirmed_count,
            "inferred": self.inferred_count,
            "mate_chain": len(self.mate_chain),
            "leaf_fitment_allowed": self.leaf_fitment_allowed(),
        }


def parse_dimension_register(data: Mapping[str, Any]) -> DimensionRegister:
    """Validate and parse a register mapping into :class:`DimensionRegister`."""
    errors = validate_dimension_register(data)
    if errors:
        raise DimensionRegisterError(
            "Invalid dimension register:\n- " + "\n- ".join(errors)
        )
    entries: list[DimensionEntry] = []
    for e in data.get("entries") or []:
        if not isinstance(e, dict):
            continue
        entries.append(
            DimensionEntry(
                dim_id=str(e["dim_id"]),
                label=str(e["label"]),
                value=float(e["value"]),
                confidence=str(e["confidence"]),
                units=e.get("units"),
                axis=str(e.get("axis") or "other"),
                part_ids=tuple(e.get("part_ids") or ()),
                evidence=e.get("evidence"),
                notes=e.get("notes"),
            )
        )
    mates: list[MateLink] = []
    for m in data.get("mate_chain") or []:
        if not isinstance(m, dict):
            continue
        mates.append(
            MateLink(
                mate_id=str(m["mate_id"]),
                from_part=str(m["from_part"]),
                to_part=str(m["to_part"]),
                mate_type=str(m["mate_type"]),
                confidence=str(m["confidence"]),
                offset=float(m["offset"]) if m.get("offset") is not None else None,
                units=m.get("units"),
                dim_ids=tuple(m.get("dim_ids") or ()),
                notes=m.get("notes"),
            )
        )
    return DimensionRegister(
        schema_version=str(data["schema_version"]),
        subject_id=str(data["subject_id"]),
        domain=str(data["domain"]),
        units=str(data["units"]),
        entries=entries,
        mate_chain=mates,
        profile=data.get("profile"),
        envelope=dict(data.get("envelope") or {}),
        bom_refs=list(data.get("bom_refs") or []),
        handoff=dict(data.get("handoff") or {}),
        notes=data.get("notes"),
        raw=dict(data),
    )


def load_dimension_register(path: Path | str) -> DimensionRegister:
    """Load a dimension register JSON file from disk."""
    p = Path(path)
    if not p.is_file():
        raise DimensionRegisterError(f"Dimension register not found: {p}")
    with p.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise DimensionRegisterError(f"Register root must be an object: {p}")
    return parse_dimension_register(data)


def write_dimension_register(path: Path | str, data: Mapping[str, Any]) -> Path:
    """Validate and write a register document."""
    errors = validate_dimension_register(data)
    if errors:
        raise DimensionRegisterError(
            "Invalid dimension register:\n- " + "\n- ".join(errors)
        )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(data), indent=2) + "\n", encoding="utf-8")
    return out


def template_paths() -> Sequence[Path]:
    """Known fixture / template locations for RC DEX410."""
    here = Path(__file__).resolve()
    root = here.parents[3]
    return (
        root / "fixtures" / "rc-dex410" / "dimension-register.json",
        root / "fixtures" / "rc-dex410" / "templates" / "dimension-register.json",
    )
