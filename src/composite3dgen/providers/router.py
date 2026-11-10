"""Cost × quality router — local first; cloud only after QA miss or --spend rules.

Rules (from playbook COST_QUALITY_MATRIX / U7):
1. ``prefer_local=true`` (default) — attempt MWT1/local free stages before cloud.
2. No ``--spend`` — refuse live Tripo / Hi3D / Rodin / Seedance; dry-run OK.
3. With ``--spend`` — CLI hard-blocks under prefer_local without QA miss reasons
   (``assert_spend_authorized``). Router still demotes unjustified live to
   dry-run + ``block_reason`` as a belt-and-suspenders guard.
4. TripoSR is single-image draft — not multi-view proof.
5. Seedance is post-QA presentation only (never geometry).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Sequence

from composite3dgen.providers.base import LOCAL_PROVIDERS, PAID_PROVIDERS, JobMode, ProviderName
from composite3dgen.qa.miss import QAMiss, summarize_misses

RouteStage = Literal[
    "triposr",
    "photogrammetry",
    "tripo",
    "hi3d",
    "rodin_bang",
    "rodin_gen25",
    "seedance",
]

# Approximate reference costs (USD or credits as documented in playbook).
ESTIMATED_COST: dict[str, float | None] = {
    "triposr": 0.0,
    "photogrammetry": 0.0,
    "tripo": 0.55,
    "hi3d": 0.90,
    "rodin_bang": 0.5,  # credits, not USD — recorded as numeric for ledger shape
    "rodin_gen25": 2.0,
    "seedance": None,
}

# Which QA miss kinds justify promoting to which cloud stage.
MISS_TO_STAGES: dict[str, tuple[RouteStage, ...]] = {
    "angle_coverage": ("photogrammetry", "tripo", "hi3d"),
    "part_fidelity": ("tripo", "rodin_bang"),
    "hard_surface": ("rodin_gen25", "hi3d"),
    "texture": ("hi3d", "tripo"),
    "silhouette": ("tripo", "hi3d", "rodin_gen25"),
    "bom_completeness": ("tripo", "rodin_bang"),
    "operator_override": ("tripo", "hi3d", "rodin_bang", "rodin_gen25", "seedance"),
}

STAGE_PROVIDER: dict[RouteStage, ProviderName] = {
    "triposr": "triposr",
    "photogrammetry": "colmap",
    "tripo": "tripo",
    "hi3d": "hi3d",
    "rodin_bang": "rodin",
    "rodin_gen25": "rodin",
    "seedance": "seedance",
}


@dataclass(frozen=True)
class RouteDecision:
    """Router output for one requested (or next) reconstruct stage."""

    stage: RouteStage
    provider: ProviderName
    mode: JobMode
    allowed: bool
    block_reason: str | None = None
    estimated_cost: float | None = None
    prefer_local: bool = True
    spend: bool = False
    qa_misses: tuple[QAMiss, ...] = ()
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "stage": self.stage,
            "provider": self.provider,
            "mode": self.mode,
            "allowed": self.allowed,
            "block_reason": self.block_reason,
            "estimated_cost": self.estimated_cost,
            "prefer_local": self.prefer_local,
            "spend": self.spend,
            "qa_misses": [m.as_dict() for m in self.qa_misses],
            "notes": list(self.notes),
        }


@dataclass
class RoutePlan:
    """Ordered ladder of decisions for a job."""

    decisions: list[RouteDecision] = field(default_factory=list)
    prefer_local: bool = True
    spend: bool = False

    def allowed(self) -> list[RouteDecision]:
        return [d for d in self.decisions if d.allowed]

    def as_dict(self) -> dict:
        return {
            "prefer_local": self.prefer_local,
            "spend": self.spend,
            "decisions": [d.as_dict() for d in self.decisions],
        }


def _miss_kinds(misses: Sequence[QAMiss]) -> set[str]:
    return {m.kind for m in misses}


def _cloud_justified(stage: RouteStage, misses: Sequence[QAMiss], *, prefer_local: bool) -> bool:
    """Return True when live cloud for ``stage`` is justified."""
    if not prefer_local:
        return True
    kinds = _miss_kinds(misses)
    if "operator_override" in kinds:
        return True
    for kind in kinds:
        if stage in MISS_TO_STAGES.get(kind, ()):
            return True
    return False


def route_stage(
    stage: RouteStage,
    *,
    prefer_local: bool = True,
    spend: bool = False,
    qa_misses: Sequence[QAMiss] = (),
) -> RouteDecision:
    """Decide mode/allowance for a single pipeline stage."""
    provider = STAGE_PROVIDER[stage]
    estimated = ESTIMATED_COST.get(stage)
    misses = tuple(qa_misses)
    notes: list[str] = []

    # Local free stages
    if provider in LOCAL_PROVIDERS or stage in ("triposr", "photogrammetry"):
        mode: JobMode = "local" if prefer_local else "local"
        notes.append("Local/MWT1 stage — $0; TripoSR is single-image draft only.")
        return RouteDecision(
            stage=stage,
            provider=provider,
            mode=mode,
            allowed=True,
            block_reason=None,
            estimated_cost=0.0,
            prefer_local=prefer_local,
            spend=spend,
            qa_misses=misses,
            notes=tuple(notes),
        )

    # Paid cloud stages
    assert provider in PAID_PROVIDERS or stage == "seedance"

    if not spend:
        notes.append("No --spend: recording dry-run virtual job only (no live HTTP).")
        return RouteDecision(
            stage=stage,
            provider=provider,
            mode="dry-run",
            allowed=True,
            block_reason=None,
            estimated_cost=estimated,
            prefer_local=prefer_local,
            spend=spend,
            qa_misses=misses,
            notes=tuple(notes),
        )

    # spend=True
    if not _cloud_justified(stage, misses, prefer_local=prefer_local):
        reason = (
            "Live cloud blocked: prefer_local=true and no justifying QA miss. "
            "Record a QA miss or pass --no-prefer-local with --spend."
        )
        if misses:
            reason += f" Current misses: {summarize_misses(misses)}"
        notes.append("Dry-run still allowed; live HTTP refused.")
        return RouteDecision(
            stage=stage,
            provider=provider,
            mode="dry-run",
            allowed=True,
            block_reason=reason,
            estimated_cost=estimated,
            prefer_local=prefer_local,
            spend=spend,
            qa_misses=misses,
            notes=tuple(notes),
        )

    notes.append("Live cloud authorized (--spend + QA miss or --no-prefer-local).")
    if misses:
        notes.append("QA misses: " + "; ".join(summarize_misses(misses)))
    return RouteDecision(
        stage=stage,
        provider=provider,
        mode="live",
        allowed=True,
        block_reason=None,
        estimated_cost=estimated,
        prefer_local=prefer_local,
        spend=spend,
        qa_misses=misses,
        notes=tuple(notes),
    )


def next_stages(
    *,
    prefer_local: bool = True,
    qa_misses: Sequence[QAMiss] = (),
) -> list[RouteStage]:
    """Suggest ordered stages to attempt given router policy + misses."""
    ladder: list[RouteStage] = []
    if prefer_local:
        ladder.append("triposr")
        kinds = _miss_kinds(qa_misses)
        if "angle_coverage" in kinds:
            ladder.append("photogrammetry")
    # Cloud promote suggestions from misses
    seen: set[RouteStage] = set(ladder)
    for miss in qa_misses:
        for stage in MISS_TO_STAGES.get(miss.kind, ()):
            if stage in ("triposr", "photogrammetry"):
                continue
            if stage not in seen:
                ladder.append(stage)
                seen.add(stage)
    if not qa_misses and not prefer_local:
        ladder.extend(["tripo", "hi3d"])
    return ladder


def plan_routes(
    *,
    prefer_local: bool = True,
    spend: bool = False,
    qa_misses: Sequence[QAMiss] = (),
    stages: Iterable[RouteStage] | None = None,
) -> RoutePlan:
    """Build a route plan for explicit stages or the policy ladder."""
    ordered = list(stages) if stages is not None else next_stages(
        prefer_local=prefer_local, qa_misses=qa_misses
    )
    if not ordered:
        ordered = ["triposr"]
    decisions = [
        route_stage(stage, prefer_local=prefer_local, spend=spend, qa_misses=qa_misses)
        for stage in ordered
    ]
    return RoutePlan(decisions=decisions, prefer_local=prefer_local, spend=spend)


def assert_live_allowed(decision: RouteDecision) -> None:
    """Raise if a caller attempts live mode that the router refused."""
    if decision.mode == "live" and decision.block_reason:
        raise PermissionError(decision.block_reason)
    if decision.mode == "live" and not decision.spend:
        raise PermissionError(
            f"Live mode for {decision.provider} requires --spend "
            "(secrets via env/Bitwarden only)."
        )


def gate_live_request(
    provider: str,
    *,
    spend: bool,
    prefer_local: bool = True,
    qa_misses: Sequence[QAMiss] = (),
    stage: RouteStage | None = None,
) -> RouteDecision:
    """CLI/helper gate: map a provider request to a RouteDecision.

    Blocks live paid calls without ``--spend``. With ``--spend`` but no QA miss
    (and prefer_local), returns dry-run + block_reason instead of live.
    """
    stage_map: dict[str, RouteStage] = {
        "triposr": "triposr",
        "colmap": "photogrammetry",
        "meshroom": "photogrammetry",
        "tripo": "tripo",
        "hi3d": "hi3d",
        "rodin": stage or "rodin_gen25",
        "seedance": "seedance",
    }
    resolved = stage or stage_map.get(provider)
    if resolved is None:
        raise ValueError(f"Unknown provider for routing: {provider}")
    return route_stage(
        resolved,
        prefer_local=prefer_local,
        spend=spend,
        qa_misses=qa_misses,
    )
