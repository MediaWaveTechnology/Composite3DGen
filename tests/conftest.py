"""Shared pytest helpers for Composite3DGen."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw


def write_labeled_jpeg(
    path: Path,
    *,
    label: str,
    size: tuple[int, int] = (320, 240),
    bg: tuple[int, int, int] = (245, 245, 245),
    fg: tuple[int, int, int] = (30, 30, 30),
    box: tuple[int, int, int, int] | None = None,
) -> Path:
    """Write a simple JPEG with a filled rect + label (for occupancy/sharpness)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    rect = box or (60, 40, size[0] - 60, size[1] - 40)
    draw.rectangle(rect, fill=fg)
    draw.text((70, 50), label, fill=(220, 220, 220))
    # A few high-contrast edges help sharpness scoring.
    draw.line((rect[0], rect[1], rect[2], rect[3]), fill=(255, 0, 0), width=2)
    draw.line((rect[2], rect[1], rect[0], rect[3]), fill=(0, 255, 0), width=2)
    img.save(path, format="JPEG", quality=95)
    return path


@pytest.fixture
def cardinal_job(tmp_path: Path) -> Path:
    """Job dir with named front/left/back/right frames + valid manifest."""
    frames = tmp_path / "frames"
    for angle in ("front", "left", "back", "right"):
        write_labeled_jpeg(frames / f"{angle}.jpg", label=angle.upper())

    manifests = tmp_path / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "subject.manifest.json").write_text(
        """
{
  "schema_version": "1.0.0",
  "subject_id": "test-cardinals",
  "domain": "generic",
  "capture": {
    "source_type": "frames",
    "media_paths": ["frames"]
  },
  "angles": {
    "required": ["front", "left", "back", "right"],
    "optional": ["top", "iso"],
    "hints": {
      "front": "front.jpg",
      "left": "left.jpg",
      "back": "back.jpg",
      "right": "right.jpg"
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def missing_front_job(tmp_path: Path) -> Path:
    """Job dir with left/back/right only — front intentionally absent."""
    frames = tmp_path / "frames"
    for angle in ("left", "back", "right"):
        write_labeled_jpeg(frames / f"{angle}.jpg", label=angle.upper())

    manifests = tmp_path / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "subject.manifest.json").write_text(
        """
{
  "schema_version": "1.0.0",
  "subject_id": "test-missing-front",
  "domain": "generic",
  "capture": {
    "source_type": "frames",
    "media_paths": ["frames"]
  },
  "angles": {
    "required": ["front", "left", "back", "right"],
    "optional": [],
    "hints": {
      "left": "left.jpg",
      "back": "back.jpg",
      "right": "right.jpg"
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return tmp_path
