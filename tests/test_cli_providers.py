"""CLI dry-run / --spend gate wiring for U3 providers."""

from __future__ import annotations

import json
from pathlib import Path

from composite3dgen.cli import main


def test_route_command_json(capsys) -> None:
    code = main(["route", "--stage", "triposr", "--stage", "tripo"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["prefer_local"] is True
    assert out["spend"] is False
    assert out["decisions"][0]["stage"] == "triposr"
    assert out["decisions"][1]["mode"] == "dry-run"


def test_run_dry_run_records_virtual_jobs(cardinal_job: Path, capsys) -> None:
    code = main(
        [
            "run",
            str(cardinal_job),
            "--executor",
            "local",
            "--stage",
            "triposr",
            "--stage",
            "tripo",
            "--json",
        ]
    )
    assert code == 0
    ledger = cardinal_job / "manifests" / "provider_jobs.json"
    assert ledger.is_file()
    doc = json.loads(ledger.read_text(encoding="utf-8"))
    assert doc["spend"] is False
    providers = {j["provider"] for j in doc["jobs"]}
    assert "triposr" in providers
    assert "tripo" in providers
    assert all(j["mode"] == "dry-run" for j in doc["jobs"])
    assert all(j["status"] == "dry_run" for j in doc["jobs"])


def test_spend_without_qa_miss_does_not_live(cardinal_job: Path) -> None:
    code = main(
        [
            "--spend",
            "run",
            str(cardinal_job),
            "--executor",
            "local",
            "--skip-packs",
            "--stage",
            "tripo",
            "--json",
        ]
    )
    assert code == 0
    doc = json.loads((cardinal_job / "manifests" / "provider_jobs.json").read_text())
    assert doc["spend"] is True
    assert doc["jobs"][0]["mode"] == "dry-run"
    assert doc["jobs"][0]["status"] == "dry_run"


def test_spend_with_qa_miss_attempts_live_but_needs_secret(
    cardinal_job: Path, monkeypatch
) -> None:
    # Clear secrets so live path blocks on MissingSecret — still no paid HTTP.
    for key in ("TRIPO_API_KEY", "TRIPO_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    code = main(
        [
            "--spend",
            "run",
            str(cardinal_job),
            "--executor",
            "local",
            "--skip-packs",
            "--qa-miss",
            "angle_coverage",
            "--stage",
            "tripo",
            "--json",
        ]
    )
    assert code == 0
    doc = json.loads((cardinal_job / "manifests" / "provider_jobs.json").read_text())
    job = doc["jobs"][0]
    assert job["mode"] == "live"
    assert job["status"] == "blocked"
    assert "API key" in (job.get("error") or "")


def test_schema_validates_provider_record(cardinal_job: Path) -> None:
    import jsonschema

    schema = json.loads(
        Path("schema/job.provider.schema.json").read_text(encoding="utf-8")
    )
    code = main(
        [
            "run",
            str(cardinal_job),
            "--executor",
            "local",
            "--skip-packs",
            "--stage",
            "hi3d",
            "--json",
        ]
    )
    assert code == 0
    doc = json.loads((cardinal_job / "manifests" / "provider_jobs.json").read_text())
    for job in doc["jobs"]:
        jsonschema.validate(job, schema)
