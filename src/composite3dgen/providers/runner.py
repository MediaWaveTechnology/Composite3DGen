"""Execute a route plan: dry-run records virtual jobs; live/local call adapters."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from composite3dgen.providers.base import (
    JobStatus,
    ProviderJobRequest,
    ProviderJobResult,
)
from composite3dgen.providers.hi3d import Hi3DAdapter
from composite3dgen.providers.rodin import RodinAdapter
from composite3dgen.providers.router import RouteDecision, RoutePlan, RouteStage
from composite3dgen.providers.tripo import TripoAdapter
from composite3dgen.providers.triposr import TripoSRAdapter
from composite3dgen.providers.transport import HTTPTransport, RemoteFSTransport


@dataclass
class ProviderBundle:
    """Injectable adapter set for CLI / tests."""

    triposr: TripoSRAdapter = field(default_factory=TripoSRAdapter)
    tripo: TripoAdapter = field(default_factory=TripoAdapter)
    hi3d: Hi3DAdapter = field(default_factory=Hi3DAdapter)
    rodin: RodinAdapter = field(default_factory=RodinAdapter)


@dataclass
class ProviderRunResult:
    """Aggregate of virtual/live provider jobs for one CLI run."""

    plan: RoutePlan
    results: list[ProviderJobResult] = field(default_factory=list)
    ledger_path: Path | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "prefer_local": self.plan.prefer_local,
            "spend": self.plan.spend,
            "jobs": [r.to_record() for r in self.results],
            "ledger_path": str(self.ledger_path) if self.ledger_path else None,
        }


def _adapter_for(stage: RouteStage, bundle: ProviderBundle):
    if stage == "triposr":
        return bundle.triposr
    if stage == "tripo":
        return bundle.tripo
    if stage == "hi3d":
        return bundle.hi3d
    if stage in ("rodin_bang", "rodin_gen25"):
        return bundle.rodin
    return None


def _request_for(
    decision: RouteDecision,
    job_dir: Path,
    *,
    subject_id: str | None,
    inputs: dict[str, Any] | None,
) -> ProviderJobRequest:
    options: dict[str, Any] = {}
    if decision.stage == "rodin_bang":
        options["operation"] = "bang"
    elif decision.stage == "rodin_gen25":
        options["operation"] = "gen25"
    # Photogrammetry is U6 — record dry stub only via synthetic result below.
    return ProviderJobRequest(
        provider=decision.provider,
        job_dir=job_dir,
        inputs=dict(inputs or {}),
        mode=decision.mode,
        options=options,
        subject_id=subject_id,
    )


async def _run_decision(
    decision: RouteDecision,
    job_dir: Path,
    bundle: ProviderBundle,
    *,
    subject_id: str | None,
    inputs: dict[str, Any] | None,
) -> ProviderJobResult:
    if decision.stage == "photogrammetry":
        # U6 owns COLMAP/Meshroom execution; U3 records the routed intent.
        from composite3dgen.providers.base import new_job_id

        result = ProviderJobResult(
            provider="colmap",
            job_id=new_job_id("colmap"),
            status=JobStatus.DRY_RUN if decision.mode == "dry-run" else JobStatus.PENDING,
            mode=decision.mode if decision.mode != "live" else "local",
            consumed=0.0,
            notes=[
                "Photogrammetry stage reserved for U6 (COLMAP/Meshroom on MWT1).",
                *decision.notes,
            ],
            meta={"stage": decision.stage, "block_reason": decision.block_reason},
        )
        out = Path(job_dir) / "out" / "colmap"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{result.job_id}.json").write_text(
            json.dumps(result.to_record(), indent=2) + "\n", encoding="utf-8"
        )
        return result

    if decision.stage == "seedance":
        from composite3dgen.providers.base import new_job_id

        result = ProviderJobResult(
            provider="seedance",
            job_id=new_job_id("seedance"),
            status=JobStatus.DRY_RUN,
            mode="dry-run",
            consumed=0.0,
            notes=[
                "Seedance is post-QA presentation only — not invoked in U3 reconstruct.",
                *decision.notes,
            ],
            meta={"stage": decision.stage},
        )
        out = Path(job_dir) / "out" / "seedance"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{result.job_id}.json").write_text(
            json.dumps(result.to_record(), indent=2) + "\n", encoding="utf-8"
        )
        return result

    adapter = _adapter_for(decision.stage, bundle)
    if adapter is None:
        from composite3dgen.providers.base import new_job_id

        return ProviderJobResult(
            provider=decision.provider,
            job_id=new_job_id(decision.provider),
            status=JobStatus.FAILED,
            mode=decision.mode,
            error=f"No adapter wired for stage {decision.stage}",
        )

    # If router refused live (block_reason) keep dry-run even when spend was set.
    mode = decision.mode
    request = _request_for(decision, job_dir, subject_id=subject_id, inputs=inputs)
    request = ProviderJobRequest(
        provider=request.provider,
        job_dir=request.job_dir,
        inputs=request.inputs,
        mode=mode,
        options=request.options,
        subject_id=request.subject_id,
    )
    result = await adapter.run(request)
    if decision.block_reason:
        result.notes = [*result.notes, f"router: {decision.block_reason}"]
        result.meta = {**result.meta, "block_reason": decision.block_reason}
    return result


async def run_plan_async(
    plan: RoutePlan,
    job_dir: Path,
    *,
    subject_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    bundle: ProviderBundle | None = None,
) -> ProviderRunResult:
    """Execute all allowed decisions in the plan (sequential)."""
    bundle = bundle or ProviderBundle()
    results: list[ProviderJobResult] = []
    for decision in plan.decisions:
        if not decision.allowed:
            continue
        results.append(
            await _run_decision(
                decision,
                job_dir,
                bundle,
                subject_id=subject_id,
                inputs=inputs,
            )
        )

    ledger_dir = Path(job_dir) / "manifests"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "provider_jobs.json"
    doc = {
        "prefer_local": plan.prefer_local,
        "spend": plan.spend,
        "jobs": [r.to_record() for r in results],
    }
    ledger_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return ProviderRunResult(plan=plan, results=results, ledger_path=ledger_path)


def run_plan(
    plan: RoutePlan,
    job_dir: Path,
    *,
    subject_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    bundle: ProviderBundle | None = None,
) -> ProviderRunResult:
    """Sync wrapper around :func:`run_plan_async`."""
    return asyncio.run(
        run_plan_async(
            plan,
            job_dir,
            subject_id=subject_id,
            inputs=inputs,
            bundle=bundle,
        )
    )


def default_bundle(
    *,
    http: HTTPTransport | None = None,
    remote_fs: RemoteFSTransport | None = None,
    environ: dict[str, str] | None = None,
) -> ProviderBundle:
    """Build a ProviderBundle with optional injected transports (tests / U3b)."""
    triposr = TripoSRAdapter(transport=remote_fs) if remote_fs is not None else TripoSRAdapter()
    kwargs: dict[str, Any] = {}
    if http is not None:
        kwargs["transport"] = http
    if environ is not None:
        kwargs["environ"] = environ
    return ProviderBundle(
        triposr=triposr,
        tripo=TripoAdapter(**kwargs) if kwargs else TripoAdapter(),
        hi3d=Hi3DAdapter(**kwargs) if kwargs else Hi3DAdapter(),
        rodin=RodinAdapter(**kwargs) if kwargs else RodinAdapter(),
    )


def collect_pack_inputs(job_dir: Path, provider: str = "triposr") -> dict[str, Any]:
    """Load cardinal JPEGs from ``build_packs/<provider>/`` when present."""
    pack = Path(job_dir) / "build_packs" / provider
    images: dict[str, str] = {}
    inputs: dict[str, Any] = {"images": images}
    for angle in ("front", "left", "back", "right", "top", "iso"):
        path = pack / f"{angle}.jpg"
        if path.is_file():
            images[angle] = str(path)
            inputs[angle] = str(path)
    if "front" in images:
        inputs["image"] = images["front"]
    return inputs
