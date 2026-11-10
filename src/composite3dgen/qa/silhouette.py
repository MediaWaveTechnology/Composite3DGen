"""Silhouette overlay scoring for QA gates (U7).

Compares a reference silhouette (capture / expected outline) against a
rendered candidate (Blender/MWT1 QA still). Offline-mockable via file paths
or in-memory PIL images — no live Blender / MWT1 required for unit tests.

Score = IoU of binary masks after thresholding. Coverage = intersection /
reference foreground. Gate fails when IoU or coverage fall below thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Literal, Sequence

from PIL import Image, ImageOps

SilhouetteSource = Path | str | Image.Image | BinaryIO

DEFAULT_IOU_THRESHOLD = 0.55
DEFAULT_COVERAGE_THRESHOLD = 0.70
DEFAULT_THRESHOLD = 128  # pixels darker than this count as foreground


@dataclass(frozen=True)
class SilhouetteScore:
    """One reference↔candidate silhouette comparison."""

    axis: str
    iou: float
    coverage: float
    reference_fg_pixels: int
    candidate_fg_pixels: int
    intersection_pixels: int
    union_pixels: int
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "iou": self.iou,
            "coverage": self.coverage,
            "reference_fg_pixels": self.reference_fg_pixels,
            "candidate_fg_pixels": self.candidate_fg_pixels,
            "intersection_pixels": self.intersection_pixels,
            "union_pixels": self.union_pixels,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SilhouetteGateResult:
    """Aggregate silhouette gate across one or more axes."""

    scores: tuple[SilhouetteScore, ...]
    passed: bool
    iou_threshold: float
    coverage_threshold: float
    notes: tuple[str, ...] = ()

    @property
    def failed_axes(self) -> list[str]:
        return [s.axis for s in self.scores if not s.passed]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "iou_threshold": self.iou_threshold,
            "coverage_threshold": self.coverage_threshold,
            "failed_axes": self.failed_axes,
            "scores": [s.as_dict() for s in self.scores],
            "notes": list(self.notes),
        }


def _open_image(source: SilhouetteSource) -> Image.Image:
    if isinstance(source, Image.Image):
        return source.convert("L")
    if isinstance(source, (Path, str)):
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Silhouette image not found: {path}")
        with Image.open(path) as img:
            return img.convert("L")
    # file-like
    with Image.open(source) as img:
        return img.convert("L")


def to_binary_mask(
    source: SilhouetteSource,
    *,
    threshold: int = DEFAULT_THRESHOLD,
    invert: bool | None = None,
    size: tuple[int, int] | None = None,
) -> Image.Image:
    """Convert an image to a binary L-mode mask (255 = foreground).

    Silhouette stills from Blender are typically black subject on white
    background. Capture references may be the inverse — when ``invert`` is
    None we auto-detect by mean luminance (bright mean → dark=foreground).
    """
    gray = _open_image(source)
    if size is not None and gray.size != size:
        gray = gray.resize(size, Image.Resampling.NEAREST)

    if invert is None:
        # Bright background with dark silhouette → invert so FG=255.
        pixels = list(gray.get_flattened_data())
        invert = (sum(pixels) / max(1, len(pixels))) > threshold

    if invert:
        gray = ImageOps.invert(gray)

    return gray.point(lambda p: 255 if p >= threshold else 0, mode="L")


def score_silhouette_pair(
    reference: SilhouetteSource,
    candidate: SilhouetteSource,
    *,
    axis: str = "front",
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
    threshold: int = DEFAULT_THRESHOLD,
) -> SilhouetteScore:
    """Score one reference/candidate silhouette pair (mockable offline)."""
    ref_img = _open_image(reference)
    cand_img = _open_image(candidate)
    # Align candidate to reference size for overlay comparison.
    size = ref_img.size
    ref_mask = to_binary_mask(ref_img, threshold=threshold, size=size)
    cand_mask = to_binary_mask(cand_img, threshold=threshold, size=size)

    ref_px = list(ref_mask.get_flattened_data())
    cand_px = list(cand_mask.get_flattened_data())
    ref_fg = sum(1 for p in ref_px if p)
    cand_fg = sum(1 for p in cand_px if p)
    intersection = sum(1 for a, b in zip(ref_px, cand_px) if a and b)
    union = sum(1 for a, b in zip(ref_px, cand_px) if a or b)

    iou = (intersection / union) if union else 0.0
    coverage = (intersection / ref_fg) if ref_fg else 0.0
    passed = iou >= iou_threshold and coverage >= coverage_threshold
    detail = (
        f"iou={iou:.3f} (min {iou_threshold:.3f}); "
        f"coverage={coverage:.3f} (min {coverage_threshold:.3f})"
    )
    if not passed:
        detail += " — silhouette gate FAIL"
    return SilhouetteScore(
        axis=axis,
        iou=iou,
        coverage=coverage,
        reference_fg_pixels=ref_fg,
        candidate_fg_pixels=cand_fg,
        intersection_pixels=intersection,
        union_pixels=union,
        passed=passed,
        detail=detail,
    )


def run_silhouette_gate(
    pairs: Sequence[tuple[str, SilhouetteSource, SilhouetteSource]],
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
    threshold: int = DEFAULT_THRESHOLD,
) -> SilhouetteGateResult:
    """Run silhouette overlay gate over ``(axis, reference, candidate)`` pairs."""
    notes: list[str] = []
    if not pairs:
        notes.append("No silhouette pairs provided — gate fails closed.")
        return SilhouetteGateResult(
            scores=(),
            passed=False,
            iou_threshold=iou_threshold,
            coverage_threshold=coverage_threshold,
            notes=tuple(notes),
        )

    scores: list[SilhouetteScore] = []
    for axis, reference, candidate in pairs:
        scores.append(
            score_silhouette_pair(
                reference,
                candidate,
                axis=axis,
                iou_threshold=iou_threshold,
                coverage_threshold=coverage_threshold,
                threshold=threshold,
            )
        )
    passed = all(s.passed for s in scores)
    if not passed:
        notes.append(
            "Silhouette coverage/IoU below threshold on: "
            + ", ".join(s.axis for s in scores if not s.passed)
        )
    else:
        notes.append("All silhouette axes passed overlay thresholds.")
    return SilhouetteGateResult(
        scores=tuple(scores),
        passed=passed,
        iou_threshold=iou_threshold,
        coverage_threshold=coverage_threshold,
        notes=tuple(notes),
    )


def discover_silhouette_pairs(
    job_dir: Path,
    *,
    axes: Sequence[str] = ("front", "left", "back", "right"),
    reference_dir: Path | str | None = None,
    verification_dir: Path | str | None = None,
) -> list[tuple[str, Path, Path]]:
    """Discover reference/candidate silhouette files under a job directory.

    References default to ``verification/reference-silhouette-<axis>.png`` or
    ``frames/silhouette-<axis>.png``. Candidates default to Blender QA stills
    ``out/blender/verification/*-silhouette-<axis>.png``.
    """
    job_dir = Path(job_dir)
    ref_root = Path(reference_dir) if reference_dir else None
    ver_root = (
        Path(verification_dir)
        if verification_dir
        else job_dir / "out" / "blender" / "verification"
    )
    pairs: list[tuple[str, Path, Path]] = []
    for axis in axes:
        candidate: Path | None = None
        if ver_root.is_dir():
            matches = sorted(ver_root.glob(f"*-silhouette-{axis}.png"))
            if matches:
                candidate = matches[0]
        if candidate is None:
            continue

        reference: Path | None = None
        candidates_ref = []
        if ref_root is not None:
            candidates_ref.append(ref_root / f"silhouette-{axis}.png")
            candidates_ref.append(ref_root / f"reference-silhouette-{axis}.png")
        candidates_ref.extend(
            [
                job_dir / "verification" / f"reference-silhouette-{axis}.png",
                job_dir / "verification" / f"silhouette-{axis}.png",
                job_dir / "frames" / f"silhouette-{axis}.png",
            ]
        )
        for path in candidates_ref:
            if path.is_file():
                reference = path
                break
        if reference is None:
            continue
        pairs.append((axis, reference, candidate))
    return pairs


AxisName = Literal["front", "left", "back", "right", "top", "iso"]


__all__ = [
    "DEFAULT_COVERAGE_THRESHOLD",
    "DEFAULT_IOU_THRESHOLD",
    "DEFAULT_THRESHOLD",
    "SilhouetteGateResult",
    "SilhouetteScore",
    "SilhouetteSource",
    "discover_silhouette_pairs",
    "run_silhouette_gate",
    "score_silhouette_pair",
    "to_binary_mask",
]
