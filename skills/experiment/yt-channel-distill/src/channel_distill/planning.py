"""Conservative, side-effect-free storage estimates for topic downloads."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


GIB = 1024**3
DEFAULT_BYTES_PER_SECOND = 400_000
UNKNOWN_DURATION_BYTES = 2 * GIB
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "unknown": 4}


def estimate_bytes(
    record: dict[str, Any], observed_bytes_per_second: float | None = None
) -> int:
    """Estimate a canonical video's bytes, using observed corpus bitrate when known."""
    for key in ("actual_size", "estimated_size"):
        size = record.get(key)
        if isinstance(size, (int, float)) and size > 0:
            return math.ceil(size)

    duration = record.get("duration")
    if not isinstance(duration, (int, float)) or duration <= 0:
        return UNKNOWN_DURATION_BYTES

    rate = observed_bytes_per_second or DEFAULT_BYTES_PER_SECOND
    if rate <= 0:
        raise ValueError("observed_bytes_per_second must be positive")
    return math.ceil(duration * rate)


def topic_is_safe(
    free_bytes: int, reserve_bytes: int, remaining_estimate: int, margin: float
) -> bool:
    """Require positive space left after reserve and uncertainty-adjusted estimate."""
    if margin < 1:
        raise ValueError("margin must be at least 1")
    if min(free_bytes, reserve_bytes, remaining_estimate) < 0:
        raise ValueError("byte counts must be non-negative")
    return free_bytes - reserve_bytes - math.ceil(remaining_estimate * margin) > 0


def _topic_specs(record: dict[str, Any]) -> list[tuple[str, str]]:
    specs = []
    for item in record.get("topics") or []:
        if isinstance(item, str):
            specs.append((item, record.get("topic_priority") or "unknown"))
        elif isinstance(item, dict):
            topic = item.get("topic")
            if topic:
                specs.append((str(topic), item.get("priority") or "unknown"))
    return specs or [("unclassified", "unknown")]


def build_download_plan(
    records: dict[str, dict[str, Any]],
    *,
    free_bytes: int,
    min_free_bytes: int,
    safety_reserve_percent: float,
    margin: float,
    observed_bytes_per_second: float | None = None,
) -> dict[str, Any]:
    """Summarize unique remaining files and per-topic safe-start decisions."""
    if not 0 <= safety_reserve_percent < 1:
        raise ValueError("safety_reserve_percent must be between 0 and 1")
    if min(free_bytes, min_free_bytes) < 0:
        raise ValueError("byte counts must be non-negative")
    if margin < 1:
        raise ValueError("margin must be at least 1")

    reserve = max(min_free_bytes, math.ceil(free_bytes * safety_reserve_percent))
    topics: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"priority": "unknown", "video_ids": set(), "remaining_ids": set()}
    )
    remaining: dict[str, int] = {}
    unavailable: set[str] = set()

    for video_id, record in records.items():
        if record.get("status") == "UNAVAILABLE":
            unavailable.add(video_id)
        elif not record.get("verified"):
            remaining[video_id] = estimate_bytes(record, observed_bytes_per_second)
        for name, priority in _topic_specs(record):
            entry = topics[name]
            entry["video_ids"].add(video_id)
            if PRIORITY_ORDER.get(priority, 4) < PRIORITY_ORDER.get(entry["priority"], 4):
                entry["priority"] = priority
            if video_id in remaining:
                entry["remaining_ids"].add(video_id)

    sorted_topics = sorted(
        topics.items(), key=lambda pair: (PRIORITY_ORDER.get(pair[1]["priority"], 4), pair[0])
    )
    output_topics: dict[str, dict[str, Any]] = {}
    for name, entry in sorted_topics:
        ids = sorted(entry["remaining_ids"])
        estimate = sum(remaining[video_id] for video_id in ids)
        output_topics[name] = {
            "priority": entry["priority"],
            "video_count": len(entry["video_ids"]),
            "video_ids": sorted(entry["video_ids"]),
            "remaining_ids": ids,
            "remaining_estimate_bytes": estimate,
            "safe_to_start": topic_is_safe(free_bytes, reserve, estimate, margin),
        }

    return {
        "free_bytes": free_bytes,
        "safety_reserve_bytes": reserve,
        "margin": margin,
        "unique_remaining_count": len(remaining),
        "unique_remaining_estimate_bytes": sum(remaining.values()),
        "unavailable_ids": sorted(unavailable),
        "topics": output_topics,
    }
