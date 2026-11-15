"""Deterministic coverage audit for source-backed priority review queues."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Mapping


def build_coverage_report(
    records: Mapping[str, Mapping[str, object]], source_chunks_dir: Path, priority: str = "P0"
) -> dict:
    """Report corpus coverage facts and explicit gaps without semantic guesses."""
    topics: dict[str, list[tuple[str, Mapping[str, object]]]] = {}
    for video_id, record in records.items():
        if record.get("topic_priority") != priority:
            continue
        for label in record.get("topics") or []:
            if not isinstance(label, Mapping) or label.get("priority") != priority:
                continue
            topic = label.get("topic")
            if isinstance(topic, str) and topic:
                topics.setdefault(topic, []).append((video_id, record))

    report_topics: dict[str, dict] = {}
    for topic, members in sorted(topics.items()):
        years: set[int] = set()
        courses: set[str] = set()
        transcript_types: Counter[str] = Counter()
        source_chunk_count = 0
        asr_needed: list[str] = []
        transcript_unavailable: list[str] = []
        ready_ids: list[str] = []
        partial_ids: list[str] = []
        unavailable_segment_count = 0
        verified_ids: list[str] = []
        for video_id, record in members:
            if record.get("verified") is True:
                verified_ids.append(video_id)
            transcript_ready = (
                record.get("transcript_downloaded") is True
                and record.get("transcript_status") in {"READY", "READY_PARTIAL"}
            )
            # A local ASR failure is retryable work, not evidence that the
            # transcript gap vanished.  Keep it in the active queue so a
            # failed attempt cannot make coverage look better than it is.
            if record.get("transcript_status") in {"ASR_NEEDED", "ASR_FAILED"}:
                asr_needed.append(video_id)
            if not transcript_ready:
                transcript_unavailable.append(video_id)
            if transcript_ready:
                ready_ids.append(video_id)
                segment_gaps = record.get("transcript_unavailable_segments")
                if record.get("transcript_status") == "READY_PARTIAL":
                    partial_ids.append(video_id)
                if isinstance(segment_gaps, list):
                    unavailable_segment_count += sum(1 for item in segment_gaps if isinstance(item, Mapping))
                transcript_type = record.get("transcript_type")
                if isinstance(transcript_type, str):
                    transcript_types[transcript_type] += 1
                chunk_path = source_chunks_dir / f"{video_id}.json"
                if chunk_path.is_file():
                    payload = json.loads(chunk_path.read_text(encoding="utf-8"))
                    chunks = payload.get("chunks") if isinstance(payload, dict) else None
                    if isinstance(chunks, list):
                        source_chunk_count += len(chunks)
            for association in record.get("course_associations") or []:
                if not isinstance(association, Mapping):
                    continue
                year = association.get("course_year")
                if isinstance(year, int):
                    years.add(year)
                course = association.get("course")
                if isinstance(course, str) and course:
                    courses.add(course)

        gaps: list[str] = []
        if not ready_ids:
            gaps.append("NO_READY_TRANSCRIPT")
        if asr_needed:
            gaps.append("ASR_NEEDED")
        if transcript_unavailable:
            gaps.append("TRANSCRIPT_UNAVAILABLE")
        if partial_ids:
            gaps.append("PARTIAL_ASR_SEGMENTS")
        if len(years) < 2:
            gaps.append("LIMITED_COURSE_YEAR_COVERAGE")
        if source_chunk_count == 0:
            gaps.append("NO_SOURCE_CHUNKS")
        report_topics[topic] = {
            "p0_video_ids": sorted(video_id for video_id, _ in members),
            "verified_media_ids": sorted(verified_ids),
            "ready_transcript_ids": sorted(ready_ids),
            "asr_needed_ids": sorted(asr_needed),
            "transcript_unavailable_ids": sorted(transcript_unavailable),
            "partial_transcript_ids": sorted(partial_ids),
            "unavailable_segment_count": unavailable_segment_count,
            "course_years": sorted(years),
            "courses": sorted(courses),
            "transcript_types": dict(sorted(transcript_types.items())),
            "source_chunk_count": source_chunk_count,
            "coverage_gaps": gaps,
        }
    return {
        "scope": f"{priority} only; coverage facts, not semantic completeness",
        "topics": report_topics,
    }


build_p0_coverage_report = build_coverage_report
