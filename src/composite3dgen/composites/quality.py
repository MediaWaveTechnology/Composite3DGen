"""Frame quality scoring: sharpness (Laplacian variance) + occupancy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat


@dataclass(frozen=True)
class FrameScore:
    """Per-frame quality metrics used for canonical angle selection."""

    path: Path
    sharpness: float
    occupancy: float
    combined: float
    width: int
    height: int

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "path": str(self.path),
            "sharpness": self.sharpness,
            "occupancy": self.occupancy,
            "combined": self.combined,
            "width": self.width,
            "height": self.height,
        }


def _to_grayscale(image: Image.Image) -> Image.Image:
    if image.mode == "L":
        return image
    return image.convert("L")


def laplacian_sharpness(image: Image.Image) -> float:
    """Approximate Laplacian variance via Pillow edge filter + pixel variance.

    Higher values indicate sharper frames. Soft / motion-blurred frames score low.
    """
    gray = _to_grayscale(image)
    # FIND_EDGES approximates a Laplacian/Sobel edge magnitude map.
    edges = gray.filter(ImageFilter.FIND_EDGES)
    stats = ImageStat.Stat(edges)
    # Variance of edge response; ImageStat.var is a per-band list.
    return float(stats.var[0])


def occupancy_score(image: Image.Image, *, border: int = 8) -> float:
    """Fraction of pixels that differ from a border-derived background estimate.

    Assumes a relatively simple backdrop (see capture checklist). Returns a
    value in ``[0, 1]``.
    """
    gray = _to_grayscale(image)
    width, height = gray.size
    if width < border * 2 + 1 or height < border * 2 + 1:
        return 0.0

    # Flattened luminance samples (Pillow 14 removes Image.getdata).
    if hasattr(gray, "get_flattened_data"):
        pixels = list(gray.get_flattened_data())
    else:  # pragma: no cover — older Pillow
        pixels = list(gray.getdata())
    # Sample border ring for background estimate.
    bg_samples: list[int] = []
    for y in range(height):
        row = y * width
        for x in range(width):
            if x < border or y < border or x >= width - border or y >= height - border:
                bg_samples.append(int(pixels[row + x]))
    if not bg_samples:
        return 0.0
    bg = sorted(bg_samples)[len(bg_samples) // 2]
    threshold = 28
    subject = sum(1 for p in pixels if abs(int(p) - bg) > threshold)
    return subject / float(len(pixels))


def score_frame(path: Path | str) -> FrameScore:
    """Score a single image for sharpness and subject occupancy."""
    image_path = Path(path)
    with Image.open(image_path) as img:
        img.load()
        sharpness = laplacian_sharpness(img)
        occupancy = occupancy_score(img)
        width, height = img.size
    # Combined: prioritize sharpness, with occupancy as a soft prior.
    combined = sharpness * (0.35 + 0.65 * occupancy)
    return FrameScore(
        path=image_path,
        sharpness=sharpness,
        occupancy=occupancy,
        combined=combined,
        width=width,
        height=height,
    )


def score_frames(paths: list[Path]) -> list[FrameScore]:
    """Score many frames; returns scores in input order."""
    return [score_frame(p) for p in paths]
