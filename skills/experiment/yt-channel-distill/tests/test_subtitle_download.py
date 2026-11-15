import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from channel_distill.subtitle_download import collect_subtitles


VTT = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n訓練損失高\n"


class SubtitleCollectionTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "video_id": "abc123",
            "title": "研究方法",
            "url": "https://www.youtube.com/watch?v=abc123",
            "verified": True,
        }

    def test_prefers_official_and_preserves_timed_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            metadata = {
                "id": "abc123",
                "subtitles": {"zh-Hant": [{"ext": "vtt"}]},
                "automatic_captions": {"zh": [{"ext": "vtt"}]},
            }

            def fake_run(command):
                if "-J" in command:
                    return subprocess.CompletedProcess(command, 0, json.dumps(metadata), "")
                self.assertIn("--write-subs", command)
                self.assertNotIn("--write-auto-subs", command)
                (target / "abc123.zh-Hant.vtt").write_text(VTT, encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.subtitle_download._run_yt_dlp", side_effect=fake_run):
                result = collect_subtitles(self.record, transcript_dir=target)
            self.assertTrue(result["transcript_downloaded"])
            self.assertEqual(result["transcript_type"], "official")
            self.assertTrue(result["verified"])
            self.assertTrue(Path(result["transcript_path"]).exists())
            chunks = json.loads(Path(result["transcript_chunks_path"]).read_text(encoding="utf-8"))
            self.assertEqual(chunks["language"], "zh-Hant")
            self.assertEqual(chunks["chunks"][0]["start_seconds"], 0.0)
            self.assertEqual(chunks["chunks"][0]["video_id"], "abc123")
            self.assertEqual(chunks["chunks"][0]["transcript_type"], "official")

    def test_uses_auto_only_when_official_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            metadata = {
                "id": "abc123",
                "subtitles": {},
                "automatic_captions": {"zh": [{"ext": "vtt"}]},
            }

            def fake_run(command):
                if "-J" in command:
                    return subprocess.CompletedProcess(command, 0, json.dumps(metadata), "")
                self.assertIn("--write-auto-subs", command)
                (target / "abc123.zh.vtt").write_text(VTT, encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.subtitle_download._run_yt_dlp", side_effect=fake_run):
                result = collect_subtitles(self.record, transcript_dir=target)
            self.assertEqual(result["transcript_type"], "auto")
            self.assertTrue(result["transcript_downloaded"])

    def test_missing_subtitles_are_not_mislabeled_as_official(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = {"id": "abc123", "subtitles": {}, "automatic_captions": {}}
            with patch("channel_distill.subtitle_download._run_yt_dlp") as run:
                run.return_value = subprocess.CompletedProcess([], 0, json.dumps(metadata), "")
                result = collect_subtitles(self.record, transcript_dir=Path(directory))
            self.assertFalse(result["transcript_downloaded"])
            self.assertEqual(result["transcript_type"], "missing")
            self.assertEqual(result["transcript_status"], "ASR_NEEDED")
            self.assertFalse(Path(directory, "abc123.chunks.json").exists())

    def test_metadata_failure_is_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("channel_distill.subtitle_download._run_yt_dlp") as run:
                run.return_value = subprocess.CompletedProcess([], 1, "", "temporary network error")
                result = collect_subtitles(self.record, transcript_dir=Path(directory))
            self.assertEqual(result["transcript_status"], "FETCH_FAILED")
            self.assertTrue(result["transcript_retryable"])
            self.assertFalse(result["transcript_downloaded"])


if __name__ == "__main__":
    unittest.main()
