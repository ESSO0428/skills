#!/usr/bin/env python3
"""Acquire one frozen video batch, keeping resumable manifest/report checkpoints."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import sys
from typing import Any


from channel_distill.asr import transcribe_local_asr
from channel_distill.download import download_one
from channel_distill.manifest import export_csv, load_manifest, save_manifest
from channel_distill.planning import GIB, estimate_bytes
from channel_distill.subtitle_download import collect_subtitles
from channel_distill.workspace import find_binary, resolve_workspace


TERMINAL_MEDIA_FAILURES = {"DOWNLOAD_FAILED", "VERIFY_FAILED", "UNAVAILABLE"}
ASR_ELIGIBLE_TRANSCRIPT_STATES = {"ASR_NEEDED", "FETCH_FAILED", "PARSE_FAILED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_batch(batch_path: Path) -> dict[str, Any]:
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    ids = batch.get("expected_video_ids") if isinstance(batch, dict) else None
    if not isinstance(ids, list) or not ids:
        raise ValueError("batch expected_video_ids must be a non-empty list")
    if any(not isinstance(video_id, str) or not video_id for video_id in ids):
        raise ValueError("batch expected_video_ids must contain non-empty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("batch expected_video_ids contains duplicate IDs")
    if not isinstance(batch.get("run_id"), str) or not batch["run_id"].strip():
        raise ValueError("batch run_id must be a non-empty string")
    return batch


def _load_scope(manifest_path: Path, batch_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[str]]:
    records = load_manifest(manifest_path)
    batch = _load_batch(batch_path)
    ids = batch["expected_video_ids"]
    missing = sorted(set(ids) - set(records))
    if missing:
        raise ValueError(f"batch IDs missing from manifest: {', '.join(missing)}")
    mismatched = [video_id for video_id in ids if records[video_id].get("video_id", video_id) != video_id]
    if mismatched:
        raise ValueError(f"manifest key/video_id mismatch: {', '.join(mismatched)}")
    return records, batch, ids


def freeze_batch(manifest_path: Path, ids_file: Path, output_path: Path, *, run_id: str | None = None) -> dict[str, Any]:
    """Freeze a user-selected JSON ID list without replacing an existing batch ledger."""
    records = load_manifest(manifest_path)
    selected = json.loads(ids_file.read_text(encoding="utf-8"))
    ids = selected.get("video_ids") if isinstance(selected, dict) else selected
    if not isinstance(ids, list) or not ids:
        raise ValueError("selected IDs must be a non-empty JSON list or an object with video_ids")
    if any(not isinstance(video_id, str) or not video_id for video_id in ids):
        raise ValueError("selected IDs must contain non-empty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("selected IDs contain duplicates")
    missing = sorted(set(ids) - set(records))
    if missing:
        raise ValueError(f"selected IDs missing from manifest: {', '.join(missing)}")
    resolved_run_id = run_id or f"batch-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    if not resolved_run_id.strip():
        raise ValueError("run_id must not be empty")
    payload = {
        "run_id": resolved_run_id,
        "created_at": _now(),
        "expected_video_ids": ids,
        "agy_remote_capability": "UNVERIFIED",
        "agy_results": {},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return payload


def _batch_estimate(
    records: dict[str, dict[str, Any]], ids: list[str], *, retry_download_failures: bool = False
) -> tuple[int, list[str]]:
    needs_video = [
        video_id
        for video_id in ids
        if not records[video_id].get("verified")
        and (
            records[video_id].get("status") not in TERMINAL_MEDIA_FAILURES
            or (retry_download_failures and records[video_id].get("status") == "DOWNLOAD_FAILED")
        )
    ]
    return sum(estimate_bytes(records[video_id]) for video_id in needs_video), needs_video


def build_plan(
    manifest_path: Path,
    batch_path: Path,
    data_dir: Path,
    *,
    min_free_bytes: int,
    safety_reserve_percent: float,
    margin: float,
    retry_download_failures: bool = False,
) -> dict[str, Any]:
    """Read-only batch preflight; it never creates directories or contacts a source."""
    if min_free_bytes < 0:
        raise ValueError("min_free_bytes must not be negative")
    if not 0 <= safety_reserve_percent < 1:
        raise ValueError("safety_reserve_percent must be between 0 and 1")
    if margin < 1:
        raise ValueError("margin must be at least 1")
    records, batch, ids = _load_scope(manifest_path, batch_path)
    free_bytes = shutil.disk_usage(data_dir).free
    reserve = max(min_free_bytes, math.ceil(free_bytes * safety_reserve_percent))
    estimate, needs_video = _batch_estimate(
        records, ids, retry_download_failures=retry_download_failures
    )
    required = math.ceil(estimate * margin)
    return {
        "run_id": batch["run_id"],
        "expected_video_ids": ids,
        "target_count": len(ids),
        "already_verified_ids": [video_id for video_id in ids if records[video_id].get("verified")],
        "retry_download_failures": retry_download_failures,
        "terminal_media_failure_ids": [
            video_id
            for video_id in ids
            if records[video_id].get("status") in TERMINAL_MEDIA_FAILURES
            and not (retry_download_failures and records[video_id].get("status") == "DOWNLOAD_FAILED")
        ],
        "video_download_pending_ids": needs_video,
        "storage": {
            "free_bytes": free_bytes,
            "reserve_bytes": reserve,
            "estimated_download_bytes": estimate,
            "margin": margin,
            "required_bytes_with_margin": required,
            "safe_to_start": free_bytes - reserve - required > 0,
        },
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _persist(manifest_path: Path, csv_path: Path, records: dict[str, dict[str, Any]]) -> None:
    save_manifest(manifest_path, records)
    export_csv(csv_path, records)


def run_batch(
    manifest_path: Path,
    batch_path: Path,
    data_dir: Path,
    report_path: Path,
    *,
    ffprobe: Path,
    ffmpeg: str,
    model_path: Path,
    min_free_bytes: int,
    safety_reserve_percent: float,
    margin: float,
    retry_download_failures: bool = False,
) -> dict[str, Any]:
    """Run one authorized batch once; failures are recorded, never auto-retried."""
    plan = build_plan(
        manifest_path,
        batch_path,
        data_dir,
        min_free_bytes=min_free_bytes,
        safety_reserve_percent=safety_reserve_percent,
        margin=margin,
        retry_download_failures=retry_download_failures,
    )
    if not plan["storage"]["safe_to_start"]:
        raise RuntimeError(
            "Insufficient storage for the frozen batch after reserve and safety margin; no acquisition started"
        )
    records, batch, ids = _load_scope(manifest_path, batch_path)
    csv_path = manifest_path.with_name("videos.csv")
    report: dict[str, Any] = {
        "run_id": batch["run_id"],
        "started_at": _now(),
        "manifest": str(manifest_path),
        "batch": str(batch_path),
        "plan": plan,
        "expected_video_ids": ids,
        "results": [],
        "processed_ids": [],
        "skipped_terminal_ids": [],
    }
    _atomic_write_json(report_path, report)

    for index, video_id in enumerate(ids, start=1):
        before = records[video_id]
        updated = dict(before)
        action = "PENDING"
        asr_attempted = False
        if before.get("status") in TERMINAL_MEDIA_FAILURES and not (
            retry_download_failures and before.get("status") == "DOWNLOAD_FAILED"
        ):
            action = "SKIPPED_FOR_AGY"
            report["skipped_terminal_ids"].append(video_id)
        elif before.get("verified") and before.get("transcript_status") == "ASR_FAILED":
            action = "SKIPPED_ASR_TERMINAL"
            report["skipped_terminal_ids"].append(video_id)
        else:
            try:
                if not (updated.get("verified") and updated.get("transcript_downloaded")):
                    updated = download_one(
                        updated,
                        video_dir=data_dir / "videos",
                        ffprobe=ffprobe,
                        min_free_bytes=min_free_bytes,
                        safety_reserve_percent=safety_reserve_percent,
                        margin=margin,
                    )
                if updated.get("verified") and updated.get("canonical_video_path"):
                    updated["media_archival_status"] = "VIDEO_ARCHIVED_VERIFIED"
                    if not updated.get("transcript_downloaded"):
                        try:
                            updated = collect_subtitles(updated, transcript_dir=data_dir / "transcripts")
                        except Exception as exc:
                            updated["transcript_status"] = "FETCH_FAILED"
                            updated["transcript_error"] = f"subtitle collection exception: {exc}"[-2000:]
                            updated["transcript_retryable"] = True
                        _persist(manifest_path, csv_path, {**records, video_id: updated})
                        records[video_id] = updated

                    if (
                        not updated.get("transcript_downloaded")
                        and updated.get("transcript_status") in ASR_ELIGIBLE_TRANSCRIPT_STATES
                    ):
                        asr_attempted = True
                        try:
                            updated = transcribe_local_asr(
                                updated,
                                video_path=Path(updated["canonical_video_path"]),
                                transcript_dir=data_dir / "transcripts",
                                ffmpeg=ffmpeg,
                                model_path=model_path,
                                min_free_bytes=min_free_bytes,
                            )
                            if updated.get("transcript_downloaded") and updated.get("transcript_type") == "ASR":
                                updated["transcript_source"] = "verified_local_video"
                                updated["transcript_provenance_note"] = (
                                    "ASR derived from the canonical local video after successful ffprobe verification."
                                )
                        except Exception as exc:
                            updated = dict(updated)
                            updated.update(
                                transcript_downloaded=False,
                                transcript_type="missing",
                                transcript_status="ASR_FAILED",
                                transcript_error=str(exc)[-2000:],
                                transcript_retryable=True,
                            )
                    action = "READY" if updated.get("transcript_downloaded") else str(
                        updated.get("transcript_status") or updated.get("status") or "INCOMPLETE"
                    )
                else:
                    action = str(updated.get("status") or "DOWNLOAD_FAILED")
            except Exception as exc:
                updated = dict(updated)
                updated.update(status="DOWNLOAD_FAILED", error=str(exc)[-2000:], retryable=True, verified=False)
                action = "DOWNLOAD_FAILED"

            records[video_id] = updated
            _persist(manifest_path, csv_path, records)
            report["processed_ids"].append(video_id)

        result = {
            "video_id": video_id,
            "action": action,
            "verified": bool(updated.get("verified")),
            "video_path": updated.get("canonical_video_path"),
            "transcript_status": updated.get("transcript_status"),
            "transcript_type": updated.get("transcript_type"),
            "transcript_path": updated.get("transcript_path"),
            "asr_attempted": asr_attempted,
        }
        report["results"].append(result)
        report["updated_at"] = _now()
        _atomic_write_json(report_path, report)
        print(f"[{index}/{len(ids)}] {video_id}: {action}", flush=True)

    report["finished_at"] = _now()
    _atomic_write_json(report_path, report)
    return report


def _workspace_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace", type=Path,
        help="workspace root (default: $YTD_WORKSPACE, else the current directory); other paths default under it",
    )


def _apply_workspace(args: argparse.Namespace) -> None:
    """Fill every unset path from the workspace layout (<ws>/data/...)."""
    ws = resolve_workspace(args.workspace)
    args.workspace = ws.root
    args.manifest = args.manifest or ws.manifest / "videos.json"
    if hasattr(args, "batch"):
        args.batch = args.batch or ws.processing / "current-batch.json"
    if hasattr(args, "output"):
        args.output = args.output or ws.processing / "current-batch.json"
    if hasattr(args, "data_dir"):
        args.data_dir = args.data_dir or ws.data
        args.report = args.report or ws.processing / "acquisition-report.json"
    if hasattr(args, "model_path") and not args.model_path:
        found = sorted(ws.models.glob("faster-whisper-tiny-*")) if ws.models.is_dir() else []
        args.model_path = found[0] if found else ws.models / "faster-whisper-tiny"


def _common_args(parser: argparse.ArgumentParser) -> None:
    _workspace_arg(parser)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--min-free-space-gb", type=float, default=30.0)
    parser.add_argument("--safety-reserve-percent", type=float, default=0.25)
    parser.add_argument("--margin", type=float, default=1.5)
    parser.add_argument(
        "--retry-download-failures",
        action="store_true",
        help="retry only DOWNLOAD_FAILED records in this explicitly frozen batch once",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze_parser = commands.add_parser("freeze", help="create an immutable ledger from an explicit selected-ID JSON file")
    _workspace_arg(freeze_parser)
    freeze_parser.add_argument("--manifest", type=Path)
    freeze_parser.add_argument("--ids-file", type=Path, required=True)
    freeze_parser.add_argument("--output", type=Path)
    freeze_parser.add_argument("--run-id")
    plan_parser = commands.add_parser("plan", help="read-only storage and frozen-scope preflight")
    _common_args(plan_parser)
    run_parser = commands.add_parser("run", help="download media, collect captions, and run local ASR if needed")
    _common_args(run_parser)
    run_parser.add_argument("--execute", action="store_true", help="required explicit opt-in for network/local processing")
    run_parser.add_argument("--ffprobe", type=Path, help="ffprobe binary (default: $YTD_FFMPEG_DIR, then PATH)")
    run_parser.add_argument("--ffmpeg", help="ffmpeg binary (default: $YTD_FFMPEG_DIR, then PATH)")
    run_parser.add_argument("--model-path", type=Path, help="local faster-whisper model dir (default: <ws>/data/models/faster-whisper-tiny-*)")
    args = parser.parse_args(argv)
    _apply_workspace(args)
    try:
        if args.command == "freeze":
            payload = freeze_batch(args.manifest, args.ids_file, args.output, run_id=args.run_id)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        min_free_bytes = int(args.min_free_space_gb * GIB)
        if args.command == "plan":
            plan = build_plan(
                args.manifest,
                args.batch,
                args.data_dir,
                min_free_bytes=min_free_bytes,
                safety_reserve_percent=args.safety_reserve_percent,
                margin=args.margin,
                retry_download_failures=args.retry_download_failures,
            )
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0 if plan["storage"]["safe_to_start"] else 2
        if not args.execute:
            parser.error("run requires --execute after reviewing the plan and obtaining authorization")
        args.ffprobe = find_binary("ffprobe", args.ffprobe)
        try:
            args.ffmpeg = str(find_binary("ffmpeg", args.ffmpeg))
        except FileNotFoundError as exc:
            print(f"warning: {exc}; local ASR will fail if it is needed", file=sys.stderr)
            args.ffmpeg = args.ffmpeg or "ffmpeg"
        if not args.model_path.is_dir():
            print(
                f"warning: local ASR model not found at {args.model_path}; ASR fallback will report "
                "ASR_MODEL_MISSING (place weights there or pass --model-path)",
                file=sys.stderr,
            )
        run_batch(
            args.manifest,
            args.batch,
            args.data_dir,
            args.report,
            ffprobe=args.ffprobe,
            ffmpeg=args.ffmpeg,
            model_path=args.model_path,
            min_free_bytes=min_free_bytes,
            safety_reserve_percent=args.safety_reserve_percent,
            margin=args.margin,
            retry_download_failures=args.retry_download_failures,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:  # includes FileNotFoundError
        print(f"acquisition batch failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
