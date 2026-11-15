#!/usr/bin/env python3
"""Run zero-shot AGY recovery jobs and persist raw plus normalized outputs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agy_batch_jobs as agy
from channel_distill.workspace import COLLECTION_ROOT
REQUIRED = {"video_id", "media_access", "coverage", "transcript_segments", "unreadable_ranges", "visual_observations", "limitations"}
def now(): return datetime.now(timezone.utc).isoformat()
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
def usage():
    proc = subprocess.run(["agy", "-p", "/usage"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    out = {"checked_at": now(), "agy_cli_version": agy.get_cli_version(), "raw_output": proc.stdout or "", "availability": "AVAILABLE" if proc.returncode == 0 else "UNAVAILABLE", "five_hour_remaining_percent": None, "weekly_remaining_percent": None}
    for line in (proc.stdout or "").splitlines():
        cols = line.split("\t")
        if len(cols) < 3 or cols[0] != "Gemini Models": continue
        try: value = float(cols[2].rstrip("%"))
        except ValueError: continue
        if cols[1] == "Weekly Limit Remaining": out["weekly_remaining_percent"] = value
        if cols[1] == "Five Hour Limit Remaining": out["five_hour_remaining_percent"] = value
    return out
def parse_output(raw):
    try:
        envelope = json.loads(raw)
        candidate = envelope.get("response") if isinstance(envelope, dict) and "response" in envelope else envelope
        value = json.loads(candidate) if isinstance(candidate, str) else candidate
    except Exception as exc:
        return None, str(exc)
    if not isinstance(value, dict) or not REQUIRED <= set(value): return None, "missing required transcript schema fields"
    return value, None
def classify(value, error, returncode):
    if returncode != 0: return "AGY_EXECUTION_FAILED"
    if error: return "AGY_INVALID_OUTPUT"
    if value.get("media_access") in {"METADATA_ONLY", "INACCESSIBLE"} or value.get("coverage") == "NONE": return "AGY_UNREADABLE"
    if value.get("coverage") == "PARTIAL": return "AGY_PARTIAL"
    if value.get("coverage") == "COMPLETE" and value.get("transcript_segments"): return "OUTPUT_CAPTURED_REVIEW_REQUIRED"
    return "AGY_INVALID_OUTPUT"
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=COLLECTION_ROOT / "schemas" / "agy-zero-shot-schema.json")
    parser.add_argument("--model", required=True)
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--reserve-percent", type=float, default=10.0)
    args = parser.parse_args()
    batch = load(args.batch); manifest = load(args.manifest); records = manifest.get("videos", manifest)
    expected = list(batch.get("expected_video_ids") or [])
    attempted = {x.get("video_id") for x in batch.get("agy_attempt_history", []) if x.get("video_id")}
    global_ids = sorted((video_id for video_id in expected if video_id not in attempted), key=lambda video_id: (float((records.get(video_id) or {}).get("duration") or 10**12), video_id))
    ids = global_ids[:args.limit] if args.limit > 0 else global_ids
    if not ids: raise SystemExit("no unattempted IDs remain in frozen batch")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    before = usage(); save(args.output_dir / "usage-before.json", before)
    if before["five_hour_remaining_percent"] is None and before["weekly_remaining_percent"] is None:
        raise SystemExit("cannot read quota from `agy -p /usage` (expected tab-separated 'Gemini Models' rows; the output format may have changed); refusing to run without a quota guard")
    if args.reserve_percent < 0 or args.reserve_percent >= 100: raise SystemExit("reserve-percent must be between 0 and 100")
    history = batch.setdefault("agy_attempt_history", [])
    results = batch.setdefault("agy_results", {})
    jobs = []
    quota_stop_reason = None
    for video_id in ids:
        current_usage = usage()
        if current_usage.get("five_hour_remaining_percent") is not None and current_usage["five_hour_remaining_percent"] <= args.reserve_percent:
            quota_stop_reason = f"five-hour remaining <= reserve ({args.reserve_percent}%)"
            break
        if current_usage.get("weekly_remaining_percent") is not None and current_usage["weekly_remaining_percent"] <= args.reserve_percent:
            quota_stop_reason = f"weekly remaining <= reserve ({args.reserve_percent}%)"
            break
        record = records.get(video_id) or {}
        source = Path(record.get("canonical_video_path") or "").resolve()
        if record.get("verified") is not True or not source.is_file() or source.stem != video_id:
            entry = {"attempt_id": f"{batch['run_id']}-zero-shot-{video_id}", "video_id": video_id, "status": "AGY_EXECUTION_FAILED", "review_status": "REJECTED", "error": "verified local media missing", "attempted_at": now()}
            history.append(entry); results[video_id] = entry; save(args.batch, batch); jobs.append(entry); continue
        prompt = agy._prompt(video_id, "local_file", str(source)) + "\n\nCritical execution rule: do not launch background tasks, asynchronous jobs, or a command that you leave running. Finish all media inspection in this single print turn and wait for every foreground command to finish before responding. Do not report progress or say you are waiting. Return the final schema object now; if you cannot access the media, return a schema-valid INACCESSIBLE/NONE object instead of progress text."
        prompt_path = args.output_dir / "prompts" / f"{video_id}.txt"; prompt_path.parent.mkdir(parents=True, exist_ok=True); prompt_path.write_text(prompt, encoding="utf-8")
        command = ["agy"]
        if args.yolo: command.append("--dangerously-skip-permissions")
        command.extend(["--model", args.model, "--output-format", "json", "--json-schema", str(args.schema.resolve()), "--print-timeout", "0", "--add-dir", str(source.parent), "--print", prompt])
        proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        raw_path = args.output_dir / "results" / f"{video_id}.stdout.json"; err_path = args.output_dir / "results" / f"{video_id}.stderr.log"; raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_text(proc.stdout or "", encoding="utf-8"); err_path.write_text(proc.stderr or "", encoding="utf-8")
        value, parse_error = parse_output(proc.stdout or ""); status = classify(value, parse_error, proc.returncode); transcript_path = None
        if value is not None:
            transcript_path = args.output_dir / "transcripts" / f"{video_id}.json"; save(transcript_path, value)
        envelope = None
        try: envelope = json.loads(proc.stdout or "")
        except Exception: pass
        entry = {"attempt_id": f"{batch['run_id']}-zero-shot-{video_id}", "video_id": video_id, "status": status, "review_status": "PENDING" if status in {"OUTPUT_CAPTURED_REVIEW_REQUIRED", "AGY_PARTIAL"} else "REJECTED", "source_mode": "local_file", "source_ref": str(source), "model": args.model, "agy_cli_version": agy.get_cli_version(), "permission_mode": "yolo" if args.yolo else "standard", "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "output_path": str(raw_path), "stderr_path": str(err_path), "transcript_path": str(transcript_path) if transcript_path else None, "returncode": proc.returncode, "attempted_at": now(), "parse_error": parse_error, "usage": envelope.get("usage") if isinstance(envelope, dict) else None}
        history.append(entry); results[video_id] = entry; save(args.batch, batch); jobs.append(entry); print(json.dumps({"video_id": video_id, "status": status, "transcript_path": entry["transcript_path"]}, ensure_ascii=True), flush=True)
    after = usage(); save(args.output_dir / "usage-after.json", after); save(args.batch, batch)
    attempted_after = {x.get("video_id") for x in history if x.get("video_id")}
    wave_complete = quota_stop_reason is None and len(jobs) == len(ids)
    summary = {"run_id": batch["run_id"], "attempted_video_ids": [entry.get("video_id") for entry in jobs], "attempted_count": len(jobs), "requested_wave_count": len(ids), "wave_complete": wave_complete, "remaining_unattempted_count": len(ids) - len(jobs), "global_unattempted_before_count": len(global_ids), "global_remaining_unattempted_count": len(set(expected) - attempted_after), "quota_stop_reason": quota_stop_reason, "status_counts": {status: sum(1 for entry in jobs if entry.get("status") == status) for status in sorted({entry.get("status") for entry in jobs})}, "usage_before": before, "usage_after": after}
    save(args.output_dir / "summary.json", summary); print(json.dumps(summary, ensure_ascii=True, indent=2))
    if not wave_complete:
        return 2
    return 0
if __name__ == "__main__": raise SystemExit(main())
