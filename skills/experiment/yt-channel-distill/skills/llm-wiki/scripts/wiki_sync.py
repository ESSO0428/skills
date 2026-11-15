#!/usr/bin/env python3
"""Sync manifest terminal states to a gate log and compile the derived Wiki once."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from _wiki_core import WikiError, compile_wiki
from wiki_gate import append_gate_event, decide_evidence_gate, decide_gate


def _records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = payload.get("videos", payload)
    if not isinstance(records, dict) or not all(isinstance(value, dict) for value in records.values()):
        raise WikiError("manifest must be an object or contain a videos object")
    return records


def sync_manifest(
    manifest: Path,
    log: Path,
    candidates: Path | None,
    coverage: Path | None,
    wiki_dir: Path | None,
    evidence_dir: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WikiError("manifest JSON must be an object")
    events = [decide_gate(record) for record in _records(payload).values()]
    terminal = [event for event in events if event["terminal_state"] != "WAITING"]
    records = _records(payload)
    evidence_events: list[dict[str, Any]] = []
    if evidence_dir is not None and evidence_dir.is_dir():
        for packet_path in sorted(evidence_dir.rglob("*.packet.json")):
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            if not isinstance(packet, dict):
                raise WikiError(f"evidence packet must be an object: {packet_path}")
            video_id = str(packet.get("video_id") or "")
            if video_id not in records:
                raise WikiError(f"evidence packet video is absent from manifest: {packet_path}")
            event = decide_evidence_gate(packet, records[video_id])
            event["packet_path"] = str(packet_path)
            evidence_events.append(event)
    compile_needed = any(event["action"] in {"COMPILE", "COMPILE_WITH_GAPS"} for event in terminal)
    compiled = False
    if not dry_run:
        for event in [*terminal, *evidence_events]:
            append_gate_event(log, event)
        if compile_needed:
            if not candidates or not coverage or not wiki_dir:
                raise WikiError("compile inputs are required when a record requests Wiki compilation")
            compile_wiki(candidates, coverage, wiki_dir)
            compiled = True
    return {
        "record_count": len(events),
        "terminal_count": len(terminal),
        "evidence_packet_count": len(evidence_events),
        "evidence_blocked_count": sum(event["terminal_state"] == "AGY_BLOCKED" for event in evidence_events),
        "state_counts": {state: sum(event["terminal_state"] == state for event in events) for state in sorted({event["terminal_state"] for event in events})},
        "compile_needed": compile_needed,
        "compiled": compiled,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="manifest JSON; read-only")
    parser.add_argument("--log", type=Path, required=True, help="append-only gate JSONL")
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--coverage", type=Path)
    parser.add_argument("--wiki-dir", type=Path)
    parser.add_argument("--evidence-dir", type=Path, help="directory of immutable *.packet.json evidence packets")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = sync_manifest(
            args.manifest, args.log, args.candidates, args.coverage, args.wiki_dir,
            args.evidence_dir, dry_run=args.dry_run,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, WikiError) as exc:
        print(f"Wiki sync failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
