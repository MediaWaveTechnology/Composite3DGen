"""U6: CadQuery adapter — missing-binary dry-run returns structured next steps."""

from __future__ import annotations

import json
from pathlib import Path

from composite3dgen.cad.cadquery_adapter import (
    CadQueryProbe,
    missing_binary_next_steps,
    run_cadquery,
)
from composite3dgen.cli import main

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "rc-dex410"


def test_missing_binary_next_steps_structured() -> None:
    steps = missing_binary_next_steps(
        prefer_mwt1=True,
        register_path=FIXTURE / "dimension-register.json",
        subject_id="rc-dex410",
    )
    assert len(steps) >= 4
    blob = "\n".join(steps)
    assert "CadQuery" in blob
    assert "AlanTBrain" in blob or "MWT1" in blob
    assert "FUSION_HANDOFF" in blob or "Fusion" in blob
    assert "3ds Max" in blob


def test_cadquery_dry_run_when_missing(tmp_path: Path, monkeypatch) -> None:
    # Force local probe to report missing even if the environment has CadQuery.
    job = tmp_path / "job"
    job.mkdir()
    (job / "cad").mkdir()
    register = FIXTURE / "dimension-register.json"
    (job / "cad" / "dimension-register.json").write_text(
        register.read_text(encoding="utf-8"), encoding="utf-8"
    )

    monkeypatch.setattr(
        "composite3dgen.cad.cadquery_adapter.probe_cadquery_local",
        lambda: CadQueryProbe(
            available=False,
            import_ok=False,
            cq_cli=None,
            detail="test: forced missing",
            where="none",
        ),
    )

    result = run_cadquery(
        job,
        prefer_mwt1=False,
        force_executor="local",
        allow_local=True,
    )
    assert result.ok
    assert result.status == "dry_run_missing_binary"
    assert result.mode == "dry-run"
    assert result.next_steps
    assert any("CadQuery" in s for s in result.next_steps)
    assert any("Fusion" in s or "FUSION" in s for s in result.next_steps)
    record = result.out_dir / "cadquery_job.json"
    assert record.is_file()
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["status"] == "dry_run_missing_binary"
    assert payload["next_steps"]
    assert payload["leaf_fitment_allowed"] is True


def test_cli_cad_json(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "composite3dgen.cad.cadquery_adapter.probe_cadquery_local",
        lambda: CadQueryProbe(
            available=False,
            import_ok=False,
            cq_cli=None,
            detail="test: forced missing",
            where="none",
        ),
    )
    code = main(
        [
            "cad",
            str(FIXTURE),
            "--executor",
            "local",
            "--json",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "dry_run_missing_binary"
    assert isinstance(payload["next_steps"], list)
    assert payload["next_steps"]
