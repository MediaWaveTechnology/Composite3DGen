"""Orchestrate silhouette + BOM QA gates and emit miss reasons (U7)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from composite3dgen.qa.bom import BomCompletenessResult, BomTier, check_bom_completeness
from composite3dgen.qa.ledger import (
    CostLedger,
    LOCAL_PIPELINE_STAGES,
    build_ledger_from_provider_jobs,
    write_ledger,
)
from composite3dgen.qa.miss import QAMiss
from composite3dgen.qa.promote import PromoteDecision, promote_from_misses
from composite3dgen.qa.silhouette import (
    SilhouetteGateResult,
    SilhouetteSource,
    discover_silhouette_pairs,
    run_silhouette_gate,
)


@dataclass
class QAGateReport:
    """Full QA gate report for a job (silhouette + BOM + promote + ledger)."""

    job_dir: Path
    subject_id: str | None
    passed: bool
    silhouette: SilhouetteGateResult | None = None
    bom: BomCompletenessResult | None = None
    misses: list[QAMiss] = field(default_factory=list)
    promote: list[PromoteDecision] = field(default_factory=list)
    ledger: CostLedger | None = None
    report_path: Path | None = None
    ledger_path: Path | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "kind": "qa_gate_report",
            "job_dir": str(self.job_dir),
            "subject_id": self.subject_id,
            "passed": self.passed,
            "silhouette": self.silhouette.as_dict() if self.silhouette else None,
            "bom": self.bom.as_dict() if self.bom else None,
            "misses": [m.as_dict() for m in self.misses],
            "promote": [p.as_dict() for p in self.promote],
            "ledger": self.ledger.as_dict() if self.ledger else None,
            "report_path": str(self.report_path) if self.report_path else None,
            "ledger_path": str(self.ledger_path) if self.ledger_path else None,
            "notes": list(self.notes),
        }


def _load_provider_jobs(job_dir: Path) -> list[dict[str, Any]]:
    path = job_dir / "manifests" / "provider_jobs.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    jobs = data.get("jobs") or []
    return [j for j in jobs if isinstance(j, dict)]


def _resolve_hierarchy_path(job_dir: Path, hierarchy_path: Path | None) -> Path | None:
    if hierarchy_path is not None:
        return Path(hierarchy_path)
    candidates = [
        job_dir / "out" / "blender" / "parts.json",
        job_dir / "staging" / "qm1-assembly.json",
        job_dir / "staging" / "parts-hierarchy.l1l2.json",
        job_dir / "staging" / "parts.hierarchy.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _subject_id_from_job(job_dir: Path) -> str | None:
    try:
        from composite3dgen.pipeline import resolve_manifest

        return resolve_manifest(job_dir).subject_id
    except Exception:  # noqa: BLE001
        return job_dir.name


def run_qa_gates(
    job_dir: Path,
    *,
    hierarchy_path: Path | None = None,
    required_bom_tier: BomTier = "L2",
    silhouette_pairs: Sequence[tuple[str, SilhouetteSource, SilhouetteSource]] | None = None,
    skip_silhouette: bool = False,
    skip_bom: bool = False,
    known_scene_meshes: Sequence[str] | None = None,
    require_cad_for_leaf: bool = False,
    leaf_cad_allowed: bool | None = None,
    iou_threshold: float = 0.55,
    coverage_threshold: float = 0.70,
    spend: bool = False,
    prefer_local: bool = True,
    extra_misses: Sequence[QAMiss] = (),
    local_stages_present: Sequence[str] | None = None,
    write: bool = True,
) -> QAGateReport:
    """Run silhouette + BOM gates; write report + cost ledger under manifests/."""
    job_dir = Path(job_dir)
    notes: list[str] = ["U7 QA gates: silhouette overlay + BOM completeness + cost ledger."]
    subject_id = _subject_id_from_job(job_dir)
    misses: list[QAMiss] = list(extra_misses)

    silhouette: SilhouetteGateResult | None = None
    if skip_silhouette:
        notes.append("Silhouette gate skipped.")
    else:
        pairs: list[tuple[str, SilhouetteSource, SilhouetteSource]]
        if silhouette_pairs is not None:
            pairs = list(silhouette_pairs)
        else:
            pairs = list(discover_silhouette_pairs(job_dir))  # type: ignore[arg-type]
            if not pairs:
                notes.append(
                    "No silhouette reference/candidate pairs found under job "
                    "(verification/reference-silhouette-* + out/blender/verification). "
                    "Silhouette gate skipped — provide pairs or stills for scoring."
                )
        if silhouette_pairs is not None or pairs:
            if not pairs and silhouette_pairs is not None:
                silhouette = run_silhouette_gate(
                    [],
                    iou_threshold=iou_threshold,
                    coverage_threshold=coverage_threshold,
                )
            elif pairs:
                silhouette = run_silhouette_gate(
                    pairs,
                    iou_threshold=iou_threshold,
                    coverage_threshold=coverage_threshold,
                )
            if silhouette is not None and not silhouette.passed:
                detail = "; ".join(s.detail for s in silhouette.scores if not s.passed)
                misses.append(
                    QAMiss(
                        kind="silhouette",
                        detail=detail or "silhouette coverage/IoU below threshold",
                        stage="qa_silhouette",
                    )
                )
            notes.extend(silhouette.notes if silhouette else [])

    bom: BomCompletenessResult | None = None
    if skip_bom:
        notes.append("BOM completeness gate skipped.")
    else:
        hier_path = _resolve_hierarchy_path(job_dir, hierarchy_path)
        if hier_path is None:
            bom = BomCompletenessResult(
                required_tier=required_bom_tier,
                claimed_tier=None,
                passed=False,
                issues=(),
                notes=("No parts hierarchy found for BOM gate.",),
            )
            # Represent as a synthetic fail via miss
            misses.append(
                QAMiss(
                    kind="bom_completeness",
                    detail="No parts.json / staging hierarchy found",
                    stage="qa_bom",
                )
            )
            notes.append("BOM gate FAIL: hierarchy missing.")
        else:
            bom = check_bom_completeness(
                hier_path,
                required_tier=required_bom_tier,
                require_cad_for_leaf=require_cad_for_leaf,
                leaf_cad_allowed=leaf_cad_allowed,
                known_scene_meshes=known_scene_meshes,
            )
            notes.append(f"BOM hierarchy: {hier_path}")
            notes.extend(bom.notes)
            if not bom.passed:
                detail = "; ".join(
                    i.message for i in bom.issues if i.severity == "fail"
                )
                misses.append(
                    QAMiss(
                        kind="bom_completeness",
                        detail=detail,
                        stage="qa_bom",
                    )
                )

    sil_ok = True if silhouette is None else silhouette.passed
    bom_ok = True if bom is None else bom.passed
    # When silhouette skipped with no pairs, do not fail overall on silhouette alone.
    if skip_silhouette:
        sil_ok = True
    if skip_bom:
        bom_ok = True
    # Missing hierarchy already added miss and bom.passed=False
    passed = sil_ok and bom_ok and not any(
        m.kind in ("silhouette", "bom_completeness") for m in misses
    )
    # Recompute: passed iff no silhouette/bom misses from this run
    gate_miss_kinds = {m.kind for m in misses if m.stage in ("qa_silhouette", "qa_bom")}
    passed = "silhouette" not in gate_miss_kinds and "bom_completeness" not in gate_miss_kinds
    if skip_silhouette and skip_bom:
        passed = True

    promote = promote_from_misses(
        misses,
        spend=spend,
        prefer_local=prefer_local,
        qa_passed=passed,
    )

    # Cost ledger: fold provider jobs + ensure local $0 stages.
    provider_jobs = _load_provider_jobs(job_dir)
    present = list(local_stages_present) if local_stages_present is not None else None
    if present is None:
        # Infer which local stages look present from job tree.
        inferred: list[str] = []
        if (job_dir / "frames").exists():
            inferred.append("ingest")
        if (job_dir / "manifests" / "frame_quality.json").is_file():
            inferred.append("quality")
        if (job_dir / "build_packs").exists():
            inferred.extend(["composites", "build_packs"])
        if any(
            j.get("provider") == "triposr" for j in provider_jobs
        ) or (job_dir / "out" / "triposr").exists():
            inferred.append("triposr")
        if (job_dir / "out" / "colmap").exists() or (job_dir / "out" / "meshroom").exists():
            inferred.append("photogrammetry")
        if (job_dir / "out" / "blender").exists():
            inferred.append("blender_explode")
        if silhouette is not None:
            inferred.append("qa_silhouette")
        if bom is not None:
            inferred.append("qa_bom")
        present = inferred

    ledger = build_ledger_from_provider_jobs(
        provider_jobs,
        subject_id=subject_id,
        spend_authorized=spend,
        qa_miss_kinds=[m.kind for m in misses],
        include_local_pipeline=True,
        local_stages_present=present,
    )
    # Guarantee every canonical local stage appears (skipped at $0 if absent).
    from composite3dgen.qa.ledger import ensure_local_pipeline_zeros

    ensure_local_pipeline_zeros(ledger, present_stages=present)

    report = QAGateReport(
        job_dir=job_dir,
        subject_id=subject_id,
        passed=passed,
        silhouette=silhouette,
        bom=bom,
        misses=misses,
        promote=promote,
        ledger=ledger,
        notes=notes,
    )

    if write:
        manifests = job_dir / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        report.report_path = manifests / "qa_gate_report.json"
        report.report_path.write_text(
            json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        report.ledger_path = write_ledger(manifests / "cost_ledger.json", ledger)
        # Also write miss reasons for --qa-miss / router consumption
        misses_path = manifests / "qa_misses.json"
        misses_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "passed": passed,
                    "misses": [m.as_dict() for m in misses],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return report


def load_misses_file(path: Path | str) -> list[QAMiss]:
    """Load QA misses previously written by :func:`run_qa_gates`."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    misses: list[QAMiss] = []
    for raw in data.get("misses") or []:
        if not isinstance(raw, Mapping):
            continue
        kind = raw.get("kind")
        if not isinstance(kind, str):
            continue
        misses.append(
            QAMiss(
                kind=kind,  # type: ignore[arg-type]
                detail=str(raw.get("detail") or ""),
                stage=raw.get("stage"),
            )
        )
    return misses


__all__ = [
    "LOCAL_PIPELINE_STAGES",
    "QAGateReport",
    "load_misses_file",
    "run_qa_gates",
]
