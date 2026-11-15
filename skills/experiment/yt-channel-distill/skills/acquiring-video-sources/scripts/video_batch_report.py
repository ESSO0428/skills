#!/usr/bin/env python3
"""Reconcile acquisition, AGY fallback, and final source coverage for one frozen batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


_DOWNLOAD_FAILURES = {"DOWNLOAD_FAILED", "VERIFY_FAILED", "UNAVAILABLE", "VIDEO_DOWNLOAD_BLOCKED"}
_NO_SUBTITLE = {"ASR_NEEDED", "FETCH_FAILED", "NO_SUBTITLE"}
_OTHER_TRANSCRIPT_FAILURES = {"PARSE_FAILED", "ASR_INVALID_OUTPUT"}
_BAD_MEDIA = {"BAD_TRACK", "CORRUPT", "DAMAGED", "INVALID_MEDIA"}
_AGY_SUCCESS = {"READ_MEDIA", "READ_SUCCESS", "SUCCESS", "COMPLETED"}
_AGY_CAPABILITIES = {"UNVERIFIED", "AVAILABLE", "UNAVAILABLE"}


class ReportError(ValueError):
    """Input cannot support a trustworthy batch report."""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReportError(f"Expected a JSON object: {path}")
    return payload


def _records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    videos = payload.get("videos")
    if not isinstance(videos, dict):
        raise ReportError("Manifest must contain a videos object keyed by video ID")
    result: dict[str, dict[str, Any]] = {}
    for video_id, record in videos.items():
        if not isinstance(video_id, str) or not isinstance(record, dict):
            raise ReportError("Every manifest video must be an object keyed by video ID")
        result[video_id] = record
    return result


def _expected_ids(batch: dict[str, Any]) -> list[str]:
    values = batch.get("expected_video_ids")
    if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
        raise ReportError("Batch must contain a nonempty expected_video_ids list of strings")
    if len(set(values)) != len(values):
        raise ReportError("expected_video_ids contains duplicates")
    return sorted(values)


def _agy_results(batch: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = batch.get("agy_results", {})
    if not isinstance(results, dict):
        raise ReportError("Batch agy_results must be an object keyed by video ID")
    if any(not isinstance(video_id, str) or not isinstance(item, dict) for video_id, item in results.items()):
        raise ReportError("Every AGY result must be an object keyed by video ID")
    return results


def _transcript_status(record: dict[str, Any]) -> str:
    return str(record.get("transcript_status") or "MISSING_STATUS").upper()


def _media_integrity(record: dict[str, Any]) -> str:
    return str(record.get("media_integrity_status") or "").upper()


def _bad_track(record: dict[str, Any]) -> bool:
    # ASR_FAILED is the user's whole-video failure bucket; retain the original
    # error separately because the status alone does not prove physical damage.
    return _transcript_status(record) == "ASR_FAILED" or _media_integrity(record) in _BAD_MEDIA


def _no_subtitle(record: dict[str, Any]) -> bool:
    return _transcript_status(record) in _NO_SUBTITLE


def _other_transcript_problem(record: dict[str, Any]) -> bool:
    return (
        _transcript_status(record) in _OTHER_TRANSCRIPT_FAILURES | {"READY_PARTIAL"}
        or bool(record.get("transcript_unavailable_segments"))
    )


def _agy_provenance_complete(result: dict[str, Any]) -> bool:
    prompt_hash = result.get("prompt_sha256")
    valid_hash = (
        isinstance(prompt_hash, str)
        and len(prompt_hash) == 64
        and all(char in "0123456789abcdefABCDEF" for char in prompt_hash)
    )
    return bool(result.get("agy_cli_version") and result.get("model") and valid_hash)


def _agy_accepted(result: dict[str, Any]) -> bool:
    return (
        str(result.get("status") or "").upper() in _AGY_SUCCESS
        and str(result.get("review_status") or "").upper() == "ACCEPTED"
        and result.get("coverage_complete") is True
        and _agy_provenance_complete(result)
    )


def _partition_media(
    expected: list[str], records: dict[str, dict[str, Any]]
) -> tuple[list[str], list[str], list[str], list[str]]:
    verified: list[str] = []
    failed: list[str] = []
    pending: list[str] = []
    conflicts: list[str] = []
    for video_id in expected:
        record = records.get(video_id)
        if record is None:
            pending.append(video_id)
            continue
        status = str(record.get("status") or "").upper()
        is_verified = record.get("verified") is True
        is_failed = status in _DOWNLOAD_FAILURES and not is_verified
        if is_verified and status in _DOWNLOAD_FAILURES:
            conflicts.append(video_id)
        if is_verified:
            verified.append(video_id)
        elif is_failed:
            failed.append(video_id)
        else:
            pending.append(video_id)
    return verified, failed, pending, conflicts


def build_report(
    stage: str,
    manifest: dict[str, Any],
    batch: dict[str, Any],
) -> dict[str, Any]:
    records = _records(manifest)
    expected = _expected_ids(batch)
    agy_results = _agy_results(batch)
    remote_capability = str(batch.get("agy_remote_capability") or "UNVERIFIED").upper()
    if remote_capability not in _AGY_CAPABILITIES:
        raise ReportError("agy_remote_capability must be UNVERIFIED, AVAILABLE, or UNAVAILABLE")

    verified, download_failed, pending, media_conflicts = _partition_media(expected, records)
    missing_manifest_ids = sorted(set(expected) - set(records))
    out_of_scope_agy_ids = sorted(set(agy_results) - set(expected))

    bad_track_ids: list[str] = []
    no_subtitle_ids: list[str] = []
    other_problem_ids: list[str] = []
    local_candidates: list[str] = []
    for video_id in verified:
        record = records[video_id]
        if _bad_track(record):
            bad_track_ids.append(video_id)
        elif _no_subtitle(record):
            no_subtitle_ids.append(video_id)
        elif _other_transcript_problem(record):
            other_problem_ids.append(video_id)
    local_candidates = sorted(set(bad_track_ids + no_subtitle_ids + other_problem_ids))
    remote_candidates = download_failed if remote_capability == "AVAILABLE" else []

    accepted_agy_ids = sorted(
        video_id for video_id, result in agy_results.items()
        if video_id in expected and _agy_accepted(result)
    )
    attempted_ids = sorted(set(agy_results) & set(expected))
    attempted_not_repaired = sorted(set(attempted_ids) - set(accepted_agy_ids))
    missing_agy_provenance_ids = sorted(
        video_id for video_id in attempted_ids
        if not _agy_provenance_complete(agy_results[video_id])
    )
    ready_transcript_ids = sorted(
        video_id for video_id in expected
        if video_id in records
        and _transcript_status(records[video_id]) == "READY"
        and records[video_id].get("transcript_downloaded") is not False
    )
    transcript_status_ids: dict[str, list[str]] = {}
    for video_id in expected:
        status = _transcript_status(records[video_id]) if video_id in records else "MISSING_RECORD"
        transcript_status_ids.setdefault(status, []).append(video_id)
    transcript_status_ids = {
        status: sorted(video_ids) for status, video_ids in sorted(transcript_status_ids.items())
    }
    usable_sources = sorted(set(ready_transcript_ids) | set(accepted_agy_ids))
    final_failed = sorted(set(expected) - set(usable_sources))

    agy_repaired_bad_track = sorted(
        video_id for video_id in accepted_agy_ids
        if video_id in records and _bad_track(records[video_id])
    )
    agy_repaired_no_subtitle = sorted(
        video_id for video_id in accepted_agy_ids
        if video_id in records and _no_subtitle(records[video_id])
    )

    failures: list[str] = []
    if missing_manifest_ids:
        failures.append("expected IDs missing from manifest")
    if out_of_scope_agy_ids:
        failures.append("AGY results contain IDs outside the frozen batch")
    if media_conflicts:
        failures.append("manifest marks a download-failed record as verified")
    if set(verified) | set(download_failed) | set(pending) != set(expected):
        failures.append("media outcome sets do not cover the frozen batch")
    if set(verified) & set(download_failed) or set(verified) & set(pending) or set(download_failed) & set(pending):
        failures.append("media outcome sets overlap")
    if set(usable_sources) | set(final_failed) != set(expected):
        failures.append("final source outcome sets do not cover the frozen batch")
    if set(usable_sources) & set(final_failed):
        failures.append("final source outcome sets overlap")

    report: dict[str, Any] = {
        "run_id": batch.get("run_id"),
        "stage": stage,
        "expected_video_ids": expected,
        "expected_count": len(expected),
        "media": {
            "verified_ids": verified,
            "verified_count": len(verified),
            "download_failed_ids": download_failed,
            "download_failed_count": len(download_failed),
            "pending_ids": pending,
            "pending_count": len(pending),
        },
        "transcripts": {
            "status_ids": transcript_status_ids,
            "ready_ids": ready_transcript_ids,
            "ready_count": len(ready_transcript_ids),
        },
        "reconciliation": {
            "status": "FAIL" if failures else "PASS",
            "issues": failures,
            "missing_manifest_ids": missing_manifest_ids,
            "out_of_scope_agy_ids": out_of_scope_agy_ids,
            "media_conflict_ids": media_conflicts,
        },
    }

    if stage == "agy-plan":
        report["agy"] = {
            "remote_capability": remote_capability,
            "local_candidate_ids": local_candidates,
            "local_candidate_count": len(local_candidates),
            "direct_failure_attemptable_ids": sorted(remote_candidates),
            "direct_failure_attemptable_count": len(remote_candidates),
            "direct_failures_not_attemptable_ids": (
                download_failed if remote_capability != "AVAILABLE" else []
            ),
            "categories": {
                "asr_failed_ids": sorted(video_id for video_id in bad_track_ids
                                          if _transcript_status(records[video_id]) == "ASR_FAILED"),
                "confirmed_bad_media_ids": sorted(video_id for video_id in bad_track_ids
                                                   if _media_integrity(records[video_id]) in _BAD_MEDIA),
                "no_subtitle_ids": no_subtitle_ids,
                "other_transcript_problem_ids": other_problem_ids,
            },
            "attempted_ids": attempted_ids,
            "attempted_but_not_repaired_ids": attempted_not_repaired,
        }
        report["next_action"] = (
            "Run the bounded AGY capability check before considering remote download failures."
            if remote_capability == "UNVERIFIED"
            else "Review the listed IDs and user-approved usage cap before any AGY run."
        )
    elif stage == "final":
        report["agy"] = {
            "attempted_ids": attempted_ids,
            "accepted_ids": accepted_agy_ids,
            "attempted_but_not_repaired_ids": attempted_not_repaired,
            "missing_provenance_ids": missing_agy_provenance_ids,
        }
        report["sources"] = {
            "ready_transcript_ids": ready_transcript_ids,
            "agy_repaired_bad_track_ids": agy_repaired_bad_track,
            "agy_repaired_no_subtitle_ids": agy_repaired_no_subtitle,
            "usable_ids": usable_sources,
            "usable_count": len(usable_sources),
            "final_failed_ids": final_failed,
            "final_failed_count": len(final_failed),
        }
        if missing_agy_provenance_ids:
            report["reconciliation"]["status"] = "FAIL"
            report["reconciliation"]["issues"].append("AGY attempts are missing version/model/prompt provenance")
        report["next_action"] = (
            "Proceed to evidence review only after every listed ID is reconciled and unresolved coverage is visible."
        )
    elif stage != "acquisition":
        raise ReportError(f"Unsupported stage: {stage}")

    return report


def _human_report(report: dict[str, Any]) -> str:
    lines = [
        f"批次：{report.get('run_id') or '(未命名)'} / 階段：{report['stage']}",
        f"預期影片：{report['expected_count']} 部",
        f"實際已驗證本機影片：{report['media']['verified_count']} 部",
        f"直接下載失敗：{report['media']['download_failed_count']} 部",
        f"統計集合核對：{report['reconciliation']['status']}",
    ]
    if report["stage"] == "agy-plan":
        agy = report["agy"]
        lines.extend([
            f"本機可嘗試 AGY：{agy['local_candidate_count']} 部",
            f"  ASR_FAILED 全片失敗候選：{len(agy['categories']['asr_failed_ids'])} 部 {agy['categories']['asr_failed_ids']}",
            f"  明確媒體壞軌標記：{agy['categories']['confirmed_bad_media_ids']}",
            f"  沒有可用字幕：{len(agy['categories']['no_subtitle_ids'])} 部 {agy['categories']['no_subtitle_ids']}",
            f"  其他逐字稿問題：{len(agy['categories']['other_transcript_problem_ids'])} 部 {agy['categories']['other_transcript_problem_ids']}",
            f"遠端抓取失敗可嘗試：{agy['direct_failure_attemptable_count']} 部",
            f"遠端 AGY 能力：{agy['remote_capability']}",
            report["next_action"],
        ])
    elif report["stage"] == "final":
        lines.extend([
            f"可供後續蒸餾的來源：{report['sources']['usable_count']} 部 {report['sources']['usable_ids']}",
            f"AGY 修復原 ASR_FAILED 候選：{report['sources']['agy_repaired_bad_track_ids']}",
            f"最終未修復：{report['sources']['final_failed_count']} 部 {report['sources']['final_failed_ids']}",
            f"AGY 嘗試但未修復：{report['agy']['attempted_but_not_repaired_ids']}",
            report["next_action"],
        ])
    if report["reconciliation"]["issues"]:
        lines.append("核對問題：" + "；".join(report["reconciliation"]["issues"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("acquisition", "agy-plan", "final"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="Write the full report as JSON")
    parser.add_argument("--output", type=Path, help="optional UTF-8 JSON report path")
    args = parser.parse_args()
    try:
        report = build_report(args.stage, _read_json(args.manifest), _read_json(args.batch))
    except (OSError, json.JSONDecodeError, ReportError) as exc:
        print(f"video batch report failed: {exc}", file=sys.stderr)
        return 2
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.stage} report to {args.output}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _human_report(report))
    return 0 if report["reconciliation"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
