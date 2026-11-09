"""U5 dry-run E2E: packs → virtual providers → Blender hierarchy → checklist.

Never performs live paid cloud HTTP. Reuses recorded GLM/Tripo proofs when
present under the job fixture. Success = L1/L2 explode artifacts at $0 this run.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from composite3dgen.blender.jobs import BlenderExplodeResult, run_blender_explode
from composite3dgen.blender.schema import load_parts_hierarchy
from composite3dgen.manifest import SubjectManifest
from composite3dgen.nodes.executor import ExecutorName
from composite3dgen.pipeline import BuildPacksPipelineResult, resolve_manifest, run_build_packs
from composite3dgen.providers.base import PAID_PROVIDERS, JobStatus, ProviderJobResult
from composite3dgen.providers.router import plan_routes
from composite3dgen.providers.runner import ProviderRunResult, collect_pack_inputs, run_plan

ChecklistStatus = Literal["pass", "fail", "warn", "skip"]


@dataclass
class ChecklistItem:
    """One verification checklist row for dry-run E2E."""

    id: str
    label: str
    status: ChecklistStatus
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class DryRunE2EResult:
    """Aggregate outcome of a zero-spend dry-run E2E."""

    job_dir: Path
    subject_id: str
    packs: BuildPacksPipelineResult | None
    providers: ProviderRunResult | None
    explode: BlenderExplodeResult | None
    reused_records: list[Path] = field(default_factory=list)
    checklist: list[ChecklistItem] = field(default_factory=list)
    checklist_path: Path | None = None
    this_run_consumed: float = 0.0
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        if self.error:
            return False
        fails = [c for c in self.checklist if c.status == "fail"]
        return not fails

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "job_dir": str(self.job_dir),
            "subject_id": self.subject_id,
            "this_run_consumed": self.this_run_consumed,
            "reused_records": [str(p) for p in self.reused_records],
            "packs": self.packs.summary() if self.packs else None,
            "providers": self.providers.summary() if self.providers else None,
            "explode": self.explode.summary() if self.explode else None,
            "checklist": [c.as_dict() for c in self.checklist],
            "checklist_path": str(self.checklist_path) if self.checklist_path else None,
            "notes": list(self.notes),
            "error": self.error,
        }


def _fixture_paths(job_dir: Path) -> dict[str, Path]:
    return {
        "staging": job_dir / "staging" / "qm1-assembly.json",
        "parts_task": job_dir / "recorded" / "tripo" / "parts-task.json",
        "texture_task": job_dir / "recorded" / "tripo" / "texture-task.json",
        "media_refs": job_dir / "recorded" / "media-refs.json",
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def reuse_recorded_provider_proofs(
    job_dir: Path,
    manifest: SubjectManifest,
) -> tuple[list[Path], list[ProviderJobResult], list[str]]:
    """Copy recorded Tripo/provider proofs into ``out/<provider>/`` for dry-run.

    Historical ``consumed`` stays on the record for audit; this-run cost is 0.
    """
    notes: list[str] = []
    reused: list[Path] = []
    results: list[ProviderJobResult] = []

    prior = list((manifest.reuse or {}).get("prior_provider_outs") or [])
    # Always try canonical fixture paths even if manifest reuse is sparse.
    paths = _fixture_paths(job_dir)
    extras = [
        {"provider": "tripo", "path": str(paths["parts_task"].relative_to(job_dir))},
        {"provider": "tripo", "path": str(paths["texture_task"].relative_to(job_dir))},
    ]
    seen: set[str] = set()
    entries: list[Mapping[str, Any]] = []
    for entry in [*prior, *extras]:
        rel = str(entry.get("path") or "")
        if not rel or rel in seen:
            continue
        # Skip hierarchy docs — those feed Blender, not provider out/.
        if rel.endswith("qm1-assembly.json") or entry.get("provider") == "blender":
            continue
        seen.add(rel)
        entries.append(entry)

    for entry in entries:
        provider = str(entry.get("provider") or "tripo")
        rel = str(entry["path"])
        src = (job_dir / rel).resolve()
        if not src.is_file():
            notes.append(f"reuse miss: {rel}")
            continue
        try:
            data = _load_json(src)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            notes.append(f"reuse unreadable {rel}: {exc}")
            continue

        out_dir = job_dir / "out" / provider
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / src.name
        shutil.copy2(src, dest)
        reused.append(dest)

        # Stamp this-run cost zero while preserving historical consumed.
        stamped = dict(data)
        meta = dict(stamped.get("meta") or {})
        meta["recorded"] = True
        meta["this_run_consumed"] = 0.0
        meta["reused_from"] = rel
        stamped["meta"] = meta
        notes_list = list(stamped.get("notes") or [])
        notes_list.append("U5 dry-run reuse: no new cloud spend for this run.")
        stamped["notes"] = notes_list
        dest.write_text(json.dumps(stamped, indent=2) + "\n", encoding="utf-8")

        status_raw = str(stamped.get("status") or "succeeded")
        try:
            status = JobStatus(status_raw)
        except ValueError:
            status = JobStatus.SUCCEEDED

        results.append(
            ProviderJobResult(
                provider=provider,  # type: ignore[arg-type]
                job_id=str(stamped.get("job_id") or src.stem),
                status=status,
                mode="dry-run",
                artifacts=dict(stamped.get("artifacts") or {}),
                consumed=0.0,
                remote_task_id=stamped.get("remote_task_id"),
                notes=notes_list,
                meta=meta,
            )
        )
        notes.append(f"reused recorded proof → {dest.relative_to(job_dir)}")

    return reused, results, notes


def _resolve_staging_hierarchy(job_dir: Path, hierarchy_path: Path | None) -> Path | None:
    if hierarchy_path is not None:
        return Path(hierarchy_path)
    staging = job_dir / "staging" / "qm1-assembly.json"
    if staging.is_file():
        return staging
    # Generic fallback name
    alt = job_dir / "staging" / "parts.hierarchy.json"
    if alt.is_file():
        return alt
    return None


def _write_checklist(path: Path, items: Sequence[ChecklistItem], *, summary: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": "1.0.0",
        "kind": "dry_run_verification_checklist",
        "ok": all(i.status != "fail" for i in items),
        "items": [i.as_dict() for i in items],
        "summary": dict(summary),
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def _build_checklist(
    *,
    job_dir: Path,
    packs: BuildPacksPipelineResult | None,
    providers: ProviderRunResult | None,
    reused: Sequence[Path],
    reused_results: Sequence[ProviderJobResult],
    explode: BlenderExplodeResult | None,
    this_run_consumed: float,
    spend_requested: bool,
) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    items.append(
        ChecklistItem(
            id="no_spend",
            label="No --spend / zero this-run cloud consumed",
            status="fail" if spend_requested or this_run_consumed > 0 else "pass",
            detail=(
                f"spend_requested={spend_requested} this_run_consumed={this_run_consumed}"
            ),
        )
    )

    # Packs
    if packs is None:
        items.append(
            ChecklistItem(
                id="packs",
                label="Build packs with front cardinal",
                status="fail",
                detail="Packs stage did not run",
            )
        )
    else:
        front_ok = False
        for provider in packs.packs.providers:
            front = packs.packs.packs_root / provider / "front.jpg"
            if front.is_file():
                front_ok = True
                break
        items.append(
            ChecklistItem(
                id="packs",
                label="Build packs with front cardinal",
                status="pass" if front_ok else "fail",
                detail=(
                    f"providers={packs.packs.providers} "
                    f"angles={sorted(packs.selection.angles)}"
                ),
            )
        )

    # Virtual providers
    virtual_ok = True
    detail_bits: list[str] = []
    if providers is not None:
        for job in providers.results:
            detail_bits.append(f"{job.provider}:{job.mode}:{job.status.value}")
            if job.mode == "live" and job.provider in PAID_PROVIDERS:
                virtual_ok = False
            if (job.consumed or 0) > 0 and job.mode != "dry-run":
                # Live spend in this run
                if job.provider in PAID_PROVIDERS and job.mode == "live":
                    virtual_ok = False
        # All provider modes should be dry-run (or local triposr virtualized)
        if any(j.mode == "live" and j.provider in PAID_PROVIDERS for j in providers.results):
            virtual_ok = False
    items.append(
        ChecklistItem(
            id="virtual_providers",
            label="Provider jobs are virtual / dry-run (no live paid HTTP)",
            status="pass" if providers is not None and virtual_ok else "fail",
            detail="; ".join(detail_bits) or "no provider jobs",
        )
    )

    items.append(
        ChecklistItem(
            id="reuse_recorded",
            label="Recorded GLM/Tripo proofs reused",
            status="pass" if reused else "warn",
            detail=(
                f"{len(reused)} record(s): "
                + ", ".join(str(p.relative_to(job_dir)) for p in reused[:6])
                if reused
                else "no recorded proofs found under recorded/ or reuse.prior_provider_outs"
            ),
        )
    )

    # Blender L1/L2
    if explode is None or not explode.ok or explode.parts_path is None:
        items.append(
            ChecklistItem(
                id="blender_l1_l2",
                label="Blender hierarchy L1/L2 parts.json",
                status="fail",
                detail=explode.error if explode else "explode stage missing",
            )
        )
    else:
        try:
            hier = load_parts_hierarchy(explode.parts_path)
            tier_ok = hier.tier in ("L1", "L2")
            has_l1 = any(p.level == "L1" for p in hier.parts)
            has_l2 = any(p.level == "L2" for p in hier.parts)
            ok = tier_ok and has_l1 and (hier.tier != "L2" or has_l2)
            items.append(
                ChecklistItem(
                    id="blender_l1_l2",
                    label="Blender hierarchy L1/L2 parts.json",
                    status="pass" if ok else "fail",
                    detail=(
                        f"tier={hier.tier} parts={len(hier.parts)} "
                        f"mode={explode.mode} path={explode.parts_path}"
                    ),
                )
            )
            # Staging source preferred for QM1 fixture
            src = hier.source
            items.append(
                ChecklistItem(
                    id="staging_not_dumptruck",
                    label="Hierarchy from staging / dry-run (not dump-truck stub)",
                    status="pass" if src in ("staging", "blender", "manual") else "warn",
                    detail=f"source={src}; notes={(hier.notes or '')[:160]}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            items.append(
                ChecklistItem(
                    id="blender_l1_l2",
                    label="Blender hierarchy L1/L2 parts.json",
                    status="fail",
                    detail=str(exc),
                )
            )

    # Verification artifacts (planned markers OK in dry-run)
    if explode is not None and explode.verification:
        items.append(
            ChecklistItem(
                id="verification_stills",
                label="Verification stills planned or written",
                status="pass",
                detail=f"{len(explode.verification)} path(s)",
            )
        )
    else:
        items.append(
            ChecklistItem(
                id="verification_stills",
                label="Verification stills planned or written",
                status="fail",
                detail="No verification paths on explode result",
            )
        )

    # Media refs present for large GLBs (external / LFS)
    media_refs = job_dir / "recorded" / "media-refs.json"
    items.append(
        ChecklistItem(
            id="media_refs",
            label="Large GLB media refs documented (no invented binary truth)",
            status="pass" if media_refs.is_file() else "warn",
            detail=str(media_refs.relative_to(job_dir)) if media_refs.is_file() else "missing",
        )
    )

    # Reused results should claim this_run_consumed 0
    bad_reuse = [
        r for r in reused_results if (r.meta or {}).get("this_run_consumed", 0) not in (0, 0.0)
    ]
    items.append(
        ChecklistItem(
            id="reuse_zero_cost",
            label="Reused proofs stamp this_run_consumed=0",
            status="pass" if not bad_reuse else "fail",
            detail=f"checked={len(reused_results)} bad={len(bad_reuse)}",
        )
    )

    return items


def run_dry_run_e2e(
    job_dir: Path,
    *,
    manifest_path: Path | None = None,
    hierarchy_path: Path | None = None,
    prefer_mwt1: bool = True,
    force_executor: ExecutorName | None = None,
    skip_packs: bool = False,
    stages: Sequence[str] | None = None,
    prefix: str = "local",
    spend_requested: bool = False,
) -> DryRunE2EResult:
    """Run full dry-run E2E. Refuses any spend path (``spend_requested`` → error)."""
    job_dir = Path(job_dir)
    notes: list[str] = [
        "U5 dry-run E2E: packs → virtual providers → Blender → checklist.",
        "No live paid cloud HTTP; reuse recorded GLM/Tripo proofs when present.",
    ]

    if spend_requested:
        return DryRunE2EResult(
            job_dir=job_dir,
            subject_id=job_dir.name,
            packs=None,
            providers=None,
            explode=None,
            error=(
                "dry-run refuses --spend. Use `composite3dgen run --spend` only when "
                "authorizing live cloud (U7 QA gates). U5 success is zero new spend."
            ),
            notes=notes,
        )

    try:
        manifest = resolve_manifest(job_dir, manifest_path)
    except Exception as exc:  # noqa: BLE001
        return DryRunE2EResult(
            job_dir=job_dir,
            subject_id=job_dir.name,
            packs=None,
            providers=None,
            explode=None,
            error=f"Manifest resolve failed: {exc}",
            notes=notes,
        )

    subject_id = manifest.subject_id
    packs: BuildPacksPipelineResult | None = None
    if not skip_packs:
        try:
            packs = run_build_packs(
                job_dir,
                manifest_path=manifest_path,
                prefer_mwt1=prefer_mwt1,
                force_executor=force_executor,
            )
            notes.append(f"packs ok via executor={packs.executor.name}")
        except Exception as exc:  # noqa: BLE001
            return DryRunE2EResult(
                job_dir=job_dir,
                subject_id=subject_id,
                packs=None,
                providers=None,
                explode=None,
                error=f"Packs stage failed: {exc}",
                notes=notes,
            )
    else:
        notes.append("packs skipped (--skip-packs)")

    # Virtual provider ladder (always dry-run: spend=False).
    stage_list = list(stages) if stages else ["triposr", "tripo"]
    plan = plan_routes(
        prefer_local=prefer_mwt1,
        spend=False,
        qa_misses=[],
        stages=stage_list,  # type: ignore[arg-type]
    )
    # Force dry-run modes (belt + suspenders — plan_routes already does this).
    from composite3dgen.providers.router import RouteDecision

    safe_decisions = []
    for d in plan.decisions:
        if d.mode == "live" and d.provider in PAID_PROVIDERS:
            safe_decisions.append(
                RouteDecision(
                    stage=d.stage,
                    provider=d.provider,
                    mode="dry-run",
                    allowed=True,
                    block_reason="U5 dry-run: forced virtual (no --spend)",
                    estimated_cost=0.0,
                    prefer_local=d.prefer_local,
                    spend=False,
                    qa_misses=d.qa_misses,
                    notes=tuple([*d.notes, "Forced dry-run by U5 E2E"]),
                )
            )
        elif d.stage == "triposr" and d.mode == "local":
            # Cloud/controller agents: virtualize TripoSR (no MWT1).
            safe_decisions.append(
                RouteDecision(
                    stage=d.stage,
                    provider=d.provider,
                    mode="dry-run",
                    allowed=True,
                    block_reason="U5 dry-run: TripoSR virtualized (no live MWT1 invoke)",
                    estimated_cost=0.0,
                    prefer_local=d.prefer_local,
                    spend=False,
                    qa_misses=d.qa_misses,
                    notes=tuple([*d.notes, "TripoSR dry-run virtual job"]),
                )
            )
        else:
            safe_decisions.append(d)
    plan.decisions = safe_decisions

    inputs = collect_pack_inputs(job_dir, "triposr")
    providers = run_plan(plan, job_dir, subject_id=subject_id, inputs=inputs)

    reused_paths, reused_results, reuse_notes = reuse_recorded_provider_proofs(
        job_dir, manifest
    )
    notes.extend(reuse_notes)

    # Merge reused proofs into provider ledger for audit.
    if providers.ledger_path and providers.ledger_path.is_file():
        ledger = _load_json(providers.ledger_path)
        jobs = list(ledger.get("jobs") or [])
        jobs.extend([r.to_record() for r in reused_results])
        ledger["jobs"] = jobs
        ledger["reused_recorded"] = [str(p) for p in reused_paths]
        ledger["this_run_consumed"] = 0.0
        providers.ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")

    # Sum only this-run adapter consumed (should be 0); ignore historical on disk.
    this_run_consumed = 0.0
    for job in providers.results:
        if job.mode == "live" and job.provider in PAID_PROVIDERS:
            this_run_consumed += float(job.consumed or 0.0)
        elif job.mode in ("dry-run", "local"):
            this_run_consumed += 0.0
        else:
            this_run_consumed += float(job.consumed or 0.0)

    staging = _resolve_staging_hierarchy(job_dir, hierarchy_path)
    explode = run_blender_explode(
        job_dir,
        subject_id=subject_id,
        hierarchy_path=staging,
        prefer_mwt1=prefer_mwt1,
        force_executor=force_executor,
        prefix=prefix,
        allow_local_blender=False,
    )
    if staging is not None:
        notes.append(f"explode hierarchy: {staging.relative_to(job_dir)}")
    else:
        notes.append("explode hierarchy: synthetic L1/L2 (no staging file)")

    checklist = _build_checklist(
        job_dir=job_dir,
        packs=packs,
        providers=providers,
        reused=reused_paths,
        reused_results=reused_results,
        explode=explode,
        this_run_consumed=this_run_consumed,
        spend_requested=False,
    )
    checklist_path = _write_checklist(
        job_dir / "manifests" / "dry_run_checklist.json",
        checklist,
        summary={
            "subject_id": subject_id,
            "this_run_consumed": this_run_consumed,
            "explode_mode": explode.mode if explode else None,
            "parts_path": str(explode.parts_path) if explode and explode.parts_path else None,
            "tier": explode.hierarchy.tier if explode and explode.hierarchy else None,
        },
    )

    error = None
    if any(c.status == "fail" for c in checklist):
        failed = [c.id for c in checklist if c.status == "fail"]
        error = f"Dry-run checklist failed: {', '.join(failed)}"

    return DryRunE2EResult(
        job_dir=job_dir,
        subject_id=subject_id,
        packs=packs,
        providers=providers,
        explode=explode,
        reused_records=reused_paths,
        checklist=checklist,
        checklist_path=checklist_path,
        this_run_consumed=this_run_consumed,
        notes=notes,
        error=error,
    )


__all__ = [
    "ChecklistItem",
    "DryRunE2EResult",
    "reuse_recorded_provider_proofs",
    "run_dry_run_e2e",
]
