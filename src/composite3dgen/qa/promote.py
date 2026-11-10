"""Promote-to-hero policy (U7).

Rules for escalating from local draft → paid reconstruct → textured hero →
Seedance presentation. Seedance is **post-QA presentation only** — never a
geometry source and never authorized from a failing QA report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from composite3dgen.qa.miss import QAMiss, QAMissKind, summarize_misses

# Keep stage names as plain strings to avoid circular import with providers.router.
RouteStage = Literal[
    "triposr",
    "photogrammetry",
    "tripo",
    "hi3d",
    "rodin_bang",
    "rodin_gen25",
    "seedance",
]

# Mirror of providers.router.MISS_TO_STAGES (promote policy owns the doc surface).
MISS_TO_STAGES: dict[str, tuple[RouteStage, ...]] = {
    "angle_coverage": ("photogrammetry", "tripo", "hi3d"),
    "part_fidelity": ("tripo", "rodin_bang"),
    "hard_surface": ("rodin_gen25", "hi3d"),
    "texture": ("hi3d", "tripo"),
    "silhouette": ("tripo", "hi3d", "rodin_gen25"),
    "bom_completeness": ("tripo", "rodin_bang"),
    "operator_override": ("tripo", "hi3d", "rodin_bang", "rodin_gen25", "seedance"),
}

PromoteAction = Literal[
    "stop_local_ok",
    "reshoot_capture",
    "run_photogrammetry",
    "spend_tripo_multiview",
    "spend_hi3d_hero",
    "spend_rodin_bang",
    "spend_rodin_gen25",
    "cad_leaf_fitment",
    "seedance_presentation",
    "blocked_spend",
]


@dataclass(frozen=True)
class PromoteDecision:
    """One promote-to-hero policy decision."""

    action: PromoteAction
    allowed: bool
    reason: str
    requires_spend: bool = False
    requires_qa_pass: bool = False
    suggested_stages: tuple[RouteStage, ...] = ()
    qa_miss_kinds: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "allowed": self.allowed,
            "reason": self.reason,
            "requires_spend": self.requires_spend,
            "requires_qa_pass": self.requires_qa_pass,
            "suggested_stages": list(self.suggested_stages),
            "qa_miss_kinds": list(self.qa_miss_kinds),
        }


# Map miss kinds → preferred promote actions (ordered).
MISS_TO_ACTIONS: dict[QAMissKind, tuple[PromoteAction, ...]] = {
    "angle_coverage": ("run_photogrammetry", "spend_tripo_multiview", "spend_hi3d_hero"),
    "part_fidelity": ("spend_tripo_multiview", "spend_rodin_bang"),
    "hard_surface": ("spend_rodin_gen25", "spend_hi3d_hero"),
    "texture": ("spend_hi3d_hero", "spend_tripo_multiview"),
    "silhouette": ("spend_tripo_multiview", "spend_hi3d_hero", "spend_rodin_gen25"),
    "bom_completeness": ("spend_tripo_multiview", "spend_rodin_bang", "cad_leaf_fitment"),
    "operator_override": (
        "spend_tripo_multiview",
        "spend_hi3d_hero",
        "spend_rodin_bang",
        "spend_rodin_gen25",
    ),
}

ACTION_TO_STAGE: dict[PromoteAction, RouteStage | None] = {
    "stop_local_ok": None,
    "reshoot_capture": None,
    "run_photogrammetry": "photogrammetry",
    "spend_tripo_multiview": "tripo",
    "spend_hi3d_hero": "hi3d",
    "spend_rodin_bang": "rodin_bang",
    "spend_rodin_gen25": "rodin_gen25",
    "cad_leaf_fitment": None,
    "seedance_presentation": "seedance",
    "blocked_spend": None,
}


def assert_spend_authorized(
    *,
    spend: bool,
    prefer_local: bool = True,
    qa_misses: Sequence[QAMiss] = (),
) -> None:
    """Hard-block ``--spend`` without justifying QA miss reasons.

    Raises ``PermissionError`` when ``spend`` is requested under
    ``prefer_local`` with an empty miss list. ``--no-prefer-local`` with
    ``--spend`` is an explicit operator override and is allowed.
    """
    if not spend:
        return
    if not prefer_local:
        return
    if qa_misses:
        return
    raise PermissionError(
        "Refusing --spend: prefer_local=true requires recorded QA miss "
        "reason(s) (pass --qa-miss KIND, or --no-prefer-local to override). "
        "Run `composite3dgen qa` to produce miss kinds from silhouette/BOM gates."
    )


def seedance_allowed(*, qa_passed: bool, spend: bool) -> PromoteDecision:
    """Seedance is presentation-only after QA pass (+ spend for live)."""
    if not qa_passed:
        return PromoteDecision(
            action="seedance_presentation",
            allowed=False,
            reason=(
                "Seedance blocked: QA has not passed. Presentation is post-QA "
                "only and never a geometry source."
            ),
            requires_spend=True,
            requires_qa_pass=True,
            suggested_stages=(),
        )
    if not spend:
        return PromoteDecision(
            action="seedance_presentation",
            allowed=False,
            reason=(
                "Seedance dry-run only without --spend. Live presentation "
                "requires --spend after QA pass."
            ),
            requires_spend=True,
            requires_qa_pass=True,
            suggested_stages=("seedance",),
        )
    return PromoteDecision(
        action="seedance_presentation",
        allowed=True,
        reason="QA passed — Seedance presentation authorized (not geometry).",
        requires_spend=True,
        requires_qa_pass=True,
        suggested_stages=("seedance",),
    )


def promote_from_misses(
    misses: Sequence[QAMiss],
    *,
    spend: bool = False,
    prefer_local: bool = True,
    qa_passed: bool = False,
) -> list[PromoteDecision]:
    """Build ordered promote-to-hero decisions from QA misses / pass state."""
    decisions: list[PromoteDecision] = []

    if qa_passed and not misses:
        decisions.append(
            PromoteDecision(
                action="stop_local_ok",
                allowed=True,
                reason="QA passed on local draft — stop climbing the cost ladder.",
            )
        )
        decisions.append(seedance_allowed(qa_passed=True, spend=spend))
        return decisions

    if not misses:
        if spend and prefer_local:
            decisions.append(
                PromoteDecision(
                    action="blocked_spend",
                    allowed=False,
                    reason=(
                        "No QA miss reasons recorded — --spend hard-blocked under "
                        "prefer_local. Run QA gates or pass --qa-miss / --no-prefer-local."
                    ),
                    requires_spend=True,
                )
            )
        else:
            decisions.append(
                PromoteDecision(
                    action="stop_local_ok",
                    allowed=True,
                    reason="No QA misses — remain on local/MWT1 path ($0).",
                )
            )
        return decisions

    kinds = tuple(m.kind for m in misses)
    seen_actions: set[PromoteAction] = set()
    for miss in misses:
        for action in MISS_TO_ACTIONS.get(miss.kind, ()):
            if action in seen_actions:
                continue
            seen_actions.add(action)
            stage = ACTION_TO_STAGE.get(action)
            requires_spend = action.startswith("spend_") or action == "seedance_presentation"
            allowed = True
            reason = f"From QA miss {miss.kind}" + (f": {miss.detail}" if miss.detail else "")
            if requires_spend and not spend:
                allowed = False
                reason += " — needs --spend for live cloud (dry-run OK)."
            elif requires_spend and spend and prefer_local:
                # Spend already justified by misses in this branch.
                reason += " — live cloud justified by QA miss."
            decisions.append(
                PromoteDecision(
                    action=action,
                    allowed=allowed,
                    reason=reason,
                    requires_spend=requires_spend,
                    suggested_stages=(stage,) if stage else (),
                    qa_miss_kinds=kinds,
                )
            )

    # Seedance never from failing QA
    decisions.append(seedance_allowed(qa_passed=qa_passed, spend=spend))
    return decisions


def suggest_stages_for_promote(
    decisions: Sequence[PromoteDecision],
) -> list[RouteStage]:
    """Flatten allowed promote decisions into router stages."""
    stages: list[RouteStage] = []
    seen: set[RouteStage] = set()
    for decision in decisions:
        if not decision.allowed:
            continue
        for stage in decision.suggested_stages:
            if stage not in seen:
                stages.append(stage)
                seen.add(stage)
    # Also expand via miss→stage map for completeness
    for decision in decisions:
        for kind in decision.qa_miss_kinds:
            for stage in MISS_TO_STAGES.get(kind, ()):
                if stage not in seen and stage not in ("triposr",):
                    # Only add if some decision allowed a spend/photo path
                    if any(d.allowed and d.requires_spend for d in decisions) or stage == "photogrammetry":
                        if stage == "photogrammetry" or any(
                            d.allowed for d in decisions if stage in d.suggested_stages
                        ):
                            stages.append(stage)
                            seen.add(stage)
    return stages


def policy_summary() -> dict[str, Any]:
    """Static promote-to-hero policy document for CLI / docs sync."""
    return {
        "schema_version": "1.0.0",
        "kind": "promote_to_hero_policy",
        "rules": [
            "Local TripoSR + Blender QA first ($0 on MWT1).",
            "Climb cost ladder only after QA miss reasons are recorded.",
            "--spend hard-blocked under prefer_local without --qa-miss (or --no-prefer-local).",
            "Hero textured path: Hi3D quality/master or Tripo texture-on-parts after parts QA.",
            "Hard-surface hero: Rodin Gen-2.5 Extreme-High when drafts fail hard_surface.",
            "Split refine: Rodin Custom BANG on any GLB after part_fidelity / bom misses.",
            "RC leaf fitment: CadQuery + Fusion — never claim leaf from AI alone.",
            "Seedance: post-QA presentation only; never geometry; never from failing QA.",
        ],
        "miss_to_actions": {
            kind: list(actions) for kind, actions in MISS_TO_ACTIONS.items()
        },
    }


__all__ = [
    "ACTION_TO_STAGE",
    "MISS_TO_ACTIONS",
    "PromoteAction",
    "PromoteDecision",
    "assert_spend_authorized",
    "policy_summary",
    "promote_from_misses",
    "seedance_allowed",
    "suggest_stages_for_promote",
    "summarize_misses",
]
