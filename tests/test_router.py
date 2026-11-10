"""Unit tests for the cost/quality router."""

from __future__ import annotations

from composite3dgen.providers.router import (
    gate_live_request,
    next_stages,
    plan_routes,
    route_stage,
)
from composite3dgen.qa.miss import QAMiss


def test_prefer_local_default_starts_with_triposr() -> None:
    plan = plan_routes(prefer_local=True, spend=False)
    assert plan.decisions
    assert plan.decisions[0].stage == "triposr"
    assert plan.decisions[0].mode == "local"
    assert plan.decisions[0].estimated_cost == 0.0


def test_cloud_without_spend_is_dry_run() -> None:
    decision = route_stage("tripo", prefer_local=True, spend=False)
    assert decision.mode == "dry-run"
    assert decision.allowed is True
    assert decision.block_reason is None


def test_spend_without_qa_miss_blocks_live_keeps_dry_run() -> None:
    decision = route_stage("tripo", prefer_local=True, spend=True, qa_misses=())
    assert decision.mode == "dry-run"
    assert decision.block_reason is not None
    assert "QA miss" in decision.block_reason or "prefer_local" in decision.block_reason


def test_spend_with_qa_miss_allows_live() -> None:
    misses = [QAMiss(kind="angle_coverage", detail="unseen rear")]
    decision = route_stage("tripo", prefer_local=True, spend=True, qa_misses=misses)
    assert decision.mode == "live"
    assert decision.block_reason is None


def test_no_prefer_local_with_spend_allows_live() -> None:
    decision = route_stage("hi3d", prefer_local=False, spend=True)
    assert decision.mode == "live"


def test_part_fidelity_suggests_tripo_or_bang() -> None:
    stages = next_stages(
        prefer_local=True,
        qa_misses=[QAMiss(kind="part_fidelity")],
    )
    assert "triposr" in stages
    assert "tripo" in stages or "rodin_bang" in stages


def test_gate_live_request_triposr_always_local() -> None:
    d = gate_live_request("triposr", spend=False)
    assert d.provider == "triposr"
    assert d.mode == "local"


def test_plan_explicit_stages() -> None:
    plan = plan_routes(
        prefer_local=True,
        spend=False,
        stages=["triposr", "rodin_bang", "hi3d"],
    )
    assert [d.stage for d in plan.decisions] == ["triposr", "rodin_bang", "hi3d"]
    assert plan.decisions[1].mode == "dry-run"
    assert plan.decisions[2].mode == "dry-run"
