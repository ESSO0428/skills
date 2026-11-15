"""Verify one canonical downloaded video before marking it complete."""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    reason: str | None
    duration: float | None
    size_bytes: int


def _probe_duration(payload: dict) -> float | None:
    candidates = [payload["format"].get("duration")]
    candidates.extend(
        stream.get("duration")
        for stream in payload["streams"]
        if stream.get("codec_type") == "video"
    )
    for candidate in candidates:
        try:
            duration = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(duration) and duration > 0:
            return duration
    return None


def verify_video(
    path: Path,
    expected_id: str,
    expected_duration: float | None,
    ffprobe: str | Path,
) -> VerificationResult:
    """Require a nonempty canonical file and readable video stream and duration."""
    if not path.is_file():
        return VerificationResult(False, "file_missing", None, 0)
    try:
        size_bytes = path.stat().st_size
    except OSError:
        return VerificationResult(False, "file_unreadable", None, 0)
    if size_bytes <= 0:
        return VerificationResult(False, "empty_file", None, size_bytes)
    if path.stem != expected_id or not path.suffix or path.suffix.lower() in {".part", ".tmp", ".ytdl"}:
        return VerificationResult(False, "filename_mismatch", None, size_bytes)
    if expected_duration is not None and (
        not math.isfinite(expected_duration) or expected_duration <= 0
    ):
        return VerificationResult(False, "expected_duration_invalid", None, size_bytes)

    try:
        completed = subprocess.run(
            [str(ffprobe), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError:
        return VerificationResult(False, "ffprobe_missing", None, size_bytes)
    except (OSError, subprocess.TimeoutExpired):
        return VerificationResult(False, "ffprobe_failed", None, size_bytes)
    if completed.returncode != 0:
        return VerificationResult(False, "ffprobe_failed", None, size_bytes)
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return VerificationResult(False, "ffprobe_invalid_json", None, size_bytes)
    if not isinstance(payload, dict):
        return VerificationResult(False, "ffprobe_invalid_json", None, size_bytes)
    format_data = payload.get("format")
    streams = payload.get("streams")
    if not isinstance(format_data, dict) or not format_data.get("format_name"):
        return VerificationResult(False, "container_unreadable", None, size_bytes)
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams
    ):
        return VerificationResult(False, "no_video_stream", None, size_bytes)

    duration = _probe_duration(payload)
    if duration is None:
        reason = "duration_missing" if expected_duration is not None else "duration_invalid"
        return VerificationResult(False, reason, None, size_bytes)
    if expected_duration is not None:
        tolerance = max(30.0, expected_duration * 0.05)
        if abs(duration - expected_duration) > tolerance:
            return VerificationResult(False, "duration_mismatch", duration, size_bytes)
    return VerificationResult(True, None, duration, size_bytes)
