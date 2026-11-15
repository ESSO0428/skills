"""Conservative multi-label topic suggestions from YouTube video titles.

Rules are workspace data (``<workspace>/config/topic-rules.json``); without a
rules file every title stays ``unknown``.  See ``examples/topic-rules.ml-course.json``.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re


PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "unknown": 4}


def load_topic_rules(path: Path | None) -> dict | None:
    """Load a rules file; ``None`` or a missing file means no rules (all unknown)."""
    if path is None or not Path(path).is_file():
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"topic rules must be a JSON object: {path}")
    return {
        "topic_rules": [tuple(rule) for rule in payload.get("topic_rules") or []],
        "core_explicit_rules": [tuple(rule) for rule in payload.get("core_explicit_rules") or []],
        "specialized_context": payload.get("specialized_context"),
    }


def best_topic_priority(labels: list[dict]) -> str:
    """Return the highest priority supported by actual labels."""
    return min(
        (label.get("priority", "unknown") for label in labels),
        key=lambda priority: PRIORITY_RANK.get(priority, PRIORITY_RANK["unknown"]),
        default="unknown",
    )


def classify_video(record: dict, rules: dict | None = None) -> list[dict]:
    """Return evidence-labeled topic suggestions; unmatched titles stay unknown."""
    title = record.get("title") or ""
    matches = []
    if rules:
        context = rules.get("specialized_context")
        specialized = bool(context and re.search(context, title, re.IGNORECASE))
        for topic, pattern in rules.get("core_explicit_rules") or []:
            hit = re.search(pattern, title, re.IGNORECASE)
            if hit:
                matches.append({
                    "topic": topic,
                    "priority": "P0",
                    "confidence": 0.9,
                    "reason": f"explicit core title matched {hit.group(0)!r}",
                })
        explicit_topics = {label["topic"] for label in matches}
        for topic, priority, pattern in rules.get("topic_rules") or []:
            if topic in explicit_topics:
                continue
            if specialized and priority == "P0":
                continue
            hit = re.search(pattern, title, re.IGNORECASE)
            if hit:
                matches.append({
                    "topic": topic,
                    "priority": priority,
                    "confidence": 0.8,
                    "reason": f"title matched {hit.group(0)!r}",
                })
    return matches or [{
        "topic": "unknown",
        "priority": "unknown",
        "confidence": 0.0,
        "reason": "No matching title rule; manual review needed",
    }]


def classify_inventory(videos: dict[str, dict], rules: dict | None = None) -> dict[str, dict]:
    """Attach suggestions to copied records, with their highest matched priority."""
    classified = deepcopy(videos)
    for record in classified.values():
        official_labels = [
            label for label in (record.get("topics") or [])
            if isinstance(label, dict) and label.get("source_url")
        ]
        official_topics = {label.get("topic") for label in official_labels}
        title_labels = [
            label for label in classify_video(record, rules)
            if label["topic"] not in official_topics and (label["topic"] != "unknown" or not official_labels)
        ]
        labels = official_labels + title_labels
        record["topics"] = labels
        record["topic_priority"] = best_topic_priority(labels)
    return classified
