"""Ingest photos/video frames (U2). Prefer ffmpeg on MWT1; controller local fallback."""

from composite3dgen.ingest.frames import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    IngestResult,
    collect_images,
    ingest_media,
)

__all__ = [
    "IMAGE_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "IngestResult",
    "collect_images",
    "ingest_media",
]
