from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "acquiring-video-sources" / "scripts" / "video_batch_report.py"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _invoke(tmp_path: Path, stage: str, manifest: dict, batch: dict) -> subprocess.CompletedProcess[str]:
    manifest_path = tmp_path / "videos.json"
    batch_path = tmp_path / "batch.json"
    _write_json(manifest_path, manifest)
    _write_json(batch_path, batch)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--stage",
            stage,
            "--manifest",
            str(manifest_path),
            "--batch",
            str(batch_path),
            "--json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_agy_plan_separates_local_candidates_from_direct_download_failures(tmp_path: Path) -> None:
    manifest = {
        "videos": {
            "ready": {"verified": True, "transcript_status": "READY"},
            "bad-track": {"verified": True, "transcript_status": "ASR_FAILED"},
            "no-captions": {"verified": True, "transcript_status": "ASR_NEEDED"},
            "unfetchable": {"verified": False, "status": "DOWNLOAD_FAILED"},
        }
    }
    batch = {
        "run_id": "batch-1",
        "expected_video_ids": ["ready", "bad-track", "no-captions", "unfetchable"],
        "agy_remote_capability": "UNAVAILABLE",
    }

    result = _invoke(tmp_path, "agy-plan", manifest, batch)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["media"]["verified_count"] == 3
    assert payload["media"]["download_failed_ids"] == ["unfetchable"]
    assert payload["agy"]["local_candidate_ids"] == ["bad-track", "no-captions"]
    assert payload["agy"]["categories"]["asr_failed_ids"] == ["bad-track"]
    assert payload["agy"]["categories"]["no_subtitle_ids"] == ["no-captions"]
    assert payload["agy"]["direct_failure_attemptable_ids"] == []
    assert payload["reconciliation"]["status"] == "PASS"


def test_final_report_reconciles_recovered_sources_and_unresolved_ids(tmp_path: Path) -> None:
    manifest = {
        "videos": {
            "ready": {"verified": True, "transcript_status": "READY"},
            "bad-track": {"verified": True, "transcript_status": "ASR_FAILED"},
            "no-captions": {"verified": True, "transcript_status": "ASR_NEEDED"},
            "unfetchable": {"verified": False, "status": "DOWNLOAD_FAILED"},
        }
    }
    batch = {
        "run_id": "batch-1",
        "expected_video_ids": ["ready", "bad-track", "no-captions", "unfetchable"],
        "agy_remote_capability": "UNAVAILABLE",
        "agy_results": {
            "bad-track": {
                "status": "READ_MEDIA",
                "review_status": "ACCEPTED",
                "coverage_complete": True,
                "agy_cli_version": "1.2.8",
                "model": "gemini-flash-test",
                "prompt_sha256": "a" * 64,
            },
            "no-captions": {
                "status": "INACCESSIBLE",
                "review_status": "REJECTED",
                "coverage_complete": False,
                "agy_cli_version": "1.2.8",
                "model": "gemini-flash-test",
                "prompt_sha256": "b" * 64,
            },
        },
    }

    result = _invoke(tmp_path, "final", manifest, batch)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["media"]["verified_count"] == 3
    assert payload["sources"]["usable_ids"] == ["bad-track", "ready"]
    assert payload["sources"]["agy_repaired_bad_track_ids"] == ["bad-track"]
    assert payload["sources"]["final_failed_ids"] == ["no-captions", "unfetchable"]
    assert payload["agy"]["attempted_but_not_repaired_ids"] == ["no-captions"]
    assert payload["reconciliation"]["status"] == "PASS"


def test_final_report_does_not_accept_agy_success_without_version_provenance(tmp_path: Path) -> None:
    manifest = {
        "videos": {
            "failed": {"verified": True, "transcript_status": "ASR_FAILED"},
        }
    }
    batch = {
        "run_id": "batch-2",
        "expected_video_ids": ["failed"],
        "agy_results": {
            "failed": {
                "status": "READ_MEDIA",
                "review_status": "ACCEPTED",
                "coverage_complete": True,
                "model": "gemini-flash-test",
                "prompt_sha256": "c" * 64,
            },
        },
    }

    result = _invoke(tmp_path, "final", manifest, batch)

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["sources"]["usable_ids"] == []
    assert payload["agy"]["missing_provenance_ids"] == ["failed"]
    assert payload["reconciliation"]["status"] == "FAIL"


def test_report_rejects_agy_results_outside_the_frozen_batch(tmp_path: Path) -> None:
    manifest = {"videos": {"expected": {"verified": True, "transcript_status": "READY"}}}
    batch = {
        "run_id": "batch-1",
        "expected_video_ids": ["expected"],
        "agy_results": {"unexpected": {"status": "READ_MEDIA", "review_status": "ACCEPTED"}},
    }

    result = _invoke(tmp_path, "final", manifest, batch)

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["reconciliation"]["status"] == "FAIL"
    assert payload["reconciliation"]["out_of_scope_agy_ids"] == ["unexpected"]


def test_report_rejects_an_empty_frozen_batch(tmp_path: Path) -> None:
    result = _invoke(
        tmp_path,
        "acquisition",
        {"videos": {}},
        {"run_id": "empty", "expected_video_ids": []},
    )

    assert result.returncode == 2
    assert "expected_video_ids" in result.stderr


def test_final_report_rejects_malformed_prompt_hash_as_agy_provenance(tmp_path: Path) -> None:
    result = _invoke(
        tmp_path,
        "final",
        {"videos": {"failed": {"verified": True, "transcript_status": "ASR_FAILED"}}},
        {
            "run_id": "batch-3",
            "expected_video_ids": ["failed"],
            "agy_results": {
                "failed": {
                    "status": "READ_MEDIA",
                    "review_status": "ACCEPTED",
                    "coverage_complete": True,
                    "agy_cli_version": "1.2.8",
                    "model": "gemini-flash-test",
                    "prompt_sha256": "not-a-sha256",
                },
            },
        },
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["sources"]["usable_ids"] == []
    assert payload["agy"]["missing_provenance_ids"] == ["failed"]


def test_json_report_can_be_written_as_utf8_for_the_next_script_stage(tmp_path: Path) -> None:
    manifest_path = tmp_path / "videos.json"
    batch_path = tmp_path / "batch.json"
    output_path = tmp_path / "processing" / "agy-plan.json"
    _write_json(manifest_path, {"videos": {"video01": {"verified": True, "transcript_status": "ASR_FAILED"}}})
    _write_json(batch_path, {"run_id": "batch-1", "expected_video_ids": ["video01"]})

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--stage",
            "agy-plan",
            "--manifest",
            str(manifest_path),
            "--batch",
            str(batch_path),
            "--json",
            "--output",
            str(output_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["agy"]["categories"]["asr_failed_ids"] == ["video01"]
