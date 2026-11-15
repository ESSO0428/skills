"""Command-line entry points for the provenance-preserving channel pipeline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .asr import transcribe_local_asr
from .classify import classify_inventory, load_topic_rules
from .coverage import build_coverage_report
from .download import download_one
from .inventory import fetch_channel_inventory, merge_inventory
from .manifest import export_csv, load_manifest, save_manifest
from .planning import GIB, build_download_plan
from .reading_view import build_reading_view
from .source_chunks import group_cues, order_cues
from .subtitle_download import collect_subtitles
from .workspace import find_binary, load_llm_wiki_module, resolve_workspace


def _wiki_gate_module():
    """The llm-wiki skill owns gate classification; load it from the collection."""
    return load_llm_wiki_module("wiki_gate")


def _save_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _save_download_status(path: Path, plan: dict, records: dict[str, dict]) -> None:
    """Derive topic completion from persisted facts, never from attempted calls."""
    topics = {}
    for name, topic in plan["topics"].items():
        ids = topic["video_ids"]
        unavailable = [video_id for video_id in ids if records[video_id].get("status") == "UNAVAILABLE"]
        available = [video_id for video_id in ids if video_id not in unavailable]
        verified = [video_id for video_id in available if records[video_id].get("verified")]
        transcripts = [video_id for video_id in ids if records[video_id].get("transcript_downloaded")]
        complete_available = len(verified) == len(available)
        topics[name] = {
            "video_count": len(ids),
            "available_count": len(available),
            "verified_count": len(verified),
            "transcript_count": len(transcripts),
            "unavailable_ids": unavailable,
            "all_discovered_items_available": not unavailable,
            "status": (
                "AVAILABLE_ITEMS_COMPLETE" if unavailable else "VERIFIED"
            ) if complete_available else "PARTIAL",
        }
    _save_json_atomic(path, {"topics": topics})


def _prepare_sources(args: argparse.Namespace) -> int:
    try:
        records = load_manifest(args.data_dir / "manifest" / "videos.json")
        if not records:
            raise ValueError("inventory is empty; run inventory first")
        total_chunks = 0
        processed = 0
        for video_id, record in records.items():
            if not record.get("transcript_downloaded"):
                continue
            transcript_path = Path(record.get("transcript_chunks_path") or "")
            if not transcript_path.is_file():
                raise ValueError(f"claimed transcript is missing for {video_id}: {transcript_path}")
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            if transcript.get("video_id") not in (None, video_id):
                raise ValueError(f"transcript video ID mismatch for {video_id}")
            source_chunks = group_cues(order_cues(transcript.get("chunks") or []))
            if not source_chunks:
                raise ValueError(f"no source chunks for {video_id}")
            output_path = args.data_dir / "processing" / "source_chunks" / f"{video_id}.json"
            _save_json_atomic(output_path, {"video_id": video_id, "chunks": source_chunks})
            processed += 1
            total_chunks += len(source_chunks)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Source preparation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Prepared {total_chunks} source chunks from {processed} transcripts")
    return 0


def _audit_coverage(args: argparse.Namespace) -> int:
    try:
        records = load_manifest(args.data_dir / "manifest" / "videos.json")
        if not records:
            raise ValueError("inventory is empty; run inventory first")
        report = build_coverage_report(
            records, args.data_dir / "processing" / "source_chunks",
            priority=getattr(args, "priority", "P0"),
        )
        _save_json_atomic(args.output, report)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Coverage audit failed: {exc}", file=sys.stderr)
        return 1
    print(f"Audited {len(report['topics'])} {getattr(args, 'priority', 'P0')} topics in {args.output}")
    return 0

def _compile_wiki(args: argparse.Namespace) -> int:
    try:
        # Use the llm-wiki skill's compiler so state/hash validation stays
        # identical for CLI and skill-script invocations.
        result = load_llm_wiki_module("_wiki_core").compile_wiki(
            args.candidates, args.coverage, args.wiki_dir
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, ImportError) as exc:
        print(f"Wiki compilation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Compiled {result['principle_count']} principles across {result['topic_count']} wiki topics")
    return 0


def _wiki_gate(args: argparse.Namespace) -> int:
    try:
        record = json.loads(args.record.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("record JSON must be an object")
        gate = _wiki_gate_module()
        event = gate.decide_gate(record)
        if args.log is not None:
            gate.append_gate_event(args.log, event)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Wiki gate failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(event, ensure_ascii=False, sort_keys=True))
    return 0


def _record_wiki_gate(data_dir: Path, record: dict) -> dict:
    """Persist one deterministic terminal decision and its derived manifest state."""
    gate = _wiki_gate_module()
    event = gate.decide_gate(record)
    gate.append_gate_event(data_dir / "processing" / "wiki-gate.jsonl", event)
    manifest_path = data_dir / "manifest" / "videos.json"
    if manifest_path.is_file():
        records = load_manifest(manifest_path)
        current = records.get(event["video_id"])
        if current is not None:
            updated = dict(current)
            updated["wiki_gate"] = {
                "terminal_state": event["terminal_state"],
                "action": event["action"],
                "reason": event["reason"],
                "record_sha256": event["record_sha256"],
            }
            records[event["video_id"]] = updated
            save_manifest(manifest_path, records)
            export_csv(data_dir / "manifest" / "videos.csv", records)
    return event


def _build_reading_views(args: argparse.Namespace) -> int:
    """Render timestamp-free text and an exact anchor map for every prepared source."""
    try:
        count = 0
        for source_path in sorted(args.source_dir.glob("*.json")):
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            video_id = payload.get("video_id")
            chunks = payload.get("chunks")
            if not isinstance(video_id, str) or not isinstance(chunks, list):
                raise ValueError(f"invalid source chunk payload: {source_path}")
            document, anchors = build_reading_view(video_id, chunks)
            output_path = args.output_dir / f"{video_id}.md"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(document, encoding="utf-8")
            _save_json_atomic(args.output_dir / f"{video_id}.anchors.json", anchors)
            count += 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Reading-view build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Built {count} timestamp-free reading views in {args.output_dir}")
    return 0


def _sync_wiki_after_text(args: argparse.Namespace) -> bool:
    """Run one Wiki gate pass after a text pipeline; only when ``--sync-wiki`` is given."""
    if not getattr(args, "sync_wiki", False):
        return True
    data_dir = args.data_dir
    workspace = data_dir.parent
    candidates = (
        Path(args.candidates) if getattr(args, "candidates", None)
        else workspace / "knowledge" / "p0_candidates.json"
    )
    coverage = data_dir / "manifest" / "coverage-report.json"
    wiki_dir = workspace / "knowledge" / "wiki"
    if not candidates.is_file():
        print(f"Wiki sync skipped: candidates file not found: {candidates}", file=sys.stderr)
        return True
    if _audit_coverage(argparse.Namespace(data_dir=data_dir, output=coverage, priority="P0")) != 0:
        return False
    try:
        result = load_llm_wiki_module("wiki_sync").sync_manifest(
            data_dir / "manifest" / "videos.json",
            data_dir / "processing" / "wiki-gate.jsonl",
            candidates,
            coverage,
            wiki_dir,
            data_dir / "processing" / "evidence_packets",
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, ImportError) as exc:
        print(f"Wiki sync failed: {exc}", file=sys.stderr)
        return False
    print(
        f"Wiki sync: {result['terminal_count']} terminal records, "
        f"evidence_packets={result.get('evidence_packet_count', 0)}, "
        f"compiled={result['compiled']}"
    )
    return True


def _run_text_pipeline(args: argparse.Namespace) -> bool:
    """Run deterministic source preparation, reading views and coverage once."""
    data_dir = args.data_dir
    source_dir = data_dir / "processing" / "source_chunks"
    reading_dir = data_dir / "processing" / "reading_views"
    if _prepare_sources(argparse.Namespace(data_dir=data_dir)) != 0:
        return False
    if _build_reading_views(
        argparse.Namespace(source_dir=source_dir, output_dir=reading_dir)
    ) != 0:
        return False
    coverage = data_dir / "manifest" / "coverage-report.json"
    if _audit_coverage(argparse.Namespace(data_dir=data_dir, output=coverage, priority="P0")) != 0:
        return False
    return _sync_wiki_after_text(args)


def _model_path(args: argparse.Namespace) -> Path:
    """``--model-path`` > ``<ws>/data/models/<--model-name>`` > first ``faster-whisper-tiny-*`` dir."""
    if args.model_path:
        return args.model_path
    models = args.data_dir / "models"
    if args.model_name:
        return models / args.model_name
    found = sorted(models.glob("faster-whisper-tiny-*")) if models.is_dir() else []
    return found[0] if found else models / "faster-whisper-tiny"


def _transcribe_one(args: argparse.Namespace) -> int:
    videos_path = args.data_dir / "manifest" / "videos.json"
    try:
        records = load_manifest(videos_path)
        if args.video_id not in records:
            raise ValueError(f"unknown video ID: {args.video_id}")
        record = records[args.video_id]
        existing_public_transcript = (
            record.get("transcript_downloaded")
            and record.get("transcript_type") in {"official", "auto"}
        )
        if existing_public_transcript:
            print(f"{args.video_id}: existing {record['transcript_type']} subtitles preserved")
            updated = record
            if not args.postprocess:
                return 0
        else:
            updated = transcribe_local_asr(
                record,
                video_path=Path(record.get("canonical_video_path") or ""),
                transcript_dir=args.data_dir / "transcripts",
                ffmpeg=find_binary("ffmpeg", args.ffmpeg),
                model_path=_model_path(args),
                min_free_bytes=int(args.min_free_space_gb * GIB),
            )
            records[args.video_id] = updated
            save_manifest(videos_path, records)
            export_csv(args.data_dir / "manifest" / "videos.csv", records)
    except (OSError, RuntimeError, ValueError) as exc:  # FileNotFoundError is an OSError
        print(f"ASR failed: {exc}", file=sys.stderr)
        return 1
    print(f"{args.video_id}: {updated.get('transcript_status')}")
    ready = existing_public_transcript or (
        updated.get("transcript_downloaded")
        and updated.get("transcript_status") in {"READY", "READY_PARTIAL"}
    )
    _record_wiki_gate(args.data_dir, updated)
    if not ready:
        return 1
    if args.postprocess and not _run_text_pipeline(args):
        return 1
    return 0


def _download_topic(args: argparse.Namespace) -> int:
    videos_path = args.data_dir / "manifest" / "videos.json"
    csv_path = args.data_dir / "manifest" / "videos.csv"
    status_path = args.data_dir / "manifest" / "download-status.json"
    try:
        records = load_manifest(videos_path)
        if not records:
            raise ValueError("inventory is empty; run inventory first")
        free_bytes = shutil.disk_usage(args.data_dir).free
        plan = build_download_plan(
            records,
            free_bytes=free_bytes,
            min_free_bytes=int(args.min_free_space_gb * GIB),
            safety_reserve_percent=args.safety_reserve_percent,
            margin=args.margin,
        )
        topic = plan["topics"].get(args.topic)
        if topic is None:
            raise ValueError(f"unknown topic: {args.topic}")
        if args.video_id is not None:
            if args.video_id not in records:
                raise ValueError(f"unknown video ID: {args.video_id}")
            if args.video_id not in topic["video_ids"]:
                raise ValueError(f"video {args.video_id!r} is not in topic {args.topic!r}")
            video_ids = [args.video_id]
        else:
            if not topic["safe_to_start"]:
                raise ValueError(
                    f"topic {args.topic!r} is unsafe with current free space; run plan-download"
                )
            video_ids = topic["video_ids"]
        if args.max_videos is not None:
            if args.max_videos < 1:
                raise ValueError("--max-videos must be positive")
            video_ids = video_ids[: args.max_videos]
        failures = []
        for video_id in video_ids:
            current = records[video_id]
            if current.get("status") == "UNAVAILABLE":
                continue
            if current.get("verified") and current.get("transcript_downloaded"):
                continue
            updated = download_one(
                current,
                video_dir=args.data_dir / "videos",
                ffprobe=find_binary("ffprobe", args.ffprobe),
                min_free_bytes=int(args.min_free_space_gb * GIB),
                safety_reserve_percent=args.safety_reserve_percent,
                margin=args.margin,
            )
            records[video_id] = updated
            save_manifest(videos_path, records)
            export_csv(csv_path, records)
            _save_download_status(status_path, plan, records)
            if updated.get("verified"):
                if not updated.get("transcript_downloaded"):
                    updated = collect_subtitles(updated, transcript_dir=args.data_dir / "transcripts")
                    records[video_id] = updated
                    save_manifest(videos_path, records)
                    export_csv(csv_path, records)
                    _save_download_status(status_path, plan, records)
            else:
                failures.append(video_id)
            _record_wiki_gate(args.data_dir, updated)
            print(f"{video_id}: {updated.get('status')}; subtitle {updated.get('transcript_status') or 'pending'}")
        _save_download_status(status_path, plan, records)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1
    if not _sync_wiki_after_text(args):
        return 1
    return 1 if failures else 0

def _render_download_plan(plan: dict, records: dict[str, dict]) -> str:
    lines = [
        "# Download Plan",
        "",
        f"Free space: {plan['free_bytes'] / GIB:.2f} GiB",
        f"Safety reserve: {plan['safety_reserve_bytes'] / GIB:.2f} GiB",
        f"Usable space: {max(0, plan['free_bytes'] - plan['safety_reserve_bytes']) / GIB:.2f} GiB",
        f"Unique remaining videos: {plan['unique_remaining_count']}",
        f"Estimated unique remaining size (before {plan['margin']:.2f}x margin): "
        f"{plan['unique_remaining_estimate_bytes'] / GIB:.2f} GiB",
        "",
        "Topic estimates overlap when one canonical video has multiple topics. "
        "Recheck actual free space before each topic; these safe-start flags are based on the current measurement.",
        "",
    ]
    for name, topic in plan["topics"].items():
        ids = topic["remaining_ids"]
        state = "SAFE TO START" if topic["safe_to_start"] else "UNSAFE"
        if not ids:
            state = "AVAILABLE ITEMS COMPLETE"
        lines.extend(
            [
                f"## {topic['priority']} {name}",
                "",
                f"Videos: {topic['video_count']}",
                f"Remaining: {len(ids)}",
                f"Estimated remaining: {topic['remaining_estimate_bytes'] / GIB:.2f} GiB "
                "(before margin)",
                f"Topic status: {state}",
                "",
            ]
        )
        for video_id in ids:
            title = records[video_id].get("title") or "(title unknown)"
            lines.append(f"- [ ] {title} (`{video_id}`)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="channel_distill")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument(
            "--workspace", type=Path,
            help="workspace root (default: $YTD_WORKSPACE, else the current directory)",
        )
        return sub

    inventory_command = add("inventory", "refresh channel video metadata")
    inventory_command.add_argument("--channel-id", required=True)
    inventory_command.add_argument("--skip-playlists", action="store_true")
    inventory_command.add_argument(
        "--topic-rules", type=Path,
        help="title rules JSON (default: <workspace>/config/topic-rules.json; absent means all unknown)",
    )
    plan_command = add("plan-download", "measure storage and plan topic downloads")
    plan_command.add_argument("--output", type=Path, help="default: <workspace>/DOWNLOAD_PLAN.md")
    plan_command.add_argument("--min-free-space-gb", type=float, default=30)
    plan_command.add_argument("--safety-reserve-percent", type=float, default=0.25)
    plan_command.add_argument("--margin", type=float, default=1.5)
    download_command = add("download", "download one storage-safe topic")
    download_command.add_argument("--topic", required=True)
    download_command.add_argument("--video-id", help="target one item in the selected topic")
    download_command.add_argument("--ffprobe", type=Path, help="ffprobe binary (default: $YTD_FFMPEG_DIR, then PATH)")
    download_command.add_argument("--min-free-space-gb", type=float, default=30)
    download_command.add_argument("--safety-reserve-percent", type=float, default=0.25)
    download_command.add_argument("--margin", type=float, default=1.5)
    download_command.add_argument("--max-videos", type=int)
    download_command.add_argument("--sync-wiki", action="store_true", help="run one Wiki gate sync afterwards")
    download_command.add_argument("--candidates", type=Path, help="candidates JSON for --sync-wiki")
    add("prepare-sources", "group timed transcript cues")
    coverage_command = add("audit-coverage", "report priority-topic source coverage gaps")
    coverage_command.add_argument("--output", type=Path, help="default: <workspace>/data/manifest/coverage-report.json")
    coverage_command.add_argument("--priority", default="P0", help="topic priority to audit (default: P0)")
    wiki_command = add("compile-wiki", "compile the derived, traceable Markdown wiki")
    wiki_command.add_argument("--candidates", type=Path, help="default: <workspace>/knowledge/p0_candidates.json")
    wiki_command.add_argument("--coverage", type=Path, help="default: <workspace>/data/manifest/coverage-report.json")
    wiki_command.add_argument("--wiki-dir", type=Path, help="default: <workspace>/knowledge/wiki")
    wiki_gate_command = add("wiki-gate", "classify one extraction record for the Wiki handoff")
    wiki_gate_command.add_argument("--record", type=Path, required=True, help="one manifest/evidence record JSON")
    wiki_gate_command.add_argument("--log", type=Path, help="optional append-only JSONL gate log")
    reading_command = add("build-reading-views", "render timestamp-free reading text with reversible source anchors")
    reading_command.add_argument("--source-dir", type=Path, help="default: <workspace>/data/processing/source_chunks")
    reading_command.add_argument("--output-dir", type=Path, help="default: <workspace>/data/processing/reading_views")
    transcribe_command = add("transcribe", "run local ASR for one verified video")
    transcribe_command.add_argument("--video-id", required=True)
    transcribe_command.add_argument("--ffmpeg", type=Path, help="ffmpeg binary (default: $YTD_FFMPEG_DIR, then PATH)")
    transcribe_command.add_argument("--model-path", type=Path, help="explicit local model directory")
    transcribe_command.add_argument("--model-name", help="model directory under <workspace>/data/models")
    transcribe_command.add_argument("--min-free-space-gb", type=float, default=30)
    transcribe_command.add_argument(
        "--postprocess", action="store_true",
        help="after READY, run source preparation, reading views and coverage once",
    )
    transcribe_command.add_argument("--sync-wiki", action="store_true", help="with --postprocess, run one Wiki gate sync")
    transcribe_command.add_argument("--candidates", type=Path, help="candidates JSON for --sync-wiki")
    args = parser.parse_args(argv)

    workspace = resolve_workspace(args.workspace)
    args.workspace = workspace.root
    args.data_dir = workspace.data

    if args.command == "download":
        return _download_topic(args)
    if args.command == "prepare-sources":
        return _prepare_sources(args)
    if args.command == "audit-coverage":
        args.output = args.output or workspace.manifest / "coverage-report.json"
        return _audit_coverage(args)
    if args.command == "compile-wiki":
        args.candidates = args.candidates or workspace.knowledge / "p0_candidates.json"
        args.coverage = args.coverage or workspace.manifest / "coverage-report.json"
        args.wiki_dir = args.wiki_dir or workspace.knowledge / "wiki"
        return _compile_wiki(args)
    if args.command == "wiki-gate":
        return _wiki_gate(args)
    if args.command == "build-reading-views":
        args.source_dir = args.source_dir or workspace.processing / "source_chunks"
        args.output_dir = args.output_dir or workspace.processing / "reading_views"
        return _build_reading_views(args)
    if args.command == "transcribe":
        return _transcribe_one(args)

    if args.command == "inventory":
        videos_path = workspace.manifest / "videos.json"
        csv_path = workspace.manifest / "videos.csv"
        try:
            rules = load_topic_rules(args.topic_rules or workspace.config / "topic-rules.json")
            existing = load_manifest(videos_path)
            incoming = fetch_channel_inventory(
                args.channel_id, include_playlists=not args.skip_playlists
            )
            videos = classify_inventory(merge_inventory(existing, incoming), rules)
            save_manifest(videos_path, videos)
            export_csv(csv_path, videos)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Inventory failed: {exc}", file=sys.stderr)
            return 1
        print(f"Indexed {len(videos)} unique videos in {videos_path}")
        return 0
    if args.command == "plan-download":
        try:
            videos = load_manifest(workspace.manifest / "videos.json")
            if not videos:
                raise ValueError("inventory is empty; run inventory first")
            workspace.data.mkdir(parents=True, exist_ok=True)
            free_bytes = shutil.disk_usage(workspace.data).free
            plan = build_download_plan(
                videos,
                free_bytes=free_bytes,
                min_free_bytes=int(args.min_free_space_gb * GIB),
                safety_reserve_percent=args.safety_reserve_percent,
                margin=args.margin,
            )
            output = args.output or workspace.root / "DOWNLOAD_PLAN.md"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(_render_download_plan(plan, videos), encoding="utf-8")
            topics_path = workspace.manifest / "topics.json"
            topics_path.parent.mkdir(parents=True, exist_ok=True)
            topics_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (OSError, ValueError) as exc:
            print(f"Plan failed: {exc}", file=sys.stderr)
            return 1
        print(f"Planned {len(plan['topics'])} topics in {output}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
