"""U2 pack builder: fixture → README + 4 cardinals; missing front rejected."""

from __future__ import annotations

from pathlib import Path

import pytest

from composite3dgen.composites.select import MissingFrontError, select_canonical_angles
from composite3dgen.manifest import load_manifest
from composite3dgen.packs.builder import BUILD_PACK_PROVIDERS, MissingFrontPackError
from composite3dgen.pipeline import run_build_packs

from .conftest import write_labeled_jpeg


def test_fixture_folder_builds_packs_with_readme_and_cardinals(cardinal_job: Path) -> None:
    result = run_build_packs(cardinal_job, prefer_mwt1=True, force_executor="local")
    assert result.executor.name == "local"
    assert set(result.packs.providers) == set(BUILD_PACK_PROVIDERS)

    for provider in BUILD_PACK_PROVIDERS:
        pack = result.packs.pack_dirs[provider]
        assert (pack / "README.md").is_file()
        for angle in ("front", "left", "back", "right"):
            jpeg = pack / f"{angle}.jpg"
            assert jpeg.is_file(), f"{provider} missing {angle}.jpg"
            assert jpeg.stat().st_size > 0

    # Packs are identical byte-for-byte on cardinals.
    triposr = result.packs.pack_dirs["triposr"]
    for provider in ("tripo", "hi3d", "rodin"):
        other = result.packs.pack_dirs[provider]
        for angle in ("front", "left", "back", "right"):
            assert (triposr / f"{angle}.jpg").read_bytes() == (
                other / f"{angle}.jpg"
            ).read_bytes()


def test_missing_front_rejected(missing_front_job: Path) -> None:
    with pytest.raises((MissingFrontError, MissingFrontPackError, FileNotFoundError)):
        # Quality fill might assign an unlabeled leftover to front if any exist.
        # Our fixture only has named left/back/right AND hints omit front, but
        # leftover frames can still fill required angles by score. Force rejection
        # by removing all frames that could become front after named assignment.
        run_build_packs(missing_front_job, force_executor="local")


def test_missing_front_hard_reject_empty_selection(tmp_path: Path) -> None:
    """Explicit unit: selection with no front raises MissingFrontError."""
    frames = tmp_path / "frames"
    # Only one frame named "left" — after named assignment, no leftovers for front.
    write_labeled_jpeg(frames / "left.jpg", label="LEFT")
    write_labeled_jpeg(frames / "back.jpg", label="BACK")
    write_labeled_jpeg(frames / "right.jpg", label="RIGHT")

    manifest_path = tmp_path / "manifests" / "subject.manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        """
{
  "schema_version": "1.0.0",
  "subject_id": "no-front",
  "domain": "generic",
  "capture": {"source_type": "frames", "media_paths": ["frames"]},
  "angles": {
    "required": ["front", "left", "back", "right"],
    "optional": [],
    "hints": {"left": "left.jpg", "back": "back.jpg", "right": "right.jpg"}
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    manifest = load_manifest(manifest_path)
    frame_paths = sorted(frames.glob("*.jpg"))
    # Named assignment consumes all three; nothing left for front → reject.
    with pytest.raises(MissingFrontError):
        select_canonical_angles(frame_paths, manifest)


def test_cli_build_packs(cardinal_job: Path) -> None:
    from composite3dgen.cli import main

    code = main(
        [
            "build-packs",
            str(cardinal_job),
            "--executor",
            "local",
        ]
    )
    assert code == 0
    assert (cardinal_job / "build_packs" / "triposr" / "front.jpg").is_file()


def test_cli_missing_front_exits_nonzero(tmp_path: Path) -> None:
    from composite3dgen.cli import main

    frames = tmp_path / "frames"
    write_labeled_jpeg(frames / "left.jpg", label="LEFT")
    write_labeled_jpeg(frames / "back.jpg", label="BACK")
    write_labeled_jpeg(frames / "right.jpg", label="RIGHT")
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "subject.manifest.json").write_text(
        """
{
  "schema_version": "1.0.0",
  "subject_id": "cli-no-front",
  "domain": "generic",
  "capture": {"source_type": "frames", "media_paths": ["frames"]},
  "angles": {
    "required": ["front", "left", "back", "right"],
    "hints": {"left": "left.jpg", "back": "back.jpg", "right": "right.jpg"}
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    code = main(["build-packs", str(tmp_path), "--executor", "local"])
    assert code == 1
