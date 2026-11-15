"""Canonical video manifest storage and export."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
FIELDS = (
    "video_id",
    "title",
    "url",
    "duration",
    "upload_date",
    "playlist",
    "series",
    "topics",
    "topic_priority",
    "download_priority",
    "estimated_size",
    "actual_size",
    "video_downloaded",
    "transcript_downloaded",
    "verified",
    "transcript_type",
    "canonical_video_path",
    "transcript_path",
    "status",
    "error",
    "retryable",
    "last_attempt",
)
LIST_FIELDS = {"playlist", "topics"}


def _normalize_record(key: str, record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError(f"Video {key!r} must be an object")
    video_id = record.get("video_id") or key
    if not isinstance(video_id, str) or not video_id:
        raise ValueError("Every video must have a nonempty video_id")
    normalized = {field: [] if field in LIST_FIELDS else None for field in FIELDS}
    normalized.update(record)
    normalized["video_id"] = video_id
    for field in LIST_FIELDS:
        if normalized[field] is None:
            normalized[field] = []
        elif not isinstance(normalized[field], list):
            raise ValueError(f"Video {video_id!r} field {field!r} must be a list")
    return normalized


def _merge_records(existing: dict, incoming: dict) -> None:
    for field, value in incoming.items():
        if field in LIST_FIELDS:
            combined = existing[field]
            for item in value:
                if item not in combined:
                    combined.append(item)
        elif field not in existing or existing[field] is None or existing[field] == "":
            existing[field] = value


def _normalize_videos(videos: dict[str, dict]) -> dict[str, dict]:
    if not isinstance(videos, dict):
        raise ValueError("Manifest videos must be an object keyed by video ID")
    normalized: dict[str, dict] = {}
    for key, record in videos.items():
        item = _normalize_record(key, record)
        video_id = item["video_id"]
        if video_id in normalized:
            _merge_records(normalized[video_id], item)
        else:
            normalized[video_id] = item
    return normalized


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def load_manifest(path: Path) -> dict[str, dict]:
    """Load videos keyed by their canonical video ID; an absent file is empty."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "videos" not in payload:
        raise ValueError("Manifest must contain a videos object")
    return _normalize_videos(payload["videos"])


def save_manifest(path: Path, videos: dict[str, dict]) -> None:
    """Save complete normalized state without exposing a partial JSON file."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "videos": _normalize_videos(videos),
    }
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def export_csv(path: Path, videos: dict[str, dict]) -> None:
    """Export the same normalized records as UTF-8 CSV for inspection."""
    records = _normalize_videos(videos)
    extra_fields = sorted({key for record in records.values() for key in record} - set(FIELDS))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=[*FIELDS, *extra_fields])
    writer.writeheader()
    for record in records.values():
        writer.writerow(
            {
                field: "" if value is None else json.dumps(value, ensure_ascii=False)
                if isinstance(value, (list, dict, bool)) else value
                for field, value in record.items()
            }
        )
    _atomic_write(path, output.getvalue())
