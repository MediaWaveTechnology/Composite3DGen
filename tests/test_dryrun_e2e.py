"""U5 GLM QM1 fixture intake + dry-run E2E (no cloud spend)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from composite3dgen.blender.schema import load_parts_hierarchy, validate_parts_hierarchy
from composite3dgen.cli import main
from composite3dgen.dryrun import reuse_recorded_provider_proofs, run_dry_run_e2e
from composite3dgen.manifest import load_manifest
from composite3dgen.providers.base import PAID_PROVIDERS

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "glm-qm1"


@pytest.fixture
def qm1_job(tmp_path: Path) -> Path:
    """Copy curated GLM QM1 fixture into an isolated job dir."""
    assert FIXTURE.is_dir(), f"missing fixture {FIXTURE}"
    dest = tmp_path / "glm-qm1"
    shutil.copytree(FIXTURE, dest)
    return dest


def test_fixture_manifest_valid() -> None:
    manifest = load_manifest(FIXTURE / "manifests" / "subject.manifest.json")
    assert manifest.subject_id == "glm-qm1"
    assert manifest.domain == "glm"
    assert manifest.reuse.get("prior_provider_outs")
    assert (FIXTURE / "frames" / "front.jpg").is_file()


def test_staging_assembly_is_l1_l2_not_dumptruck() -> None:
    path = FIXTURE / "staging" / "qm1-assembly.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_parts_hierarchy(data)
    assert errors == [], errors
    hier = load_parts_hierarchy(path)
    assert hier.subject_id == "glm-qm1"
    assert hier.tier == "L2"
    assert hier.source == "staging"
    assert any(p.level == "L1" for p in hier.parts)
    assert any(p.level == "L2" for p in hier.parts)
    # Explicit anti-stub: notes must reject dump-truck-as-truth.
    blob = json.dumps(data).lower() + (hier.notes or "").lower()
    assert "dump-truck" in blob or "dump truck" in blob or "dumptruck" in blob
    assert "staging" in blob


def test_recorded_tripo_proofs_present() -> None:
    parts = json.loads(
        (FIXTURE / "recorded" / "tripo" / "parts-task.json").read_text(encoding="utf-8")
    )
    texture = json.loads(
        (FIXTURE / "recorded" / "tripo" / "texture-task.json").read_text(encoding="utf-8")
    )
    refs = json.loads((FIXTURE / "recorded" / "media-refs.json").read_text(encoding="utf-8"))
    assert parts["provider"] == "tripo"
    assert parts["meta"]["recorded"] is True
    assert parts["meta"]["this_run_consumed"] == 0.0
    assert texture["artifacts"]["task_type"] == "texture_on_parts"
    assert refs["policy"]
    assert any(r["id"] == "tripo_parts_glb" for r in refs["refs"])
    # No invented binary GLB in fixture tree.
    assert not list(FIXTURE.rglob("*.glb"))


def test_reuse_recorded_stamps_zero_cost(qm1_job: Path) -> None:
    manifest = load_manifest(qm1_job / "manifests" / "subject.manifest.json")
    reused, results, notes = reuse_recorded_provider_proofs(qm1_job, manifest)
    assert len(reused) >= 2
    assert results
    assert all(r.consumed == 0.0 for r in results)
    assert all(r.mode == "dry-run" for r in results)
    assert all((r.meta or {}).get("this_run_consumed") == 0.0 for r in results)
    assert any("reused" in n.lower() for n in notes)
    assert (qm1_job / "out" / "tripo" / "parts-task.json").is_file()


def test_dry_run_e2e_zero_spend(qm1_job: Path) -> None:
    result = run_dry_run_e2e(
        qm1_job,
        prefer_mwt1=False,
        force_executor="local",
        prefix="local",
    )
    assert result.ok, result.error or result.summary()
    assert result.this_run_consumed == 0.0
    assert result.packs is not None
    assert result.providers is not None
    assert result.explode is not None and result.explode.ok
    assert result.explode.mode == "dry-run"
    assert result.checklist_path is not None and result.checklist_path.is_file()

    # Packs front present
    assert (qm1_job / "build_packs" / "tripo" / "front.jpg").is_file()

    # No live paid jobs
    for job in result.providers.results:
        if job.provider in PAID_PROVIDERS:
            assert job.mode == "dry-run"
            assert (job.consumed or 0) == 0.0

    # L1/L2 parts.json
    hier = load_parts_hierarchy(result.explode.parts_path)  # type: ignore[arg-type]
    assert hier.tier == "L2"
    assert hier.source == "staging"
    assert any(p.part_id == "undercarriage" for p in hier.parts)
    assert any(p.part_id == "bucket" for p in hier.parts)

    # Checklist all non-fail
    assert all(c.status != "fail" for c in result.checklist)
    by_id = {c.id: c for c in result.checklist}
    assert by_id["no_spend"].status == "pass"
    assert by_id["packs"].status == "pass"
    assert by_id["virtual_providers"].status == "pass"
    assert by_id["blender_l1_l2"].status == "pass"
    assert by_id["reuse_recorded"].status == "pass"

    # Verification markers
    assert result.explode.verification
    assert (qm1_job / "out" / "blender" / "exploded.glb.dry-run").is_file()


def test_dry_run_refuses_spend_flag(qm1_job: Path) -> None:
    result = run_dry_run_e2e(qm1_job, spend_requested=True, force_executor="local")
    assert not result.ok
    assert result.error and "--spend" in result.error


def test_cli_dry_run_json(qm1_job: Path, capsys) -> None:
    code = main(
        [
            "--no-prefer-local",
            "dry-run",
            str(qm1_job),
            "--executor",
            "local",
            "--json",
        ]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["subject_id"] == "glm-qm1"
    assert out["this_run_consumed"] == 0.0
    assert out["explode"]["tier"] == "L2"


def test_cli_dry_run_rejects_spend(qm1_job: Path, capsys) -> None:
    code = main(["--spend", "dry-run", str(qm1_job), "--executor", "local"])
    assert code == 2
    err = capsys.readouterr().err
    assert "--spend" in err
