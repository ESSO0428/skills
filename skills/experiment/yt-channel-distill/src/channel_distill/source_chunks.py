"""Group timed transcript cues at observed pauses and known topic boundaries."""

from __future__ import annotations

from typing import Any, Iterable


PROVENANCE_FIELDS = ("video_id", "title", "source_url", "transcript_type")


def order_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a timestamp-ordered copy for ASR overlap-window artifacts.

    Raw transcripts remain untouched. Invalid timestamps are left for
    ``group_cues`` to reject with its more specific validation error.
    """
    if not all(
        isinstance(item.get("start_seconds"), (int, float))
        and isinstance(item.get("end_seconds"), (int, float))
        for item in cues
    ):
        return list(cues)
    indexed = list(enumerate(cues))
    ordered = sorted(
        indexed,
        key=lambda pair: (pair[1]["start_seconds"], pair[1]["end_seconds"], pair[0]),
    )
    return [dict(item) for _, item in ordered]


def group_cues(
    cues: list[dict[str, Any]],
    *,
    max_duration_seconds: float = 90,
    max_chars: int = 1400,
    pause_seconds: float = 3,
    section_boundaries: Iterable[float] = (),
) -> list[dict[str, Any]]:
    """Build exact, non-overlapping source ranges; never invent a boundary label."""
    if max_duration_seconds <= 0 or max_chars <= 0 or pause_seconds < 0:
        raise ValueError("invalid chunking thresholds")
    if not cues:
        return []
    source = {field: cues[0].get(field) for field in PROVENANCE_FIELDS}
    if not source["video_id"] or not source["source_url"] or not source["transcript_type"]:
        raise ValueError("source provenance is incomplete")
    boundaries = sorted(set(section_boundaries))
    output: list[dict[str, Any]] = []
    current: list[tuple[int, dict[str, Any]]] = []

    def flush() -> None:
        if not current:
            return
        first_index, first = current[0]
        last_index, _ = current[-1]
        output.append({
            "chunk_id": f"{source['video_id']}:{first_index}-{last_index}",
            **source,
            "start_seconds": first["start_seconds"],
            "end_seconds": max(item["end_seconds"] for _, item in current),
            "cue_start_index": first_index,
            "cue_end_index": last_index,
            "text": " ".join(item["text"].strip() for _, item in current),
        })
        current.clear()

    previous_end = -1.0
    previous_start = -1.0
    for index, item in enumerate(cues):
        if any(item.get(field) != value for field, value in source.items()):
            raise ValueError("cannot group cues from different sources")
        start, end = item.get("start_seconds"), item.get("end_seconds")
        if not isinstance(start, (float, int)) or not isinstance(end, (float, int)) or end <= start:
            raise ValueError("cue has invalid timestamps")
        if start < previous_start:
            raise ValueError("cues are not ordered")
        if not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("cue has no text")
        if current:
            first = current[0][1]
            last = current[-1][1]
            has_section_boundary = any(last["start_seconds"] < marker <= start for marker in boundaries)
            exceeds_duration = end - first["start_seconds"] > max_duration_seconds
            exceeds_chars = sum(len(cue["text"]) for _, cue in current) + len(item["text"]) > max_chars
            if start - previous_end >= pause_seconds or has_section_boundary or exceeds_duration or exceeds_chars:
                flush()
        current.append((index, item))
        previous_start = start
        previous_end = max(previous_end, end)
    flush()
    return output
