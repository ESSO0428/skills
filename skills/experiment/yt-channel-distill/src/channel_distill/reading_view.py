"""Create low-token reading copies while keeping a reversible provenance map."""

from __future__ import annotations

from typing import Any


_REQUIRED = ("chunk_id", "text", "start_seconds", "end_seconds", "source_url", "transcript_type")


def build_reading_view(video_id: str, chunks: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Return timestamp-free Markdown and a separate exact anchor map."""
    if not video_id or not chunks:
        raise ValueError("a video ID and at least one source chunk are required")
    lines = [f"# Reading view: {video_id}", "", "> This file deliberately omits timestamps."]
    anchors: dict[str, dict[str, Any]] = {}
    for position, chunk in enumerate(chunks, start=1):
        if any(field not in chunk for field in _REQUIRED):
            raise ValueError("source chunk lacks reversible provenance")
        chunk_id = chunk["chunk_id"]
        if not isinstance(chunk_id, str) or not chunk_id.startswith(f"{video_id}:"):
            raise ValueError("source chunk does not match requested video")
        text = chunk["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("source chunk has no reading text")
        segment_id = f"S{position:04d}"
        lines.extend(["", f"## {segment_id}", "", text.strip()])
        anchors[segment_id] = {
            field: chunk[field]
            for field in ("chunk_id", "start_seconds", "end_seconds", "source_url", "transcript_type")
        }
    return "\n".join(lines) + "\n", {
        "video_id": video_id,
        "scope": "Reversible map for a timestamp-free reading view; anchors are source chunks, not semantic claims.",
        "anchors": anchors,
    }
