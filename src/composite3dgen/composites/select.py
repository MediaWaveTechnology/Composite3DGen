"""Select canonical front/left/back/right (+ optional top/iso) from scored frames."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from composite3dgen.composites.quality import FrameScore, score_frames
from composite3dgen.manifest import SubjectManifest
from composite3dgen.manifest.loader import ALL_ANGLES, CARDINAL_ANGLES

ANGLE_PATTERN = re.compile(
    r"(?:^|[_\-./\s])(front|left|back|right|top|iso)(?:$|[_\-./\s])",
    re.IGNORECASE,
)


class MissingFrontError(ValueError):
    """Raised when a pack cannot include a canonical front view."""


@dataclass
class AngleSelection:
    """Chosen frames for each angle label."""

    angles: dict[str, Path]
    scores: dict[str, FrameScore] = field(default_factory=dict)
    rejected: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def front(self) -> Path | None:
        return self.angles.get("front")

    def require_front(self) -> Path:
        front = self.front
        if front is None:
            raise MissingFrontError(
                "Canonical front view is missing; packs are rejected without front."
            )
        return front


def detect_angle_hint(path: Path) -> str | None:
    """Return an angle label if the filename/path encodes one."""
    text = str(path).replace("\\", "/")
    match = ANGLE_PATTERN.search(text)
    if not match:
        # Also accept exact stem match: front.jpg
        stem = path.stem.lower()
        if stem in ALL_ANGLES:
            return stem
        return None
    return match.group(1).lower()


def _match_hint(frames: list[Path], hint: str) -> Path | None:
    hint_path = Path(hint)
    for frame in frames:
        if frame.name == hint_path.name or frame.stem == hint_path.stem:
            return frame
        if hint in str(frame):
            return frame
    candidate = hint_path if hint_path.is_file() else None
    return candidate


def select_canonical_angles(
    frames: list[Path],
    manifest: SubjectManifest | None = None,
    *,
    scores: list[FrameScore] | None = None,
) -> AngleSelection:
    """Choose canonical angles from frames via hints, names, then quality.

    Selection order per angle:
    1. Explicit ``angles.hints`` in the manifest
    2. Filename angle tokens (``front.jpg``, ``view_left_01.png``)
    3. Highest remaining ``combined`` quality score for unfilled required angles

    Always fails closed on missing **front** via :meth:`AngleSelection.require_front`.
    """
    if not frames:
        raise MissingFrontError("No frames available for angle selection")

    scored = scores if scores is not None else score_frames(frames)
    by_path = {s.path.resolve(): s for s in scored}
    remaining = {p.resolve(): p for p in frames}
    selection = AngleSelection(angles={})

    required = list(manifest.angles_required) if manifest else list(CARDINAL_ANGLES)
    optional = list(manifest.angles_optional) if manifest else ["top", "iso"]
    if "front" not in required:
        required = ["front", *required]
    wanted = list(dict.fromkeys([*required, *optional]))

    hints = dict(manifest.angle_hints) if manifest else {}

    # 1) Explicit hints
    for angle, hint in hints.items():
        angle_l = angle.lower()
        if angle_l not in wanted:
            continue
        match = _match_hint(list(remaining.values()), hint)
        if match is None:
            selection.notes.append(f"Hint for {angle_l} not found: {hint}")
            continue
        key = match.resolve()
        if key not in remaining:
            continue
        selection.angles[angle_l] = remaining.pop(key)
        if key in by_path:
            selection.scores[angle_l] = by_path[key]

    # 2) Filename tokens
    named: dict[str, list[Path]] = {a: [] for a in ALL_ANGLES}
    for path in list(remaining.values()):
        label = detect_angle_hint(path)
        if label and label in wanted and label not in selection.angles:
            named[label].append(path)

    for angle in wanted:
        if angle in selection.angles:
            continue
        candidates = named.get(angle) or []
        if not candidates:
            continue
        # Prefer highest combined among named candidates.
        best = max(
            candidates,
            key=lambda p: by_path.get(p.resolve(), FrameScore(p, 0, 0, 0, 0, 0)).combined,
        )
        key = best.resolve()
        if key in remaining:
            selection.angles[angle] = remaining.pop(key)
            if key in by_path:
                selection.scores[angle] = by_path[key]

    # 3) Fill remaining required angles by quality (optional only if plenty left)
    leftover_scores = sorted(
        (by_path[k] for k in remaining if k in by_path),
        key=lambda s: s.combined,
        reverse=True,
    )
    for angle in required:
        if angle in selection.angles:
            continue
        if not leftover_scores:
            selection.rejected.append(f"No frame available for required angle: {angle}")
            continue
        best = leftover_scores.pop(0)
        key = best.path.resolve()
        selection.angles[angle] = remaining.pop(key)
        selection.scores[angle] = best
        selection.notes.append(
            f"Assigned '{angle}' by quality score to {best.path.name} "
            f"(combined={best.combined:.2f})"
        )

    for angle in optional:
        if angle in selection.angles or not leftover_scores:
            continue
        best = leftover_scores.pop(0)
        key = best.path.resolve()
        if key not in remaining:
            continue
        selection.angles[angle] = remaining.pop(key)
        selection.scores[angle] = best

    selection.require_front()
    return selection
