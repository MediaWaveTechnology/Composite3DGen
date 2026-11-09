"""MWT1 health-check + capability matrix (injectable transport)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from composite3dgen.nodes.capabilities import (
    BASE_REQUIRED,
    STAGE_REQUIREMENTS,
    CapabilityError,
    remediation_for,
)
from composite3dgen.nodes.health import (
    VERIFY_ON_LAN,
    HealthChecker,
    capability_matrix_fixture,
    run_health_check,
)
from composite3dgen.nodes import mwt1 as mwt1_mod
from composite3dgen.nodes.executor import select_executor
from composite3dgen.providers.transport import MockRemoteFSTransport


def _healthy_handlers() -> dict[str, tuple[int, str, str]]:
    """Command-substring → (code, stdout, stderr) for a fully capable node."""
    cuda_info = json.dumps(
        {
            "torch": True,
            "cuda": True,
            "vram_gb": 8.0,
            "torch_version": "2.2.0",
            "error": None,
            "device_name": "Mock GPU",
        }
    )
    return {
        "__mwt1_ssh_ok__": (0, "__mwt1_ssh_ok__\n", ""),
        "writable": (0, "writable\n", ""),
        "composite3dgen_write_probe": (0, "writable\n", ""),
        "command -v ffmpeg": (0, "/usr/bin/ffmpeg\nffmpeg version 6.0\n", ""),
        "pillow_ok": (0, "pillow_ok\nnumpy_ok\n", ""),
        "find_spec": (0, "pillow_ok\nnumpy_ok\n", ""),
        "vram_gb": (0, cuda_info + "\n", ""),
        "import torch": (0, cuda_info + "\n", ""),
        "path=/usr/bin/blender": (0, "path=/usr/bin/blender\nBlender 4.2.0\n", ""),
        "command -v blender": (0, "path=/usr/bin/blender\nBlender 4.2.0\n", ""),
        "rev-parse HEAD": (
            0,
            "dir_ok\nrun_py_ok\nhead=107cefdc244c39106fa830359024f6a2f1c78871\n",
            "",
        ),
        "vendor/TripoSR": (
            0,
            "dir_ok\nrun_py_ok\nhead=107cefdc244c39106fa830359024f6a2f1c78871\n",
            "",
        ),
        "path=/usr/bin/colmap": (0, "path=/usr/bin/colmap\nCOLMAP\n", ""),
        "command -v colmap": (0, "path=/usr/bin/colmap\nCOLMAP\n", ""),
        "meshroom_batch": (1, "missing\n", ""),
        "command -v Meshroom": (1, "missing\n", ""),
    }


class ScriptedTransport(MockRemoteFSTransport):
    """MockRemoteFS that matches probes by substring with priority."""

    def run(self, command: str, *, timeout: float = 600.0) -> tuple[int, str, str]:
        del timeout
        self.commands.append(command)
        # Prefer longest matching needle for specificity.
        matches = [
            (needle, result)
            for needle, result in self.run_handlers.items()
            if needle in command
        ]
        if matches:
            matches.sort(key=lambda x: len(x[0]), reverse=True)
            return matches[0][1]
        return self.default_run


@pytest.fixture
def healthy_transport(tmp_path: Path) -> ScriptedTransport:
    return ScriptedTransport(root=tmp_path, run_handlers=_healthy_handlers())


def test_run_health_check_no_transport_is_unreachable() -> None:
    report = run_health_check()
    assert report.reachable is False
    assert report.ok is False
    assert "ssh" in report.missing_required
    assert VERIFY_ON_LAN in report.facts["blender_path"]
    assert any("No transport" in n or "verify" in n.lower() for n in report.notes)


def test_healthy_matrix_ready_stages(healthy_transport: ScriptedTransport) -> None:
    report = HealthChecker(transport=healthy_transport).probe_all()
    assert report.reachable is True
    assert report.ok is True
    assert report.missing_required == []
    assert report.stages["ingest_ffmpeg"] == "ready"
    assert report.stages["quality_composites"] == "ready"
    assert report.stages["triposr"] == "ready"
    assert report.stages["blender_explode"] == "ready"
    assert report.facts["blender_path"] == "/usr/bin/blender"
    assert report.facts["vram_gb"] == 8.0
    # meshroom optional missing should not fail base
    assert "meshroom" in report.missing_optional or not report.capabilities["meshroom"].ok


def test_ssh_failure_skips_remaining(tmp_path: Path) -> None:
    transport = ScriptedTransport(
        root=tmp_path,
        run_handlers={"__mwt1_ssh_ok__": (255, "", "connection refused")},
        default_run=(255, "", "fail"),
    )
    report = HealthChecker(transport=transport).probe_all()
    assert report.reachable is False
    assert report.ok is False
    assert report.capabilities["ffmpeg"].ok is False
    assert "Skipped" in report.capabilities["ffmpeg"].detail
    assert report.capabilities["ssh"].remediation


def test_fail_closed_missing_ffmpeg(tmp_path: Path) -> None:
    handlers = _healthy_handlers()
    handlers["command -v ffmpeg"] = (1, "", "not found")
    # Also clear any ffmpeg substring match from version line handlers
    transport = ScriptedTransport(root=tmp_path, run_handlers=handlers)
    report = HealthChecker(transport=transport).probe_all()
    assert report.ok is False
    assert "ffmpeg" in report.missing_required
    assert report.stages["ingest_ffmpeg"] == "blocked"
    assert report.stages["quality_composites"] == "ready"
    report_require = report
    with pytest.raises(CapabilityError) as exc:
        report_require.require_stage("ingest_ffmpeg")
    assert "ffmpeg" in exc.value.missing


def test_cuda_vram_below_threshold_blocks_triposr(tmp_path: Path) -> None:
    handlers = _healthy_handlers()
    low = json.dumps(
        {
            "torch": True,
            "cuda": True,
            "vram_gb": 4.0,
            "torch_version": "2.2.0",
            "error": None,
            "device_name": "Small GPU",
        }
    )
    handlers["import torch"] = (0, low + "\n", "")
    handlers["vram_gb"] = (0, low + "\n", "")
    transport = ScriptedTransport(root=tmp_path, run_handlers=handlers)
    report = HealthChecker(transport=transport).probe_all()
    assert report.ok is True  # base packs still OK
    assert report.capabilities["cuda_pytorch"].ok is False
    assert report.stages["triposr"] == "blocked"
    with pytest.raises(CapabilityError):
        report.require_stage("triposr")


def test_capability_matrix_fixture_and_executor() -> None:
    healthy = capability_matrix_fixture(
        ok={name: True for name in ("ssh", "job_root_writable", "ffmpeg", "python_image")}
    )
    assert healthy.ok is True
    mwt1_mod.set_health_probe(lambda: healthy.ok)
    try:
        sel = select_executor(prefer_mwt1=True)
        assert sel.name == "mwt1"
    finally:
        mwt1_mod.set_health_probe(None)

    unreachable = capability_matrix_fixture(reachable=False)
    assert unreachable.ok is False
    mwt1_mod.set_health_probe(lambda: unreachable.ok)
    try:
        sel = select_executor(prefer_mwt1=True)
        assert sel.name == "local"
    finally:
        mwt1_mod.set_health_probe(None)


def test_photogrammetry_needs_colmap_or_meshroom(healthy_transport: ScriptedTransport) -> None:
    # healthy fixture has colmap, missing meshroom → ready
    report = HealthChecker(transport=healthy_transport).probe_all()
    assert report.stages["photogrammetry"] == "ready"

    handlers = _healthy_handlers()
    handlers["command -v colmap"] = (1, "missing\n", "")
    handlers["path=/usr/bin/colmap"] = (1, "missing\n", "")
    transport = ScriptedTransport(root=healthy_transport.root, run_handlers=handlers)
    report2 = HealthChecker(transport=transport).probe_all()
    assert report2.stages["photogrammetry"] == "blocked"


def test_remediation_text_present() -> None:
    text = remediation_for("blender")
    assert "verify" in text.lower() or "Blender" in text or "blender" in text
    assert STAGE_REQUIREMENTS["blender_explode"] == (
        "ssh",
        "job_root_writable",
        "blender",
    )
    assert set(BASE_REQUIRED) <= set(STAGE_REQUIREMENTS["ingest_ffmpeg"]) | {
        "python_image"
    }


def test_default_is_healthy_false_without_probe() -> None:
    mwt1_mod.set_health_probe(None)
    mwt1_mod.set_default_transport(None)
    assert mwt1_mod.is_healthy() is False


def test_node_contract_pin() -> None:
    contract = mwt1_mod.node_contract()
    assert contract.alias == "mwt1"
    assert contract.address == "192.168.50.212"
    assert contract.user == "davethompson"
    assert len(contract.triposr_pin) >= 7
    assert mwt1_mod.remote_job_path("qm1", "job1").endswith("qm1/job1")
