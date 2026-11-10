"""Cost ledger — local stages $0; cloud via API ``consumed`` (U7).

Aggregates pipeline stages (ingest → packs → TripoSR → Blender → QA → cloud)
into a single job ledger. Local / dry-run stages are always recorded at
``consumed=0.0``. Live cloud records use adapter ``consumed`` when known.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from composite3dgen.providers.base import LOCAL_PROVIDERS, PAID_PROVIDERS

LedgerKind = Literal["local", "cloud", "presentation"]
LedgerStatus = Literal["planned", "dry-run", "succeeded", "failed", "blocked", "skipped"]

# Canonical local pipeline stages that must appear at $0 when the happy path runs.
LOCAL_PIPELINE_STAGES: tuple[str, ...] = (
    "ingest",
    "quality",
    "composites",
    "build_packs",
    "triposr",
    "photogrammetry",
    "blender_explode",
    "qa_silhouette",
    "qa_bom",
)


@dataclass
class LedgerEntry:
    """One cost-ledger row."""

    stage: str
    provider: str | None
    kind: LedgerKind
    consumed: float
    status: LedgerStatus
    currency: str = "USD"
    notes: str = ""
    job_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "provider": self.provider,
            "kind": self.kind,
            "consumed": self.consumed,
            "status": self.status,
            "currency": self.currency,
            "notes": self.notes,
            "job_id": self.job_id,
            "meta": dict(self.meta),
        }


@dataclass
class CostLedger:
    """Job-level cost ledger."""

    subject_id: str | None = None
    entries: list[LedgerEntry] = field(default_factory=list)
    spend_authorized: bool = False
    qa_miss_kinds: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def total_consumed(self) -> float:
        return float(sum(e.consumed for e in self.entries))

    @property
    def local_total(self) -> float:
        return float(sum(e.consumed for e in self.entries if e.kind == "local"))

    @property
    def cloud_total(self) -> float:
        return float(sum(e.consumed for e in self.entries if e.kind in ("cloud", "presentation")))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "kind": "cost_ledger",
            "subject_id": self.subject_id,
            "spend_authorized": self.spend_authorized,
            "qa_miss_kinds": list(self.qa_miss_kinds),
            "totals": {
                "local": self.local_total,
                "cloud": self.cloud_total,
                "all": self.total_consumed,
            },
            "entries": [e.as_dict() for e in self.entries],
            "notes": list(self.notes),
        }


def _kind_for(stage: str, provider: str | None) -> LedgerKind:
    if stage == "seedance" or provider == "seedance":
        return "presentation"
    if provider in PAID_PROVIDERS or stage in (
        "tripo",
        "hi3d",
        "rodin_bang",
        "rodin_gen25",
        "seedance",
    ):
        return "cloud"
    return "local"


def add_local_stage(
    ledger: CostLedger,
    stage: str,
    *,
    status: LedgerStatus = "succeeded",
    provider: str | None = None,
    notes: str = "",
    meta: Mapping[str, Any] | None = None,
) -> LedgerEntry:
    """Record a local / MWT1 stage at exactly $0."""
    entry = LedgerEntry(
        stage=stage,
        provider=provider,
        kind="local",
        consumed=0.0,
        status=status,
        notes=notes or "Local/MWT1 stage — $0.",
        meta=dict(meta or {}),
    )
    ledger.entries.append(entry)
    return entry


def add_provider_result(
    ledger: CostLedger,
    *,
    stage: str,
    provider: str,
    mode: str,
    consumed: float | None,
    status: str,
    job_id: str | None = None,
    notes: str = "",
    meta: Mapping[str, Any] | None = None,
) -> LedgerEntry:
    """Fold a provider job result into the ledger.

    Local and dry-run modes force ``consumed=0.0``. Live cloud uses API
    ``consumed`` when provided (else 0.0 with a note that API did not report).
    """
    kind = _kind_for(stage, provider)
    if mode in ("local", "dry-run") or provider in LOCAL_PROVIDERS:
        amount = 0.0
        kind = "local" if kind != "presentation" else kind
        if mode == "dry-run" and kind == "presentation":
            amount = 0.0
        elif mode == "dry-run":
            kind = "cloud" if provider in PAID_PROVIDERS else "local"
            amount = 0.0
    elif mode == "live" and provider in PAID_PROVIDERS:
        if consumed is None:
            amount = 0.0
            notes = (notes + " " if notes else "") + "Live job missing API consumed; recorded 0 pending invoice."
        else:
            amount = float(consumed)
        kind = "presentation" if provider == "seedance" else "cloud"
    else:
        amount = float(consumed or 0.0)

    # Normalize status labels
    status_map: dict[str, LedgerStatus] = {
        "succeeded": "succeeded",
        "failed": "failed",
        "dry_run": "dry-run",
        "blocked": "blocked",
        "pending": "planned",
        "queued": "planned",
        "running": "planned",
    }
    ledger_status = status_map.get(status, "planned")
    if mode == "dry-run" and ledger_status == "succeeded":
        ledger_status = "dry-run"

    entry = LedgerEntry(
        stage=stage,
        provider=provider,
        kind=kind,
        consumed=amount,
        status=ledger_status,
        notes=notes,
        job_id=job_id,
        meta=dict(meta or {}),
    )
    ledger.entries.append(entry)
    return entry


def ensure_local_pipeline_zeros(
    ledger: CostLedger,
    *,
    present_stages: Sequence[str] | None = None,
    mark_missing: LedgerStatus = "skipped",
) -> CostLedger:
    """Ensure canonical local pipeline stages appear with ``consumed=0``.

    Every name in ``LOCAL_PIPELINE_STAGES`` gets a row. Stages listed in
    ``present_stages`` (default: all canonical) are marked succeeded; others
    use ``mark_missing``. Existing rows for a stage are left in place but
    forced to ``consumed=0`` when ``kind=local``.
    """
    present_set = (
        set(present_stages)
        if present_stages is not None
        else set(LOCAL_PIPELINE_STAGES)
    )
    existing = {e.stage for e in ledger.entries}
    for entry in ledger.entries:
        if entry.kind == "local" and entry.consumed != 0.0:
            entry.consumed = 0.0
            entry.notes = (entry.notes + " " if entry.notes else "") + "Forced $0 local."

    for stage in LOCAL_PIPELINE_STAGES:
        if stage in existing:
            continue
        status: LedgerStatus = "succeeded" if stage in present_set else mark_missing
        add_local_stage(
            ledger,
            stage,
            status=status,
            notes="Local pipeline stage — $0 (U7 ledger).",
        )
        existing.add(stage)
    return ledger


def build_ledger_from_provider_jobs(
    jobs: Sequence[Mapping[str, Any]],
    *,
    subject_id: str | None = None,
    spend_authorized: bool = False,
    qa_miss_kinds: Sequence[str] = (),
    include_local_pipeline: bool = True,
    local_stages_present: Sequence[str] | None = None,
) -> CostLedger:
    """Build a cost ledger from provider job records (+ optional local zeros)."""
    ledger = CostLedger(
        subject_id=subject_id,
        spend_authorized=spend_authorized,
        qa_miss_kinds=list(qa_miss_kinds),
    )
    for job in jobs:
        provider = str(job.get("provider") or "unknown")
        stage = str(job.get("meta", {}).get("stage") or provider)
        # Normalize rodin ops
        if provider == "rodin":
            op = (job.get("meta") or {}).get("operation") or (job.get("options") or {}).get("operation")
            if op == "bang":
                stage = "rodin_bang"
            elif op in ("gen25", "gen-2.5", None) and stage == provider:
                stage = "rodin_gen25"
        add_provider_result(
            ledger,
            stage=stage,
            provider=provider,
            mode=str(job.get("mode") or "dry-run"),
            consumed=job.get("consumed"),
            status=str(job.get("status") or "dry_run"),
            job_id=job.get("job_id"),
            notes="; ".join(job.get("notes") or []) if isinstance(job.get("notes"), list) else str(job.get("notes") or ""),
            meta=dict(job.get("meta") or {}),
        )

    if include_local_pipeline:
        ensure_local_pipeline_zeros(
            ledger,
            present_stages=local_stages_present,
        )
        ledger.notes.append(
            "Local pipeline stages recorded at $0; cloud consumed from API fields."
        )
    return ledger


def write_ledger(path: Path | str, ledger: CostLedger) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger.as_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_ledger(path: Path | str) -> CostLedger:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    ledger = CostLedger(
        subject_id=data.get("subject_id"),
        spend_authorized=bool(data.get("spend_authorized")),
        qa_miss_kinds=list(data.get("qa_miss_kinds") or []),
        notes=list(data.get("notes") or []),
    )
    for raw in data.get("entries") or []:
        ledger.entries.append(
            LedgerEntry(
                stage=str(raw["stage"]),
                provider=raw.get("provider"),
                kind=raw.get("kind") or "local",  # type: ignore[arg-type]
                consumed=float(raw.get("consumed") or 0.0),
                status=raw.get("status") or "planned",  # type: ignore[arg-type]
                currency=str(raw.get("currency") or "USD"),
                notes=str(raw.get("notes") or ""),
                job_id=raw.get("job_id"),
                meta=dict(raw.get("meta") or {}),
            )
        )
    return ledger


__all__ = [
    "LOCAL_PIPELINE_STAGES",
    "CostLedger",
    "LedgerEntry",
    "add_local_stage",
    "add_provider_result",
    "build_ledger_from_provider_jobs",
    "ensure_local_pipeline_zeros",
    "load_ledger",
    "write_ledger",
]
