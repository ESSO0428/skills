"""Local ASR fallback never masquerades as a public transcript."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from channel_distill.asr import transcribe_local_asr, transcribe_local_audio_asr


def _record(video_path: Path) -> dict:
    return {
        "video_id": "abc123",
        "title": "Training guidance",
        "url": "https://www.youtube.com/watch?v=abc123",
        "duration": 20.0,
        "canonical_video_path": str(video_path),
        "video_downloaded": True,
        "verified": True,
        "transcript_downloaded": False,
        "transcript_type": "missing",
        "transcript_status": "ASR_NEEDED",
    }


class LocalAsrTests(unittest.TestCase):
    def test_model_limits_cpu_parallelism_for_memory_constrained_host(self) -> None:
        captured = {}

        class FakeWhisperModel:
            def __init__(self, *args, **kwargs):
                captured["args"] = args
                captured["kwargs"] = kwargs

        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=FakeWhisperModel)}):
            from channel_distill.asr import _make_model

            _make_model(Path("model"))

        self.assertEqual(captured["kwargs"]["cpu_threads"], 1)
        self.assertEqual(captured["kwargs"]["num_workers"], 1)

    def test_verified_local_video_produces_timestamped_asr_and_word_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"fake video - external ffmpeg is isolated")
            model_path = root / "model"
            model_path.mkdir()
            original = _record(video)
            original["duration"] = 10.0
            word = SimpleNamespace(start=1.25, end=1.75, word="模型")
            segment = SimpleNamespace(start=1.0, end=2.0, text=" 模型容量", words=[word])
            model = SimpleNamespace(transcribe=lambda *_args, **_kwargs: (iter([segment]), SimpleNamespace(language="zh")))

            def fake_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
                self.assertIn(str(video), command)
                self.assertEqual(command[command.index("-ar") + 1], "16000")
                self.assertEqual(command[command.index("-ac") + 1], "1")
                self.assertEqual(command[command.index("-t") + 1], "40.0")
                Path(command[-1]).write_bytes(b"wav")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.asr._run_ffmpeg", side_effect=fake_ffmpeg), patch(
                "channel_distill.asr._make_model", return_value=model
            ) as make_model:
                updated = transcribe_local_asr(
                    original,
                    video_path=video,
                    transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg",
                    model_path=model_path,
                    min_free_bytes=0,
                )

            self.assertEqual(original["transcript_type"], "missing")
            self.assertTrue(updated["transcript_downloaded"])
            self.assertEqual(updated["transcript_type"], "ASR")
            self.assertEqual(updated["transcript_status"], "READY")
            self.assertTrue(Path(updated["transcript_path"]).is_file())
            self.assertTrue(Path(updated["transcript_chunks_path"]).is_file())
            raw = json.loads(Path(updated["transcript_path"]).read_text(encoding="utf-8"))
            self.assertEqual(
                raw["segments"],
                [{
                    "start_seconds": 1.0,
                    "end_seconds": 2.0,
                    "text": "模型容量",
                    "words": [{"start_seconds": 1.25, "end_seconds": 1.75, "text": "模型"}],
                }],
            )
            payload = json.loads(Path(updated["transcript_chunks_path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["transcript_type"], "ASR")
            self.assertEqual(payload["language"], "zh")
            self.assertEqual(
                payload["chunks"],
                [{
                    "start_seconds": 1.0,
                    "end_seconds": 2.0,
                    "text": "模型容量",
                    "video_id": "abc123",
                    "title": "Training guidance",
                    "source_url": "https://www.youtube.com/watch?v=abc123",
                    "transcript_type": "ASR",
                    "words": [{"start_seconds": 1.25, "end_seconds": 1.75, "text": "模型"}],
                }],
            )
            self.assertFalse(list((root / "transcripts").glob("*.wav")))

    def test_long_video_is_transcribed_in_windows_with_absolute_timestamps(self) -> None:
        """Regression: one full lecture must not require one full-audio allocation."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"fake video - external ffmpeg is isolated")
            model_path = root / "model"
            model_path.mkdir()
            original = _record(video)
            original["duration"] = 10.0
            record = _record(video)
            record["duration"] = 1_300.0

            def fake_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(b"wav")
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_worker(command: list[str]) -> subprocess.CompletedProcess[str]:
                jobs = json.loads(Path(command[command.index("--jobs") + 1]).read_text(encoding="utf-8"))
                output = Path(command[command.index("--output") + 1])
                chunks = []
                for job in jobs["jobs"]:
                    offset = float(job["offset_seconds"])
                    chunks.append({
                        "start_seconds": offset + 1.0,
                        "end_seconds": offset + 2.0,
                        "text": "片段",
                        "video_id": "abc123",
                        "title": "Training guidance",
                        "source_url": "https://www.youtube.com/watch?v=abc123",
                        "transcript_type": "ASR",
                        "words": [{"start_seconds": offset + 1.25, "end_seconds": offset + 1.75, "text": "片段"}],
                    })
                output.write_text(json.dumps({
                    "status": "READY", "video_id": "abc123",
                    "offsets": [job["offset_seconds"] for job in jobs["jobs"]],
                    "language": "zh", "zero_duration_words": 0, "chunks": chunks,
                }), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.asr._run_ffmpeg", side_effect=fake_ffmpeg), patch(
                "channel_distill.asr._run_asr_worker", side_effect=fake_worker
            ) as run_worker:
                updated = transcribe_local_asr(
                    record,
                    video_path=video,
                    transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg",
                    model_path=model_path,
                    min_free_bytes=0,
                )

            payload = json.loads(Path(updated["transcript_chunks_path"]).read_text(encoding="utf-8"))
            self.assertEqual(
                [(chunk["start_seconds"], chunk["end_seconds"]) for chunk in payload["chunks"]],
                [(float(offset + 1), float(offset + 2)) for offset in range(0, 1_300, 15)],
            )
            self.assertEqual(payload["chunks"][-1]["words"][0]["start_seconds"], 1291.25)
            self.assertEqual(run_worker.call_count, 5)
            for call in run_worker.call_args_list:
                self.assertEqual(call.args[0][1:3], ["-m", "channel_distill.asr_worker"])

    def test_memory_failed_batch_is_retried_as_validated_small_subbatches(self) -> None:
        """A oneMKL allocation failure must not discard earlier long-video work."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"fake video - external ffmpeg is isolated")
            model_path = root / "model"
            model_path.mkdir()
            record = _record(video)
            record["duration"] = 1_300.0
            failed_once = False

            def fake_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(b"wav")
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_worker(command: list[str]) -> subprocess.CompletedProcess[str]:
                nonlocal failed_once
                jobs = json.loads(Path(command[command.index("--jobs") + 1]).read_text(encoding="utf-8"))
                output = Path(command[command.index("--output") + 1])
                offsets = [float(job["offset_seconds"]) for job in jobs["jobs"]]
                if not failed_once and len(offsets) == 20 and offsets[0] == 300.0:
                    failed_once = True
                    output.write_text(
                        json.dumps({"status": "ASR_FAILED", "error": "mkl_malloc: failed to allocate memory"}),
                        encoding="utf-8",
                    )
                    return subprocess.CompletedProcess(command, 2, "", "")
                chunks = [
                    {
                        "start_seconds": offset + 1.0,
                        "end_seconds": offset + 2.0,
                        "text": "片段",
                        "video_id": "abc123",
                        "title": "Training guidance",
                        "source_url": "https://www.youtube.com/watch?v=abc123",
                        "transcript_type": "ASR",
                        "words": [{"start_seconds": offset + 1.25, "end_seconds": offset + 1.75, "text": "片段"}],
                    }
                    for offset in offsets
                ]
                output.write_text(
                    json.dumps({
                        "status": "READY", "video_id": "abc123", "offsets": offsets,
                        "language": "zh", "zero_duration_words": 0, "chunks": chunks,
                    }),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.asr._run_ffmpeg", side_effect=fake_ffmpeg), patch(
                "channel_distill.asr._run_asr_worker", side_effect=fake_worker
            ) as run_worker:
                updated = transcribe_local_asr(
                    record,
                    video_path=video,
                    transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg",
                    model_path=model_path,
                    min_free_bytes=0,
                )

            self.assertEqual(updated["transcript_status"], "READY")
            payload = json.loads(Path(updated["transcript_chunks_path"]).read_text(encoding="utf-8"))
            self.assertEqual(len(payload["chunks"]), 87)
            self.assertEqual(payload["chunks"][20]["start_seconds"], 301.0)
            self.assertEqual(run_worker.call_count, 25)

    def test_exhausted_segment_retries_are_skipped_and_recorded(self) -> None:
        """A repeatedly failing offset must not discard the rest of a lecture."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"fake video - external ffmpeg is isolated")
            model_path = root / "model"
            model_path.mkdir()
            record = _record(video)
            record["duration"] = 1_300.0

            def fake_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(b"wav")
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_worker(command: list[str]) -> subprocess.CompletedProcess[str]:
                jobs = json.loads(Path(command[command.index("--jobs") + 1]).read_text(encoding="utf-8"))
                output = Path(command[command.index("--output") + 1])
                offsets = [float(job["offset_seconds"]) for job in jobs["jobs"]]
                if len(offsets) == 20 and offsets[0] == 300.0:
                    output.write_text(
                        json.dumps({"status": "ASR_FAILED", "error": "mkl_malloc: failed to allocate memory"}),
                        encoding="utf-8",
                    )
                    return subprocess.CompletedProcess(command, 2, "", "")
                if len(offsets) == 1 and offsets[0] == 315.0:
                    output.write_text(
                        json.dumps({"status": "ASR_FAILED", "error": "mkl_malloc: failed to allocate memory"}),
                        encoding="utf-8",
                    )
                    return subprocess.CompletedProcess(command, 2, "", "")
                chunks = [
                    {
                        "start_seconds": offset + 1.0,
                        "end_seconds": offset + 2.0,
                        "text": "片段",
                        "video_id": "abc123",
                        "title": "Training guidance",
                        "source_url": "https://www.youtube.com/watch?v=abc123",
                        "transcript_type": "ASR",
                        "words": [{"start_seconds": offset + 1.25, "end_seconds": offset + 1.75, "text": "片段"}],
                    }
                    for offset in offsets
                ]
                output.write_text(
                    json.dumps({
                        "status": "READY", "video_id": "abc123", "offsets": offsets,
                        "language": "zh", "zero_duration_words": 0, "chunks": chunks,
                    }),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.asr._run_ffmpeg", side_effect=fake_ffmpeg), patch(
                "channel_distill.asr._run_asr_worker", side_effect=fake_worker
            ):
                updated = transcribe_local_asr(
                    record,
                    video_path=video,
                    transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg",
                    model_path=model_path,
                    min_free_bytes=0,
                )

            self.assertEqual(updated["transcript_status"], "READY_PARTIAL")
            self.assertTrue(updated["transcript_downloaded"])
            self.assertEqual(updated["transcript_unavailable_segments"][0]["offset_seconds"], 315)
            payload = json.loads(Path(updated["transcript_chunks_path"]).read_text(encoding="utf-8"))
            self.assertEqual(len(payload["chunks"]), 86)
            self.assertEqual(payload["unavailable_segments"][0]["offset_seconds"], 315)

    def test_existing_public_subtitle_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            record = _record(video)
            record.update(transcript_downloaded=True, transcript_type="official", transcript_path="kept.vtt")
            with patch("channel_distill.asr._run_ffmpeg") as ffmpeg_run:
                updated = transcribe_local_asr(
                    record, video_path=video, transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg", model_path=root / "missing-model",
                )
            self.assertEqual(updated, record)
            ffmpeg_run.assert_not_called()

    def test_unverified_video_cannot_produce_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            record = _record(video)
            record["verified"] = False
            with patch("channel_distill.asr._run_ffmpeg") as ffmpeg_run:
                updated = transcribe_local_asr(
                    record, video_path=video, transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg", model_path=root / "missing-model",
                )
            self.assertEqual(updated["transcript_status"], "ASR_VIDEO_UNVERIFIED")
            self.assertFalse(updated["transcript_downloaded"])
            ffmpeg_run.assert_not_called()

    def test_audio_only_source_can_produce_asr_without_promoting_video_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "abc123.webm"
            audio.write_bytes(b"audio-only source")
            model_path = root / "model"
            model_path.mkdir()
            record = _record(audio)
            record.update(verified=False, canonical_video_path=None, video_downloaded=False)
            segment = SimpleNamespace(start=1.0, end=2.0, text=" 音訊", words=[])
            model = SimpleNamespace(
                transcribe=lambda *_args, **_kwargs: (iter([segment]), SimpleNamespace(language="zh"))
            )

            def fake_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
                self.assertIn(str(audio), command)
                Path(command[-1]).write_bytes(b"wav")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.asr._run_ffmpeg", side_effect=fake_ffmpeg), patch(
                "channel_distill.asr._make_model", return_value=model
            ):
                updated = transcribe_local_audio_asr(
                    record,
                    audio_path=audio,
                    transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg",
                    model_path=model_path,
                    min_free_bytes=0,
                )

            self.assertEqual(updated["transcript_status"], "READY")
            self.assertTrue(updated["transcript_downloaded"])
            self.assertFalse(updated["verified"])
            self.assertIsNone(updated["canonical_video_path"])

    def test_missing_local_model_is_actionable_and_does_not_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            with patch("channel_distill.asr._run_ffmpeg") as ffmpeg_run:
                updated = transcribe_local_asr(
                    _record(video), video_path=video, transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg", model_path=root / "missing-model",
                )
            self.assertEqual(updated["transcript_status"], "ASR_MODEL_MISSING")
            self.assertTrue(updated["transcript_retryable"])
            self.assertFalse(updated["transcript_downloaded"])
            ffmpeg_run.assert_not_called()

    def test_insufficient_temporary_audio_space_stops_before_ffmpeg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            model_path = root / "model"
            model_path.mkdir()
            with patch("channel_distill.asr.shutil.disk_usage", return_value=SimpleNamespace(free=1)), patch(
                "channel_distill.asr._run_ffmpeg"
            ) as ffmpeg_run:
                updated = transcribe_local_asr(
                    _record(video), video_path=video, transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg", model_path=model_path, min_free_bytes=0,
                )
            self.assertEqual(updated["transcript_status"], "ASR_INSUFFICIENT_STORAGE")
            self.assertFalse(updated["transcript_downloaded"])
            ffmpeg_run.assert_not_called()

    def test_ffmpeg_failure_does_not_claim_asr_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            model_path = root / "model"
            model_path.mkdir()
            failed = subprocess.CompletedProcess(["ffmpeg"], 1, "", "no audio stream")
            with patch("channel_distill.asr._run_ffmpeg", return_value=failed):
                updated = transcribe_local_asr(
                    _record(video), video_path=video, transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg", model_path=model_path, min_free_bytes=0,
                )
            self.assertEqual(updated["transcript_status"], "ASR_AUDIO_FAILED")
            self.assertFalse(updated["transcript_downloaded"])
            self.assertFalse(list((root / "transcripts").glob("*.json")))

    def test_missing_backend_is_reported_without_fake_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            model_path = root / "model"
            model_path.mkdir()

            def fake_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(b"wav")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.asr._run_ffmpeg", side_effect=fake_ffmpeg), patch(
                "channel_distill.asr._make_model", side_effect=ImportError("faster-whisper is not installed")
            ):
                updated = transcribe_local_asr(
                    _record(video), video_path=video, transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg", model_path=model_path, min_free_bytes=0,
                )
            self.assertEqual(updated["transcript_status"], "ASR_BACKEND_MISSING")
            self.assertTrue(updated["transcript_retryable"])
            self.assertFalse(updated["transcript_downloaded"])

    def test_invalid_model_timing_is_rejected_without_writing_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            model_path = root / "model"
            model_path.mkdir()
            segment = SimpleNamespace(start=3.0, end=2.0, text="impossible", words=[])
            model = SimpleNamespace(transcribe=lambda *_args, **_kwargs: (iter([segment]), SimpleNamespace(language="en")))

            def fake_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(b"wav")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.asr._run_ffmpeg", side_effect=fake_ffmpeg), patch(
                "channel_distill.asr._make_model", return_value=model
            ):
                updated = transcribe_local_asr(
                    _record(video), video_path=video, transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg", model_path=model_path, min_free_bytes=0,
                )
            self.assertEqual(updated["transcript_status"], "ASR_INVALID_OUTPUT")
            self.assertFalse(updated["transcript_downloaded"])
            self.assertFalse(list((root / "transcripts").glob("*.json")))

    def test_unwritable_transcript_directory_becomes_explicit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            model_path = root / "model"
            model_path.mkdir()
            blocked_parent = root / "blocked"
            blocked_parent.write_bytes(b"not a directory")
            updated = transcribe_local_asr(
                _record(video), video_path=video, transcript_dir=blocked_parent / "transcripts",
                ffmpeg="ffmpeg", model_path=model_path, min_free_bytes=0,
            )
            self.assertEqual(updated["transcript_status"], "ASR_WRITE_FAILED")
            self.assertFalse(updated["transcript_downloaded"])

    def test_zero_duration_word_is_preserved_but_marked_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "abc123.mp4"
            video.write_bytes(b"video")
            model_path = root / "model"
            model_path.mkdir()
            original = _record(video)
            original["duration"] = 10.0
            word = SimpleNamespace(start=1.4, end=1.4, word=" 字")
            segment = SimpleNamespace(start=1.0, end=2.0, text=" 字", words=[word])
            model = SimpleNamespace(transcribe=lambda *_args, **_kwargs: (iter([segment]), SimpleNamespace(language="zh")))

            def fake_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(b"wav")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.asr._run_ffmpeg", side_effect=fake_ffmpeg), patch(
                "channel_distill.asr._make_model", return_value=model
            ):
                updated = transcribe_local_asr(
                    original, video_path=video, transcript_dir=root / "transcripts",
                    ffmpeg="ffmpeg", model_path=model_path, min_free_bytes=0,
                )
            self.assertEqual(updated["transcript_status"], "READY")
            self.assertEqual(updated["transcript_quality_status"], "REVIEW_REQUIRED")
            payload = json.loads(Path(updated["transcript_chunks_path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["timing_warnings"]["zero_duration_words"], 1)
            self.assertEqual(
                payload["chunks"][0]["words"],
                [{"start_seconds": 1.4, "end_seconds": 1.4, "text": "字", "timing_quality": "zero_duration"}],
            )


if __name__ == "__main__":
    unittest.main()
