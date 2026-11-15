"""Collect one video's timed public subtitles with explicit source labels."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from .transcripts import parse_subtitles


_LANGUAGES = ("zh-Hant", "zh-TW", "zh-Hans", "zh-CN", "zh", "en")
_FORMATS = ("vtt", "srt")


def _run_yt_dlp(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=300)


def _choose_track(metadata: dict[str, Any]) -> tuple[str, str, str] | None:
    for field, kind in (("subtitles", "official"), ("automatic_captions", "auto")):
        tracks = metadata.get(field) or {}
        for language in _LANGUAGES:
            entries = tracks.get(language) or []
            for extension in _FORMATS:
                if any(entry.get("ext") == extension for entry in entries):
                    return language, extension, kind
    return None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def collect_subtitles(record: dict[str, Any], *, transcript_dir: Path) -> dict[str, Any]:
    """Collect subtitles if available; leave an actionable status otherwise."""
    updated = deepcopy(record)
    video_id = updated.get("video_id")
    url = updated.get("url")
    if not video_id or not url:
        raise ValueError("record needs video_id and url")
    if updated.get("transcript_downloaded") and updated.get("transcript_chunks_path"):
        chunks_path = Path(updated["transcript_chunks_path"])
        transcript_path = Path(updated.get("transcript_path") or "")
        if chunks_path.is_file() and transcript_path.is_file():
            return updated

    updated.update(
        transcript_downloaded=False,
        transcript_type="missing",
        transcript_path=None,
        transcript_chunks_path=None,
        transcript_retryable=False,
    )
    try:
        metadata_result = _run_yt_dlp(["yt-dlp", "--no-playlist", "--skip-download", "-J", url])
    except (OSError, subprocess.TimeoutExpired) as exc:
        updated.update(transcript_status="FETCH_FAILED", transcript_error=str(exc), transcript_retryable=True)
        return updated
    if metadata_result.returncode != 0:
        updated.update(
            transcript_status="FETCH_FAILED",
            transcript_error=(metadata_result.stderr or metadata_result.stdout or "yt-dlp failed")[-2000:],
            transcript_retryable=True,
        )
        return updated
    try:
        metadata = json.loads(metadata_result.stdout)
    except (ValueError, TypeError) as exc:
        updated.update(transcript_status="FETCH_FAILED", transcript_error=str(exc), transcript_retryable=True)
        return updated
    track = _choose_track(metadata)
    if track is None:
        updated.update(transcript_status="ASR_NEEDED", transcript_error=None)
        return updated
    language, extension, transcript_type = track
    transcript_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "yt-dlp", "--no-playlist", "--skip-download", "--no-progress",
        "--write-subs" if transcript_type == "official" else "--write-auto-subs",
        "--sub-langs", language, "--sub-format", extension,
        "--output", str(transcript_dir / "%(id)s.%(ext)s"), url,
    ]
    try:
        result = _run_yt_dlp(command)
    except (OSError, subprocess.TimeoutExpired) as exc:
        updated.update(transcript_status="FETCH_FAILED", transcript_error=str(exc), transcript_retryable=True)
        return updated
    if result.returncode != 0:
        updated.update(
            transcript_status="FETCH_FAILED",
            transcript_error=(result.stderr or result.stdout or "yt-dlp failed")[-2000:],
            transcript_retryable=True,
        )
        return updated
    raw_path = transcript_dir / f"{video_id}.{language}.{extension}"
    if not raw_path.is_file() or raw_path.stat().st_size == 0:
        updated.update(
            transcript_status="FETCH_FAILED",
            transcript_error=f"expected subtitle file missing or empty: {raw_path}",
            transcript_retryable=True,
        )
        return updated
    try:
        chunks = parse_subtitles(
            raw_path.read_text(encoding="utf-8-sig"),
            format=extension,
            video_id=video_id,
            title=updated.get("title") or metadata.get("title") or "",
            source_url=url,
            transcript_type=transcript_type,
        )
    except (UnicodeError, ValueError) as exc:
        updated.update(transcript_status="PARSE_FAILED", transcript_error=str(exc), transcript_retryable=True)
        return updated
    if not chunks:
        updated.update(
            transcript_status="PARSE_FAILED", transcript_error="no timed subtitle cues", transcript_retryable=True
        )
        return updated
    chunks_path = transcript_dir / f"{video_id}.chunks.json"
    _atomic_json(chunks_path, {"video_id": video_id, "language": language, "transcript_type": transcript_type, "chunks": chunks})
    updated.update(
        transcript_downloaded=True,
        transcript_type=transcript_type,
        transcript_path=str(raw_path),
        transcript_chunks_path=str(chunks_path),
        transcript_status="READY",
        transcript_error=None,
        transcript_retryable=False,
    )
    return updated
