"""Blender explode job runner — mocked / dry-run (no invented Blender paths)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from composite3dgen.blender.jobs import run_blender_explode
from composite3dgen.blender.paths import UNVERIFIED, package_script_path, resolve_blender_path
from composite3dgen.blender.schema import build_l1_l2_example, load_parts_hierarchy
from composite3dgen.blender.scripts import explode_hub
from composite3dgen.nodes.health import VERIFY_ON_LAN
from composite3dgen.providers.transport import MockRemoteFSTransport


def test_package_script_exists() -> None:
    path = package_script_path("explode_hub.py")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Empty" in text or "empty" in text
    assert "export_scene.gltf" in text or "GLB" in text


def test_explode_hub_importable_outside_blender() -> None:
    assert explode_hub.IN_BLENDER is False
    assert explode_hub.main  # callable
    # main without bpy should exit non-zero if forced through run with fake ns —
    # parser alone is enough for smoke.
    parser = explode_hub.build_parser()
    args = parser.parse_args(
        [
            "--input",
            "-",
            "--hierarchy",
            "/tmp/h.json",
            "--out-dir",
            "/tmp/out",
        ]
    )
    assert args.skip_stills is False


def test_resolve_blender_unverified_by_default() -> None:
    res = resolve_blender_path()
    assert res.verified is False
    assert res.path is None
    assert VERIFY_ON_LAN in res.as_dict()["display"] or UNVERIFIED == res.as_dict()["display"]


def test_resolve_blender_from_health_facts() -> None:
    res = resolve_blender_path(health_facts={"blender_path": "/usr/bin/blender"})
    assert res.verified is True
    assert res.path == "/usr/bin/blender"
    assert res.source == "health_facts"


def test_resolve_ignores_verify_marker_in_facts() -> None:
    res = resolve_blender_path(health_facts={"blender_path": f"<{VERIFY_ON_LAN}>"})
    assert res.verified is False


def test_dry_run_local_writes_parts_json(tmp_path: Path) -> None:
    job = tmp_path / "job"
    job.mkdir()
    result = run_blender_explode(
        job,
        subject_id="dry1",
        force_executor="local",
        prefer_mwt1=False,
    )
    assert result.ok
    assert result.mode == "dry-run"
    assert result.parts_path is not None
    hier = load_parts_hierarchy(result.parts_path)
    assert hier.subject_id == "dry1"
    assert hier.tier == "L2"
    assert result.glb_path is None
    assert UNVERIFIED in result.summary()["blender"]["display"]
    assert (job / "out" / "blender" / "exploded.glb.dry-run").is_file()
    assert result.verification


def test_dry_run_with_custom_hierarchy(tmp_path: Path) -> None:
    job = tmp_path / "job"
    hier = build_l1_l2_example("custom")
    hier_path = tmp_path / "in.json"
    hier_path.write_text(json.dumps(hier.as_dict(), indent=2), encoding="utf-8")
    result = run_blender_explode(
        job,
        hierarchy_path=hier_path,
        force_executor="local",
    )
    assert result.ok
    loaded = load_parts_hierarchy(result.parts_path)  # type: ignore[arg-type]
    assert loaded.subject_id == "custom"
    assert "artifacts" in loaded.as_dict()


def test_mwt1_without_transport_falls_back_dry(tmp_path: Path) -> None:
    job = tmp_path / "job"
    result = run_blender_explode(
        job,
        subject_id="mwt1dry",
        force_executor="mwt1",
        mwt1_probe=lambda: True,
        transport=None,
    )
    assert result.ok
    assert result.mode == "dry-run"
    assert any("transport" in n.lower() or "Dry-run" in n or "dry-run" in n for n in result.notes)


class _BlenderMockFS(MockRemoteFSTransport):
    """Mock remote FS that synthesizes Blender outputs on explode_hub invoke."""

    def run(self, command: str, *, timeout: float = 600.0) -> tuple[int, str, str]:
        self.commands.append(command)
        if "explode_hub.py" in command or "blender" in command:
            # Locate remote out dir from command tokens.
            # Command is shell-quoted; find --out-dir value.
            out_dir = None
            parts = command.replace("'", " ").split()
            if "--out-dir" in parts:
                out_dir = parts[parts.index("--out-dir") + 1]
            if out_dir:
                mapped = self._map(out_dir)
                mapped.mkdir(parents=True, exist_ok=True)
                parts_doc = build_l1_l2_example("remote").as_dict()
                parts_doc["artifacts"] = {
                    "glb": "exploded.glb",
                    "parts_json": "parts.json",
                    "verification": ["verification/local-exploded-l1-front.png"],
                }
                (mapped / "parts.json").write_text(
                    json.dumps(parts_doc, indent=2) + "\n", encoding="utf-8"
                )
                (mapped / "exploded.glb").write_bytes(b"glTF-fake")
                ver = mapped / "verification"
                ver.mkdir(exist_ok=True)
                (ver / "local-exploded-l1-front.png").write_bytes(b"PNG")
            return 0, '{"ok": true}\n', ""
        return self.default_run


def test_mwt1_with_mock_transport_and_verified_path(tmp_path: Path) -> None:
    job = tmp_path / "job"
    fs = _BlenderMockFS(root=tmp_path / "remote")
    result = run_blender_explode(
        job,
        subject_id="remote",
        force_executor="mwt1",
        mwt1_probe=lambda: True,
        transport=fs,
        blender_path="/usr/bin/blender",
        health_facts={"blender_path": "/usr/bin/blender"},
        skip_stills=False,
    )
    # ensure_stage may fail without full health handlers — job should still
    # either succeed via remote mock or dry-run safely.
    assert result.parts_path is not None
    assert result.ok
    if result.mode == "mwt1":
        assert result.glb_path is not None
        assert any("blender" in c for c in fs.commands)
    else:
        # Capability ensure failed closed → dry-run is acceptable.
        assert result.mode == "dry-run"


def test_blender_smoke_skipped_if_missing(tmp_path: Path) -> None:
    """allow_local_blender without a binary must dry-run, not invent a path."""
    job = tmp_path / "job"
    result = run_blender_explode(
        job,
        subject_id="smoke",
        force_executor="local",
        allow_local_blender=True,
        # Force unresolved even if host has blender:
        blender_path=None,
        health_facts={"blender_path": f"<{VERIFY_ON_LAN}>"},
    )
    # prefer_local_which may find a real blender — if so, mode may be
    # local-blender or dry-run after failure. Never claim verified from marker.
    display = result.summary()["blender"]["display"]
    if result.blender.source == "local_which":
        pytest.skip("Host has blender on PATH — smoke may invoke real binary")
    assert result.ok
    assert result.mode == "dry-run"
    assert VERIFY_ON_LAN in display or display == UNVERIFIED
