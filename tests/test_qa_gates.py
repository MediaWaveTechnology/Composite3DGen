"""U7: silhouette overlay, BOM completeness, spend hard-block, cost ledger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from composite3dgen.blender.schema import build_l1_l2_example, write_parts_hierarchy
from composite3dgen.cli import main
from composite3dgen.qa.bom import check_bom_completeness
from composite3dgen.qa.gates import run_qa_gates
from composite3dgen.qa.ledger import (
    LOCAL_PIPELINE_STAGES,
    build_ledger_from_provider_jobs,
    ensure_local_pipeline_zeros,
    CostLedger,
)
from composite3dgen.qa.miss import QAMiss
from composite3dgen.qa.promote import (
    assert_spend_authorized,
    promote_from_misses,
    seedance_allowed,
)
from composite3dgen.qa.silhouette import (
    run_silhouette_gate,
    score_silhouette_pair,
)


def _sil_image(
    path: Path,
    *,
    box: tuple[int, int, int, int],
    size: tuple[int, int] = (128, 128),
) -> Path:
    """Black silhouette on white background."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("L", size, 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle(box, fill=0)
    img.save(path)
    return path


def test_silhouette_matching_pair_passes(tmp_path: Path) -> None:
    ref = _sil_image(tmp_path / "ref.png", box=(30, 30, 90, 90))
    cand = _sil_image(tmp_path / "cand.png", box=(30, 30, 90, 90))
    score = score_silhouette_pair(ref, cand, axis="front")
    assert score.passed
    assert score.iou == pytest.approx(1.0)
    assert score.coverage == pytest.approx(1.0)


def test_failing_coverage_fails_silhouette_gate(tmp_path: Path) -> None:
    """Failing coverage/IoU fails the gate (U7 success criterion)."""
    ref = _sil_image(tmp_path / "ref.png", box=(20, 20, 100, 100))
    # Tiny candidate barely overlaps → low coverage
    cand = _sil_image(tmp_path / "cand.png", box=(70, 70, 90, 90))
    gate = run_silhouette_gate(
        [("front", ref, cand)],
        iou_threshold=0.55,
        coverage_threshold=0.70,
    )
    assert gate.passed is False
    assert "front" in gate.failed_axes
    assert gate.scores[0].coverage < 0.70


def test_bom_completeness_l2_ok(tmp_path: Path) -> None:
    hier = build_l1_l2_example("test-bom")
    path = write_parts_hierarchy(tmp_path / "parts.json", hier)
    result = check_bom_completeness(path, required_tier="L2")
    assert result.passed
    assert result.counts["L1"] >= 1
    assert result.counts["L2"] >= 1


def test_bom_unassigned_meshes_fail(tmp_path: Path) -> None:
    hier = build_l1_l2_example("test-bom")
    path = write_parts_hierarchy(tmp_path / "parts.json", hier)
    result = check_bom_completeness(
        path,
        required_tier="L2",
        known_scene_meshes=["assembly_a_mesh", "orphan_dump_mesh"],
    )
    assert result.passed is False
    codes = {i.code for i in result.issues}
    assert "unassigned_meshes" in codes


def test_bom_leaf_requires_cad_when_flagged(tmp_path: Path) -> None:
    # Build L2 only — leaf required → fail
    hier = build_l1_l2_example("test-leaf")
    path = write_parts_hierarchy(tmp_path / "parts.json", hier)
    result = check_bom_completeness(
        path,
        required_tier="leaf",
        require_cad_for_leaf=True,
        leaf_cad_allowed=False,
    )
    assert result.passed is False
    codes = {i.code for i in result.issues}
    assert "missing_leaf" in codes or "leaf_tier_flag" in codes
    assert "leaf_cad_required" in codes


def test_spend_without_qa_miss_hard_blocks() -> None:
    with pytest.raises(PermissionError, match="QA miss"):
        assert_spend_authorized(spend=True, prefer_local=True, qa_misses=())


def test_spend_with_qa_miss_allowed() -> None:
    assert_spend_authorized(
        spend=True,
        prefer_local=True,
        qa_misses=[QAMiss(kind="silhouette", detail="iou low")],
    )


def test_spend_no_prefer_local_allowed_without_miss() -> None:
    assert_spend_authorized(spend=True, prefer_local=False, qa_misses=())


def test_cli_spend_without_qa_miss_exits_2(tmp_path: Path) -> None:
    job = tmp_path / "job"
    job.mkdir()
    (job / "manifests").mkdir()
    code = main(
        [
            "--spend",
            "run",
            str(job),
            "--skip-packs",
            "--stage",
            "tripo",
        ]
    )
    assert code == 2


def test_cli_spend_with_qa_miss_does_not_hard_block(tmp_path: Path, cardinal_job: Path) -> None:
    # Dry-run path with --spend + miss should get past the hard gate (no live HTTP).
    code = main(
        [
            "--spend",
            "run",
            str(cardinal_job),
            "--skip-packs",
            "--stage",
            "tripo",
            "--qa-miss",
            "angle_coverage",
            "--json",
        ]
    )
    assert code == 0


def test_ledger_includes_zero_cost_local_pipeline_stages() -> None:
    """Ledger includes zero-cost local pipeline stages (U7 success criterion)."""
    ledger = build_ledger_from_provider_jobs(
        [
            {
                "provider": "triposr",
                "mode": "local",
                "status": "succeeded",
                "consumed": 0.0,
                "job_id": "triposr-1",
                "meta": {"stage": "triposr"},
            },
            {
                "provider": "tripo",
                "mode": "dry-run",
                "status": "dry_run",
                "consumed": 0.0,
                "job_id": "tripo-1",
                "meta": {"stage": "tripo"},
            },
        ],
        subject_id="ledger-test",
        include_local_pipeline=True,
        local_stages_present=["ingest", "quality", "composites", "build_packs", "triposr", "blender_explode", "qa_silhouette", "qa_bom"],
    )
    ensure_local_pipeline_zeros(
        ledger,
        present_stages=[
            "ingest",
            "quality",
            "composites",
            "build_packs",
            "triposr",
            "blender_explode",
            "qa_silhouette",
            "qa_bom",
        ],
    )
    stages = {e.stage for e in ledger.entries}
    for stage in LOCAL_PIPELINE_STAGES:
        assert stage in stages, f"missing local stage {stage}"
    local_entries = [e for e in ledger.entries if e.kind == "local"]
    assert local_entries
    assert all(e.consumed == 0.0 for e in local_entries)
    assert ledger.local_total == 0.0


def test_ledger_records_cloud_consumed() -> None:
    ledger = build_ledger_from_provider_jobs(
        [
            {
                "provider": "tripo",
                "mode": "live",
                "status": "succeeded",
                "consumed": 0.55,
                "job_id": "tripo-live",
                "meta": {"stage": "tripo"},
            }
        ],
        include_local_pipeline=False,
    )
    assert ledger.cloud_total == pytest.approx(0.55)
    assert ledger.entries[0].kind == "cloud"


def test_seedance_blocked_without_qa_pass() -> None:
    decision = seedance_allowed(qa_passed=False, spend=True)
    assert decision.allowed is False
    assert "post-QA" in decision.reason or "QA" in decision.reason


def test_seedance_allowed_after_qa_pass_with_spend() -> None:
    decision = seedance_allowed(qa_passed=True, spend=True)
    assert decision.allowed is True


def test_promote_blocks_spend_without_misses() -> None:
    decisions = promote_from_misses([], spend=True, prefer_local=True, qa_passed=False)
    assert any(d.action == "blocked_spend" and not d.allowed for d in decisions)


def test_run_qa_gates_end_to_end(tmp_path: Path) -> None:
    job = tmp_path / "job"
    ver = job / "out" / "blender" / "verification"
    ref_dir = job / "verification"
    hier = build_l1_l2_example("qa-e2e")
    write_parts_hierarchy(job / "out" / "blender" / "parts.json", hier)
    _sil_image(ref_dir / "reference-silhouette-front.png", box=(30, 30, 90, 90))
    _sil_image(ver / "local-silhouette-front.png", box=(30, 30, 90, 90))
    # Also write a failing left axis to prove miss emission when coverage fails
    _sil_image(ref_dir / "reference-silhouette-left.png", box=(20, 20, 110, 110))
    _sil_image(ver / "local-silhouette-left.png", box=(80, 80, 100, 100))

    (job / "manifests").mkdir(parents=True)
    (job / "manifests" / "provider_jobs.json").write_text(
        json.dumps(
            {
                "prefer_local": True,
                "spend": False,
                "jobs": [
                    {
                        "schema_version": "1.0.0",
                        "provider": "triposr",
                        "mode": "dry-run",
                        "job_id": "t1",
                        "status": "dry_run",
                        "consumed": 0.0,
                        "meta": {"stage": "triposr"},
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (job / "frames").mkdir()
    (job / "build_packs").mkdir()

    report = run_qa_gates(job, required_bom_tier="L2", write=True)
    assert report.bom is not None and report.bom.passed
    assert report.silhouette is not None
    assert report.silhouette.passed is False  # left axis fails
    assert any(m.kind == "silhouette" for m in report.misses)
    assert report.passed is False
    assert report.ledger is not None
    assert report.ledger.local_total == 0.0
    assert (job / "manifests" / "qa_gate_report.json").is_file()
    assert (job / "manifests" / "cost_ledger.json").is_file()
    assert (job / "manifests" / "qa_misses.json").is_file()


def test_run_qa_gates_pass_when_silhouette_and_bom_ok(tmp_path: Path) -> None:
    job = tmp_path / "job"
    ver = job / "out" / "blender" / "verification"
    ref_dir = job / "verification"
    write_parts_hierarchy(
        job / "out" / "blender" / "parts.json", build_l1_l2_example("qa-pass")
    )
    for axis in ("front", "left"):
        _sil_image(ref_dir / f"reference-silhouette-{axis}.png", box=(30, 30, 90, 90))
        _sil_image(ver / f"local-silhouette-{axis}.png", box=(30, 30, 90, 90))
    report = run_qa_gates(job, required_bom_tier="L2", write=True)
    assert report.passed is True
    assert not report.misses
    # Promote should allow stop_local_ok + optional seedance dry-run block
    actions = {d.action for d in report.promote}
    assert "stop_local_ok" in actions


def test_cli_qa_policy() -> None:
    code = main(["qa", "/tmp", "--policy"])
    assert code == 0
