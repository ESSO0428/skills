"""Download one planned YouTube video without compromising disk or state safety."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .planning import GIB, estimate_bytes, topic_is_safe
from .verify import verify_video


def _run_yt_dlp(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=7200)


def _canonical_candidates(video_dir: Path, video_id: str) -> list[Path]:
    return sorted(
        path
        for path in video_dir.glob(f"{video_id}.*")
        if path.is_file() and path.stem == video_id and path.suffix.lower() not in {".part", ".tmp", ".ytdl"}
    )


def download_one(
    record: dict[str, Any],
    *,
    video_dir: Path,
    ffprobe: str | Path,
    min_free_bytes: int = 30 * GIB,
    safety_reserve_percent: float = 0.25,
    margin: float = 1.5,
    max_height: int = 720,
) -> dict[str, Any]:
    """Return updated state; caller atomically saves it after each video."""
    updated = deepcopy(record)
    updated.setdefault("video_downloaded", False)
    updated.setdefault("verified", False)
    video_id = updated.get("video_id")
    url = updated.get("url")
    if not video_id or not url:
        raise ValueError("record needs video_id and url")
    if margin < 1 or not 0 <= safety_reserve_percent < 1 or max_height <= 0:
        raise ValueError("invalid download safety settings")

    if updated.get("verified") and updated.get("canonical_video_path"):
        existing = Path(updated["canonical_video_path"])
        check = verify_video(existing, video_id, updated.get("duration"), ffprobe)
        if check.ok:
            updated.update(
                status="VERIFIED",
                error=None,
                retryable=False,
                video_downloaded=True,
                actual_size=check.size_bytes,
            )
            return updated
        updated["verified"] = False

    free_bytes = shutil.disk_usage(video_dir if video_dir.exists() else video_dir.parent).free
    reserve_bytes = max(min_free_bytes, math.ceil(free_bytes * safety_reserve_percent))
    estimate = estimate_bytes(updated)
    if not topic_is_safe(free_bytes, reserve_bytes, estimate, margin):
        updated.update(
            status="INSUFFICIENT_STORAGE",
            error=f"free={free_bytes}, reserve={reserve_bytes}, estimated={estimate}, margin={margin}",
            retryable=True,
            verified=False,
        )
        return updated

    video_dir.mkdir(parents=True, exist_ok=True)
    updated["last_attempt"] = datetime.now(timezone.utc).isoformat()
    ffprobe_path = Path(ffprobe)
    command = [
        "yt-dlp",
        "--no-playlist",
        "--continue",
        "--no-progress",
        "--retries",
        "3",
        "--fragment-retries",
        "3",
        "--ffmpeg-location",
        str(ffprobe_path.parent),
        "--format",
        f"bv*[height<={max_height}]+ba/b[height<={max_height}]",
        "--merge-output-format",
        "mp4",
        "--output",
        str(video_dir / "%(id)s.%(ext)s"),
        url,
    ]
    if shutil.which("node"):
        command[4:4] = ["--js-runtimes", "node"]
    try:
        result = _run_yt_dlp(command)
    except (OSError, subprocess.TimeoutExpired) as exc:
        updated.update(status="DOWNLOAD_FAILED", error=str(exc), retryable=True, verified=False)
        return updated
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "yt-dlp failed").strip()[-2000:]
        permanent = any(marker in error.lower() for marker in ("private video", "video has been removed"))
        updated.update(
            status="UNAVAILABLE" if permanent else "DOWNLOAD_FAILED",
            error=error,
            retryable=not permanent,
            verified=False,
        )
        return updated

    candidates = _canonical_candidates(video_dir, video_id)
    if len(candidates) != 1:
        updated.update(
            status="VERIFY_FAILED",
            error=f"expected one canonical file, found {len(candidates)}",
            retryable=True,
            verified=False,
        )
        return updated

    candidate = candidates[0]
    check = verify_video(candidate, video_id, updated.get("duration"), ffprobe)
    updated.update(
        canonical_video_path=str(candidate),
        actual_size=check.size_bytes,
        video_downloaded=True,
        verified=check.ok,
        status="VERIFIED" if check.ok else "VERIFY_FAILED",
        error=None if check.ok else check.reason,
        retryable=not check.ok,
    )
    return updated
