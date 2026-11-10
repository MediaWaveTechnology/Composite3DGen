"""Collect stills and extract video frames into a job ``frames/`` directory."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from composite3dgen.ingest.ffmpeg import FFmpegError, extract_frames, ffmpeg_available
from composite3dgen.manifest import SubjectManifest

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


@dataclass
class IngestResult:
    """Outcome of ingesting media into ``job_dir/frames``."""

    frames_dir: Path
    frames: list[Path] = field(default_factory=list)
    copied_stills: list[Path] = field(default_factory=list)
    extracted_from_video: list[Path] = field(default_factory=list)
    executor_name: str = "local"
    ffmpeg_used: bool = False
    notes: list[str] = field(default_factory=list)


def collect_images(root: Path) -> list[Path]:
    """Return sorted image paths under ``root`` (file or directory)."""
    if root.is_file():
        if root.suffix.lower() in IMAGE_EXTENSIONS:
            return [root]
        return []
    if not root.is_dir():
        return []
    images: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
    return images


def _resolve_media_paths(job_dir: Path, manifest: SubjectManifest) -> list[Path]:
    if manifest.media_paths:
        resolved: list[Path] = []
        for raw in manifest.media_paths:
            path = Path(raw)
            if not path.is_absolute():
                path = job_dir / path
            resolved.append(path)
        return resolved

    # Convention fallbacks when media_paths omitted.
    candidates = [
        job_dir / "media",
        job_dir / "photos",
        job_dir / "video",
        job_dir / "frames",
        job_dir / "input",
    ]
    return [p for p in candidates if p.exists()]


def ingest_media(
    job_dir: Path,
    manifest: SubjectManifest,
    *,
    executor_name: str = "local",
    frames_subdir: str = "frames",
) -> IngestResult:
    """Ingest photos and/or video into ``job_dir/frames``.

    Prefers ffmpeg when available (MWT1 happy path). Still copies work without
    ffmpeg. Video without ffmpeg raises :class:`FFmpegError`.
    """
    job_dir = Path(job_dir)
    frames_dir = job_dir / frames_subdir
    frames_dir.mkdir(parents=True, exist_ok=True)

    result = IngestResult(frames_dir=frames_dir, executor_name=executor_name)
    media_paths = _resolve_media_paths(job_dir, manifest)
    if not media_paths:
        # Already-populated frames dir is valid (source_type=frames).
        existing = collect_images(frames_dir)
        if existing:
            result.frames = existing
            result.notes.append("Using existing frames/ (no media_paths)")
            return result
        raise FileNotFoundError(
            f"No media found under {job_dir}. Set capture.media_paths or add "
            "media/, photos/, video/, or frames/."
        )

    fps = manifest.frame_fps
    seen: set[str] = set()

    for media in media_paths:
        if media.is_dir():
            for image in collect_images(media):
                # Skip copying frames onto themselves when media_paths points at frames/.
                if image.resolve().parent == frames_dir.resolve():
                    if image.name not in seen:
                        result.frames.append(image)
                        seen.add(image.name)
                    continue
                dest = frames_dir / image.name
                if dest.name in seen:
                    dest = frames_dir / f"{media.name}_{image.name}"
                if image.resolve() != dest.resolve():
                    shutil.copy2(image, dest)
                    result.copied_stills.append(dest)
                result.frames.append(dest)
                seen.add(dest.name)
            continue

        if not media.is_file():
            result.notes.append(f"Skipping missing media path: {media}")
            continue

        suffix = media.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            dest = frames_dir / media.name
            if dest.name in seen:
                dest = frames_dir / f"{media.stem}_dup{media.suffix}"
            shutil.copy2(media, dest)
            result.copied_stills.append(dest)
            result.frames.append(dest)
            seen.add(dest.name)
            continue

        if suffix in VIDEO_EXTENSIONS:
            if not ffmpeg_available():
                raise FFmpegError(
                    f"Video ingest requires ffmpeg ({media}). Prefer MWT1; "
                    "install ffmpeg on the controller for degraded mode."
                )
            extracted = extract_frames(
                media,
                frames_dir,
                fps=fps,
                prefix=f"{media.stem}_frame",
            )
            result.ffmpeg_used = True
            result.extracted_from_video.extend(extracted)
            for frame in extracted:
                if frame.name not in seen:
                    result.frames.append(frame)
                    seen.add(frame.name)
            continue

        result.notes.append(f"Unsupported media type skipped: {media}")

    # De-dupe while preserving order.
    unique: list[Path] = []
    names: set[str] = set()
    for frame in result.frames:
        key = str(frame.resolve())
        if key in names:
            continue
        names.add(key)
        unique.append(frame)
    result.frames = unique

    if not result.frames:
        raise FileNotFoundError(f"Ingest produced no frames under {frames_dir}")

    prefer_note = (
        "Executor: MWT1 preferred for ffmpeg ingest when healthy; "
        f"this run used '{executor_name}'."
    )
    result.notes.append(prefer_note)
    return result
