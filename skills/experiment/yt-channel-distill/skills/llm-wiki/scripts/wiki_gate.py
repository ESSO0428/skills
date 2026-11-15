#!/usr/bin/env python3
"""Classify a completed video record and decide whether the Wiki gate may run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


_FAILURE_STATES = {"DOWNLOAD_FAILED", "ASR_FAILED", "UNAVAILABLE", "FAILED"}
_AGY_BLOCKED_STATES = {"AGY_BLOCKED", "VIDEO_DOWNLOAD_BLOCKED", "REMOTE_GEMINI_BLOCKED"}


def _fingerprint(record: dict[str, Any]) -> str:
    # ``wiki_gate`` is derived bookkeeping written after the decision.  Exclude it
    # from the fingerprint so a repeated handoff is idempotent and does not create
    # a new event merely because the previous event was persisted in the manifest.
    fingerprint_record = {key: value for key, value in record.items() if key != "wiki_gate"}
    canonical = json.dumps(fingerprint_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decide_gate(record: dict[str, Any]) -> dict[str, Any]:
    """Return a terminal state and action without changing the record."""
    video_id = str(record.get("video_id") or "")
    if not video_id:
        raise ValueError("record.video_id is required")
    agy_status = str(record.get("agy_status") or record.get("supplement_status") or "")
    if agy_status in _AGY_BLOCKED_STATES:
        terminal_state, action = "AGY_BLOCKED", "RECORD_BLOCKED"
        reason = "AGY could not provide supplemental evidence; preserve the blocked gap."
    elif str(record.get("status") or "") in _FAILURE_STATES or str(record.get("transcript_status") or "") in _FAILURE_STATES:
        terminal_state, action = "FAILED", "RECORD_BLOCKED"
        reason = "The media or transcript pipeline ended in an explicit failure state."
    elif record.get("transcript_unavailable_segments") or record.get("transcript_status") == "READY_PARTIAL":
        terminal_state, action = "READY_PARTIAL", "COMPILE_WITH_GAPS"
        reason = "Some transcript segments are unavailable; compile the coverage gap explicitly."
    elif (record.get("status") == "VERIFIED" or record.get("verified") is True) and record.get("transcript_status") == "READY":
        terminal_state, action = "READY", "COMPILE"
        reason = "Verified media and transcript are ready for one Wiki compilation."
    else:
        terminal_state, action = "WAITING", "NO_ACTION"
        reason = "The record has not reached a terminal extraction state."
    return {
        "video_id": video_id,
        "terminal_state": terminal_state,
        "action": action,
        "reason": reason,
        "record_sha256": _fingerprint(record),
    }


def decide_evidence_gate(packet: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Classify a supplemental packet without promoting it to canonical text."""
    video_id = str(packet.get("video_id") or record.get("video_id") or "")
    if not video_id:
        raise ValueError("evidence packet video_id is required")
    if str(record.get("video_id") or video_id) != video_id:
        raise ValueError("evidence packet and manifest video IDs differ")
    agy = packet.get("agy") if isinstance(packet.get("agy"), dict) else {}
    packet_status = str(
        agy.get("status")
        or packet.get("agy_status")
        or packet.get("supplement_status")
        or ""
    )
    if packet_status in _AGY_BLOCKED_STATES or (
        str(packet.get("packet_type") or "").startswith("AGY_")
        and packet_status not in {"SUCCESS", "READY", "COMPLETED"}
    ):
        event = decide_gate({**record, "video_id": video_id, "agy_status": packet_status or "AGY_BLOCKED"})
        event["action"] = "RECORD_BLOCKED"
    else:
        event = decide_gate({**record, "video_id": video_id})
        event["action"] = "RECORD_SUPPLEMENT"
    event["event_type"] = "evidence_packet"
    event["packet_type"] = str(packet.get("packet_type") or "UNKNOWN")
    event["packet_status"] = packet_status or "UNKNOWN"
    event["merge_decision"] = str(packet.get("merge_decision") or "UNSPECIFIED")
    coverage_status = str(agy.get("coverage_status") or "")
    reported_duration = agy.get("reported_duration_seconds")
    canonical_duration = agy.get("canonical_duration_seconds")
    duration_mismatch = coverage_status == "PARTIAL_DURATION_MISMATCH"
    if not duration_mismatch and isinstance(reported_duration, (int, float)) and isinstance(canonical_duration, (int, float)):
        tolerance = max(30.0, abs(float(canonical_duration)) * 0.05)
        duration_mismatch = abs(float(reported_duration) - float(canonical_duration)) > tolerance
    event["supplement_review_required"] = duration_mismatch
    if duration_mismatch:
        event["supplement_review_reason"] = "AGY-reported duration differs from canonical duration; supplemental coverage is partial and cannot establish full-track integrity."
    event["packet_sha256"] = _fingerprint(packet)
    return event


def append_gate_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    marker = json.dumps(event, ensure_ascii=False, sort_keys=True)
    if any(line == marker for line in existing):
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(marker + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True, help="one manifest/evidence record JSON; read-only")
    parser.add_argument("--log", type=Path, help="optional append-only JSONL gate log")
    args = parser.parse_args()
    try:
        record = json.loads(args.record.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("record JSON must be an object")
        event = decide_gate(record)
        if args.log:
            append_gate_event(args.log, event)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Wiki gate failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(event, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
