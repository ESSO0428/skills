from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "acquiring-video-sources" / "scripts" / "acquire_video_batch.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("acquire_video_batch", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup(tmp_path: Path, records: dict, ids: list[str]):
    data_dir = tmp_path / "data"
    manifest_path = data_dir / "manifest" / "videos.json"
    batch_path = data_dir / "processing" / "batch.json"
    report_path = data_dir / "processing" / "acquisition-report.json"
    manifest_path.parent.mkdir(parents=True)
    batch_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({"videos": records}), encoding="utf-8")
    batch_path.write_text(
        json.dumps({"run_id": "batch-test", "expected_video_ids": ids}), encoding="utf-8"
    )
    return data_dir, manifest_path, batch_path, report_path


def _record(video_id: str, **updates):
    record = {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": video_id,
        "duration": 60,
        "status": "DISCOVERED",
        "verified": False,
        "video_downloaded": False,
        "transcript_downloaded": False,
        "transcript_status": None,
    }
    record.update(updates)
    return record


def test_plan_uses_only_frozen_ids_and_does_not_change_the_manifest(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    records = {"video01": _record("video01"), "video02": _record("video02"), "outside": _record("outside")}
    data_dir, manifest_path, batch_path, _ = _setup(tmp_path, records, ["video02", "video01"])
    before = manifest_path.read_bytes()
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: SimpleNamespace(free=10_000_000_000))

    result = module.build_plan(
        manifest_path, batch_path, data_dir, min_free_bytes=1, safety_reserve_percent=0.1, margin=1.5
    )

    assert result["expected_video_ids"] == ["video02", "video01"]
    assert result["target_count"] == 2
    assert result["storage"]["safe_to_start"] is True
    assert manifest_path.read_bytes() == before


def test_freeze_persists_explicit_scope_and_never_overwrites_existing_batch(tmp_path: Path) -> None:
    module = _load_module()
    records = {"video01": _record("video01"), "video02": _record("video02")}
    data_dir, manifest_path, batch_path, _ = _setup(tmp_path, records, ["video02", "video01"])
    ids_path = data_dir / "processing" / "selected-ids.json"
    frozen_path = data_dir / "processing" / "frozen.json"
    ids_path.write_text(json.dumps(["video02", "video01"]), encoding="utf-8")

    created = module.freeze_batch(manifest_path, ids_path, frozen_path, run_id="selected-test")

    assert created["expected_video_ids"] == ["video02", "video01"]
    assert created["agy_remote_capability"] == "UNVERIFIED"
    assert json.loads(frozen_path.read_text(encoding="utf-8"))["run_id"] == "selected-test"
    with pytest.raises(FileExistsError):
        module.freeze_batch(manifest_path, ids_path, frozen_path, run_id="must-not-overwrite")


def test_plan_rejects_empty_or_duplicate_frozen_scope(tmp_path: Path) -> None:
    module = _load_module()
    data_dir, manifest_path, batch_path, _ = _setup(tmp_path, {"video01": _record("video01")}, [])
    with pytest.raises(ValueError, match="non-empty"):
        module.build_plan(manifest_path, batch_path, data_dir, min_free_bytes=1, safety_reserve_percent=0, margin=1)

    batch_path.write_text(
        json.dumps({"run_id": "batch-test", "expected_video_ids": ["video01", "video01"]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate"):
        module.build_plan(manifest_path, batch_path, data_dir, min_free_bytes=1, safety_reserve_percent=0, margin=1)

    ids_path = data_dir / "processing" / "bad-ids.json"
    ids_path.write_text(json.dumps(["video01", "missing"]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing from manifest"):
        module.freeze_batch(manifest_path, ids_path, tmp_path / "new-batch.json", run_id="bad")


def test_run_aborts_before_network_if_whole_batch_storage_guard_fails(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    data_dir, manifest_path, batch_path, report_path = _setup(
        tmp_path, {"video01": _record("video01")}, ["video01"]
    )
    calls = []
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: SimpleNamespace(free=100))
    monkeypatch.setattr(module, "download_one", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(RuntimeError, match="Insufficient storage"):
        module.run_batch(
            manifest_path,
            batch_path,
            data_dir,
            report_path,
            ffprobe=Path("ffprobe"),
            ffmpeg="ffmpeg",
            model_path=Path("model"),
            min_free_bytes=50,
            safety_reserve_percent=0.25,
            margin=1.5,
        )

    assert calls == []
    assert not report_path.exists()


def test_run_processes_only_frozen_ids_and_falls_back_to_asr_after_no_subtitles(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    records = {
        "video01": _record("video01"),
        "video02": _record("video02"),
        "outside": _record("outside"),
    }
    data_dir, manifest_path, batch_path, report_path = _setup(tmp_path, records, ["video02", "video01"])
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: SimpleNamespace(free=10_000_000_000))
    downloads = []
    subtitle_calls = []
    asr_calls = []

    def fake_download(record, **kwargs):
        downloads.append(record["video_id"])
        return {**record, "verified": True, "video_downloaded": True, "status": "VERIFIED", "canonical_video_path": f"{record['video_id']}.mp4"}

    def fake_subtitles(record, *, transcript_dir):
        subtitle_calls.append(record["video_id"])
        return {**record, "transcript_status": "ASR_NEEDED", "transcript_downloaded": False}

    def fake_asr(record, *, video_path, transcript_dir, ffmpeg, model_path, min_free_bytes):
        asr_calls.append(record["video_id"])
        return {**record, "transcript_status": "READY", "transcript_type": "ASR", "transcript_downloaded": True}

    monkeypatch.setattr(module, "download_one", fake_download)
    monkeypatch.setattr(module, "collect_subtitles", fake_subtitles)
    monkeypatch.setattr(module, "transcribe_local_asr", fake_asr)

    result = module.run_batch(
        manifest_path,
        batch_path,
        data_dir,
        report_path,
        ffprobe=Path("ffprobe"),
        ffmpeg="ffmpeg",
        model_path=Path("model"),
        min_free_bytes=1,
        safety_reserve_percent=0.1,
        margin=1.5,
    )

    assert result["processed_ids"] == ["video02", "video01"]
    assert downloads == ["video02", "video01"]
    assert subtitle_calls == ["video02", "video01"]
    assert asr_calls == ["video02", "video01"]
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))["videos"]
    assert saved["video01"]["transcript_type"] == "ASR"
    assert saved["outside"]["verified"] is False


def test_run_does_not_retry_direct_download_or_asr_terminal_failures(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    records = {
        "video01": _record("video01", status="DOWNLOAD_FAILED", error="previous failure"),
        "video02": _record("video02", verified=True, video_downloaded=True, status="VERIFIED", canonical_video_path="video02.mp4", transcript_status="ASR_FAILED"),
    }
    data_dir, manifest_path, batch_path, report_path = _setup(tmp_path, records, ["video01", "video02"])
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: SimpleNamespace(free=10_000_000_000))
    calls = []
    monkeypatch.setattr(module, "download_one", lambda *args, **kwargs: calls.append("download"))
    monkeypatch.setattr(module, "collect_subtitles", lambda *args, **kwargs: calls.append("subtitles"))
    monkeypatch.setattr(module, "transcribe_local_asr", lambda *args, **kwargs: calls.append("asr"))

    result = module.run_batch(
        manifest_path,
        batch_path,
        data_dir,
        report_path,
        ffprobe=Path("ffprobe"),
        ffmpeg="ffmpeg",
        model_path=Path("model"),
        min_free_bytes=1,
        safety_reserve_percent=0.1,
        margin=1.5,
    )

    assert calls == []
    assert result["skipped_terminal_ids"] == ["video01", "video02"]


def test_explicit_retry_download_failures_retries_only_the_selected_failed_media(tmp_path: Path, monkeypatch) -> None:
    """A user-authorized retry must re-attempt DOWNLOAD_FAILED, but not ASR failures."""
    module = _load_module()
    records = {
        "video01": _record("video01", status="DOWNLOAD_FAILED", error="old 403", retryable=True),
        "video02": _record(
            "video02",
            verified=True,
            video_downloaded=True,
            status="VERIFIED",
            canonical_video_path="video02.mp4",
            transcript_status="ASR_FAILED",
        ),
    }
    data_dir, manifest_path, batch_path, report_path = _setup(tmp_path, records, ["video01", "video02"])
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: SimpleNamespace(free=10_000_000_000))
    downloads = []

    def fake_download(record, **kwargs):
        downloads.append(record["video_id"])
        return {
            **record,
            "verified": True,
            "video_downloaded": True,
            "status": "VERIFIED",
            "canonical_video_path": "video01.mp4",
        }

    monkeypatch.setattr(module, "download_one", fake_download)
    monkeypatch.setattr(
        module,
        "collect_subtitles",
        lambda record, *, transcript_dir: {**record, "transcript_downloaded": True, "transcript_status": "READY"},
    )

    plan = module.build_plan(
        manifest_path,
        batch_path,
        data_dir,
        min_free_bytes=1,
        safety_reserve_percent=0.1,
        margin=1.5,
        retry_download_failures=True,
    )
    result = module.run_batch(
        manifest_path,
        batch_path,
        data_dir,
        report_path,
        ffprobe=Path("ffprobe"),
        ffmpeg="ffmpeg",
        model_path=Path("model"),
        min_free_bytes=1,
        safety_reserve_percent=0.1,
        margin=1.5,
        retry_download_failures=True,
    )

    assert plan["video_download_pending_ids"] == ["video01"]
    assert downloads == ["video01"]
    assert result["processed_ids"] == ["video01"]
    assert result["skipped_terminal_ids"] == ["video02"]
