"""Cardinal composites, quality scoring, and angle selection (U2)."""

from composite3dgen.composites.quality import FrameScore, score_frame, score_frames
from composite3dgen.composites.select import (
    AngleSelection,
    MissingFrontError,
    select_canonical_angles,
)

__all__ = [
    "AngleSelection",
    "FrameScore",
    "MissingFrontError",
    "score_frame",
    "score_frames",
    "select_canonical_angles",
]
