from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "acquiring-video-sources" / "scripts" / "agy_batch_jobs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("agy_batch_jobs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixture(tmp_path: Path):
    data_dir = tmp_path / "data"
    local_file = data_dir / "videos" / "asrfail1.mp4"
    no_subtitle_file = data_dir / "videos" / "nosub01.mp4"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"media")
    no_subtitle_file.write_bytes(b"media")
    manifest_path = data_dir / "manifest" / "videos.json"
    batch_path = data_dir / "processing" / "batch.json"
    report_path = data_dir / "processing" / "agy-plan.json"
    approved_path = data_dir / "processing" / "approved.json"
    usage_path = data_dir / "processing" / "usage.json"
    output_dir = data_dir / "processing" / "agy-jobs"
    ids = ["asrfail1", "nosub01", "partial1", "remote1"]
    _write(
        manifest_path,
        {
            "videos": {
                "asrfail1": {"video_id": "asrfail1", "url": "https://youtu.be/asrfail1", "duration": 600, "verified": True, "canonical_video_path": str(local_file), "transcript_status": "ASR_FAILED"},
                "nosub01": {"video_id": "nosub01", "url": "https://youtu.be/nosub01", "duration": 1200, "verified": True, "canonical_video_path": str(no_subtitle_file), "transcript_status": "ASR_NEEDED"},
                "partial1": {"video_id": "partial1", "url": "https://youtu.be/partial1", "duration": 600, "verified": True, "canonical_video_path": str(local_file), "transcript_status": "READY_PARTIAL"},
                "remote1": {"video_id": "remote1", "url": "https://youtu.be/remote1", "duration": 600, "verified": False, "status": "DOWNLOAD_FAILED", "transcript_status": "MISSING"},
            }
        },
    )
    _write(
        batch_path,
        {"run_id": "batch-1", "expected_video_ids": ids, "agy_remote_capability": "AVAILABLE", "agy_results": {}},
    )
    _write(
        report_path,
        {
            "run_id": "batch-1",
            "stage": "agy-plan",
            "expected_video_ids": ids,
            "reconciliation": {"status": "PASS"},
            "agy": {
                "remote_capability": "AVAILABLE",
                "local_candidate_ids": ["asrfail1", "nosub01", "partial1"],
                "direct_failure_attemptable_ids": ["remote1"],
                "categories": {
                    "asr_failed_ids": ["asrfail1"],
                    "confirmed_bad_media_ids": [],
                    "no_subtitle_ids": ["nosub01"],
                    "other_transcript_problem_ids": ["partial1"],
                },
            },
        },
    )
    _write(approved_path, ["asrfail1", "nosub01"])
    _write(
        usage_path,
        {
            "checked_at": "2026-09-22T00:00:00Z",
            "five_hour_remaining_percent": 60,
            "weekly_remaining_percent": 30,
            "pilot_video_id": "pilot01",
            "pilot_model": "gemini-3.8-flash-medium",
            "pilot_source_mode": "local_file",
            "pilot_duration_seconds": 600,
            "pilot_five_hour_used_percent": 10,
            "pilot_weekly_used_percent": 5,
            "safety_multiplier": 1.5,
        },
    )
    return manifest_path, batch_path, report_path, approved_path, usage_path, output_dir


def _prepare(module, paths):
    manifest, batch, report, approved, usage, output_dir = paths
    return module.prepare_jobs(
        report,
        manifest,
        batch,
        approved,
        usage,
        output_dir,
        model="gemini-3.8-flash-medium",
        project_root=ROOT,
        data_dir=manifest.parent.parent,
        cli_version="1.2.8",
    )


def test_prepare_accepts_only_explicit_ids_in_full_video_fallback_categories(tmp_path: Path) -> None:
    module = _load_module()
    paths = _fixture(tmp_path)
    manifest, batch, report, _, usage, _ = paths

    budget = module.build_budget_report(
        report,
        manifest,
        batch,
        usage,
        model="gemini-3.8-flash-medium",
        project_root=ROOT,
        data_dir=manifest.parent.parent,
    )
    assert budget["eligible_by_source_mode"]["local_file"] == ["asrfail1", "nosub01"]
    assert budget["budget"]["recommended_max_video_count"] == 2

    result = _prepare(module, paths)

    assert result["budget"]["recommended_max_video_count"] == 2
    assert [job["video_id"] for job in result["jobs"]] == ["asrfail1", "nosub01"]
    assert result["jobs"][0]["source_mode"] == "local_file"
    assert result["jobs"][1]["source_mode"] == "local_file"
    assert result["jobs"][0]["prompt_sha256"]
    assert "--dangerously-skip-permissions" not in result["jobs"][0]["command"]
    assert "partial1" not in [job["video_id"] for job in result["jobs"]]


def test_prepare_rejects_approval_above_estimated_usage_budget(tmp_path: Path) -> None:
    module = _load_module()
    paths = list(_fixture(tmp_path))
    approved_path = paths[3]
    _write(approved_path, ["asrfail1", "nosub01"])
    usage_path = paths[4]
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    usage["weekly_remaining_percent"] = 10
    _write(usage_path, usage)

    with pytest.raises(ValueError, match="approved IDs exceed duration-scaled"):
        _prepare(module, paths)


def test_prepare_requires_manual_usage_snapshot_and_rejects_unproven_remote_candidate(tmp_path: Path) -> None:
    module = _load_module()
    paths = list(_fixture(tmp_path))
    usage_path = paths[4]
    _write(usage_path, {"five_hour_remaining_percent": 60})
    with pytest.raises(ValueError, match="usage snapshot is incomplete"):
        _prepare(module, paths)

    paths = list(_fixture(tmp_path / "remote"))
    _write(paths[3], ["remote1"])
    batch_path = paths[1]
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    batch["agy_remote_capability"] = "UNVERIFIED"
    _write(batch_path, batch)
    report_path = paths[2]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["agy"]["remote_capability"] = "UNVERIFIED"
    report["agy"]["direct_failure_attemptable_ids"] = []
    _write(report_path, report)
    with pytest.raises(ValueError, match="not AGY-eligible"):
        _prepare(module, paths)


def test_run_requires_execute_and_records_cli_output_without_marking_it_accepted(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    paths = _fixture(tmp_path)
    manifest_path, batch_path, _, _, _, _ = paths
    prepared = _prepare(module, paths)
    jobs_path = paths[-1] / "jobs.json"
    calls = []

    def fake_run(command, **kwargs):
        if command == ["agy", "--version"]:
            return SimpleNamespace(returncode=0, stdout="1.2.8", stderr="")
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"coverage":"PARTIAL"}', stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="requires explicit --execute"):
        module.run_jobs(jobs_path, batch_path, manifest_path, execute=False)

    result = module.run_jobs(jobs_path, batch_path, manifest_path, execute=True)

    assert len(calls) == len(prepared["jobs"]) == 2
    assert result["completed_count"] == 2
    ledger = json.loads(batch_path.read_text(encoding="utf-8"))
    assert all(item["status"] == "OUTPUT_CAPTURED_REVIEW_REQUIRED" for item in ledger["agy_results"].values())
    assert all(item["review_status"] == "PENDING" for item in ledger["agy_results"].values())

    usage_after_path = paths[0].parent / "processing" / "usage-after.json"
    _write(
        usage_after_path,
        {"checked_at": "2026-09-22T00:30:00Z", "five_hour_remaining_percent": 50, "weekly_remaining_percent": 31},
    )
    usage_result = module.record_usage_after(jobs_path, batch_path, usage_after_path)
    assert usage_result["five_hour_used_percent"] == 10
    assert usage_result["weekly_used_percent"] is None
    assert usage_result["five_hour_per_video_percent"] == 5
