"""ffmpeg helpers for video frame extraction.

Happy path: run on **MWT1** (large media I/O next to GPU jobs). Controller
local fallback is supported when MWT1 is unreachable (degraded mode).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    """Raised when ffmpeg is missing or frame extraction fails."""


def ffmpeg_available() -> bool:
    """Return True if an ``ffmpeg`` binary is on PATH."""
    return shutil.which("ffmpeg") is not None


def extract_frames(
    video: Path,
    out_dir: Path,
    *,
    fps: float = 2.0,
    prefix: str = "frame",
) -> list[Path]:
    """Extract JPEG frames from ``video`` into ``out_dir`` via ffmpeg.

    Uses ``-vf fps=<fps>`` and writes ``{prefix}_%04d.jpg``. Raises
    :class:`FFmpegError` if ffmpeg is unavailable or the process fails.
    """
    if not video.is_file():
        raise FFmpegError(f"Video not found: {video}")
    if not ffmpeg_available():
        raise FFmpegError(
            "ffmpeg not found on PATH. Install ffmpeg on MWT1 (preferred) "
            "or the controller for local degraded-mode extract."
        )
    if fps <= 0:
        raise FFmpegError(f"fps must be > 0, got {fps}")

    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / f"{prefix}_%04d.jpg")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps={fps}",
        pattern,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise FFmpegError(f"ffmpeg failed for {video}: {detail}")

    frames = sorted(out_dir.glob(f"{prefix}_*.jpg"))
    if not frames:
        raise FFmpegError(f"ffmpeg produced no frames for {video}")
    return frames
