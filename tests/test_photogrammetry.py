"""U6: photogrammetry adapter — MWT1 executor when capable; dry-run when missing."""

from __future__ import annotations

import json
from pathlib import Path

from composite3dgen.cli import main
from composite3dgen.nodes.health import capability_matrix_fixture, run_health_check
from composite3dgen.providers.photogrammetry import (
    missing_binary_next_steps,
    run_photogrammetry,
)
from composite3dgen.providers.router import plan_routes
from composite3dgen.providers.runner import ProviderBundle, run_plan
from composite3dgen.providers.transport import MockRemoteFSTransport
from composite3dgen.qa.miss import QAMiss


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "rc-dex410"


class ScriptedTransport(MockRemoteFSTransport):
    """Match health probes by substring."""

    def run(self, command: str, *, timeout: float = 600.0) -> tuple[int, str, str]:
        del timeout
        self.commands.append(command)
        matches = [
            (needle, result)
            for needle, result in self.run_handlers.items()
            if needle in command
        ]
        if matches:
            matches.sort(key=lambda x: len(x[0]), reverse=True)
            return matches[0][1]
        return (1, "", f"unhandled: {command[:120]}")


def _colmap_ready_handlers() -> dict[str, tuple[int, str, str]]:
    return {
        "__mwt1_ssh_ok__": (0, "__mwt1_ssh_ok__\n", ""),
        "writable": (0, "writable\n", ""),
        "composite3dgen_write_probe": (0, "writable\n", ""),
        "command -v ffmpeg": (0, "/usr/bin/ffmpeg\nffmpeg version 6.0\n", ""),
        "pillow_ok": (0, "pillow_ok\nnumpy_ok\n", ""),
        "find_spec": (0, "pillow_ok\nnumpy_ok\n", ""),
        "import torch": (
            0,
            json.dumps(
                {
                    "torch": False,
                    "cuda": False,
                    "vram_gb": None,
                    "torch_version": None,
                    "error": "no torch",
                    "device_name": None,
                }
            )
            + "\n",
            "",
        ),
        "path=/usr/bin/blender": (0, "path=/usr/bin/blender\nBlender 4.2.0\n", ""),
        "command -v blender": (0, "path=/usr/bin/blender\nBlender 4.2.0\n", ""),
        "vendor/TripoSR": (0, "dir_missing\n", ""),
        "path=/usr/bin/colmap": (0, "path=/usr/bin/colmap\nCOLMAP 3.9\n", ""),
        "command -v colmap": (0, "path=/usr/bin/colmap\nCOLMAP 3.9\n", ""),
        "automatic_reconstructor": (0, "colmap ok\n", ""),
        "meshroom_batch": (1, "missing\n", ""),
        "command -v Meshroom": (1, "missing\n", ""),
    }


def test_missing_binary_next_steps_mention_install() -> None:
    steps = missing_binary_next_steps(subject_id="rc-dex410")
    blob = "\n".join(steps)
    assert "COLMAP" in blob
    assert "Meshroom" in blob
    assert "photogrammetry.md" in blob or "brew install colmap" in blob
    assert "AlanTBrain" in blob or "MWT1" in blob


def test_dry_run_when_binaries_missing(tmp_path: Path) -> None:
    job = tmp_path / "job"
    frames = job / "frames"
    frames.mkdir(parents=True)
    (frames / "front.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    result = run_photogrammetry(
        job,
        prefer_mwt1=False,
        force_executor="local",
        allow_local=True,
    )
    # If the CI host somehow has colmap, still assert structured result shape.
    assert result.provider_result.consumed == 0.0
    summary = result.summary()
    assert "probe" in summary
    assert "executor" in summary
    if not result.probe.available:
        assert result.mode == "dry-run"
        assert result.next_steps
        assert result.provider_result.status.value == "dry_run"
        assert result.provider_result.meta.get("next_steps")


def test_mwt1_executor_when_colmap_capable(tmp_path: Path) -> None:
    job = tmp_path / "photo-job"
    frames = job / "frames"
    frames.mkdir(parents=True)
    (frames / "a.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (frames / "b.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    transport = ScriptedTransport(
        root=tmp_path / "remote",
        run_handlers=_colmap_ready_handlers(),
    )
    # Health must see colmap; force MWT1 selection via prefer + healthy probe.
    from composite3dgen.nodes import mwt1 as mwt1_mod

    mwt1_mod.set_default_transport(transport)
    mwt1_mod.set_health_probe(lambda: True)
    try:
        result = run_photogrammetry(
            job,
            subject_id="rc-dex410",
            prefer_mwt1=True,
            force_executor="mwt1",
            transport=transport,
        )
    finally:
        mwt1_mod.set_default_transport(None)
        mwt1_mod.set_health_probe(None)

    assert result.executor.name == "mwt1"
    assert result.mode == "mwt1"
    assert result.probe.preferred == "colmap"
    assert result.stage_ready is True
    assert result.provider_result.status.value == "succeeded"
    assert result.remote_job is not None
    # Uploaded frames + ran automatic_reconstructor
    assert any("automatic_reconstructor" in c for c in transport.commands)


def test_capability_matrix_photogrammetry_ready_with_colmap() -> None:
    report = capability_matrix_fixture(
        ok={
            "ssh": True,
            "job_root_writable": True,
            "ffmpeg": True,
            "python_image": True,
            "colmap": True,
            "meshroom": False,
        }
    )
    assert report.stages["photogrammetry"] == "ready"
    report.require_stage("photogrammetry")  # must not raise


def test_capability_matrix_photogrammetry_blocked_without_tools() -> None:
    report = capability_matrix_fixture(
        ok={
            "ssh": True,
            "job_root_writable": True,
            "ffmpeg": True,
            "python_image": True,
            "colmap": False,
            "meshroom": False,
        }
    )
    assert report.stages["photogrammetry"] == "blocked"


def test_router_and_runner_photogrammetry_stage(tmp_path: Path) -> None:
    job = tmp_path / "routed"
    (job / "frames").mkdir(parents=True)
    (job / "frames" / "front.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    plan = plan_routes(
        prefer_local=True,
        spend=False,
        qa_misses=[QAMiss(kind="angle_coverage")],
        stages=["photogrammetry"],
    )
    assert plan.decisions[0].stage == "photogrammetry"
    assert plan.decisions[0].provider == "colmap"
    assert plan.decisions[0].mode == "local"

    bundle = ProviderBundle()
    result = run_plan(plan, job, subject_id="rc-dex410", bundle=bundle)
    assert len(result.results) == 1
    assert result.results[0].provider in ("colmap", "meshroom")
    assert result.results[0].consumed == 0.0


def test_cli_photogrammetry_json(capsys) -> None:
    code = main(
        [
            "photogrammetry",
            str(FIXTURE),
            "--executor",
            "local",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["executor"] == "local"
    assert "probe" in payload
    assert "next_steps" in payload


def test_no_transport_health_skips_live() -> None:
    report = run_health_check()
    assert report.reachable is False
    assert report.stages.get("photogrammetry") == "blocked"
