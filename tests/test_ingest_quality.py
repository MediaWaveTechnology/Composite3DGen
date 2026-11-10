"""Ingest + quality scoring smoke tests."""

from __future__ import annotations

from pathlib import Path

from composite3dgen.composites.quality import score_frame
from composite3dgen.ingest import collect_images, ingest_media
from composite3dgen.manifest import load_manifest

from .conftest import write_labeled_jpeg


def test_collect_and_ingest_stills(tmp_path: Path) -> None:
    photos = tmp_path / "photos"
    write_labeled_jpeg(photos / "a.jpg", label="A")
    write_labeled_jpeg(photos / "b.jpg", label="B")
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "subject.manifest.json").write_text(
        """
{
  "schema_version": "1.0.0",
  "subject_id": "ingest-smoke",
  "domain": "generic",
  "capture": {"source_type": "photos", "media_paths": ["photos"]}
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    manifest = load_manifest(manifests / "subject.manifest.json")
    result = ingest_media(tmp_path, manifest, executor_name="local")
    assert len(result.frames) == 2
    assert all(p.parent == result.frames_dir for p in result.frames)
    assert collect_images(result.frames_dir)


def test_score_frame_positive(tmp_path: Path) -> None:
    path = write_labeled_jpeg(tmp_path / "sharp.jpg", label="SHARP")
    score = score_frame(path)
    assert score.sharpness > 0
    assert 0.0 <= score.occupancy <= 1.0
    assert score.combined >= 0
