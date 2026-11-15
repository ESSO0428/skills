from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from channel_distill.cli import main
from channel_distill.manifest import load_manifest, save_manifest


class TranscribeCommandTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("channel_distill.cli.find_binary", side_effect=lambda name, flag=None, env="": Path(name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_module_entrypoint_exposes_cli_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "channel_distill.cli", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("transcribe", result.stdout)

    def test_one_verified_missing_transcript_checkpoints_ready_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            video_path = root / "videos" / "abc123.mp4"
            video_path.parent.mkdir(parents=True)
            video_path.write_bytes(b"sample")
            save_manifest(root / "manifest" / "videos.json", {
                "abc123": {
                    "video_id": "abc123", "url": "https://www.youtube.com/watch?v=abc123",
                    "verified": True, "canonical_video_path": str(video_path),
                    "transcript_downloaded": False, "transcript_status": "ASR_NEEDED",
                }
            })
            model = root / "model"
            model.mkdir()
            with patch("channel_distill.cli.transcribe_local_asr") as transcribe:
                transcribe.side_effect = lambda record, **kwargs: {
                    **record, "transcript_downloaded": True, "transcript_type": "ASR",
                    "transcript_status": "READY", "transcript_chunks_path": "asr.json"
                }
                result = main([
                    "transcribe", "--video-id", "abc123", "--workspace", str(root.parent),
                    "--model-path", str(model),
                ])
            self.assertEqual(result, 0)
            self.assertTrue(load_manifest(root / "manifest" / "videos.json")["abc123"]["transcript_downloaded"])
            self.assertTrue((root / "manifest" / "videos.csv").is_file())
            gate_log = root / "processing" / "wiki-gate.jsonl"
            self.assertTrue(gate_log.is_file())
            self.assertIn('"terminal_state": "READY"', gate_log.read_text(encoding="utf-8"))
            manifest_record = load_manifest(root / "manifest" / "videos.json")["abc123"]
            self.assertEqual(manifest_record["wiki_gate"]["terminal_state"], "READY")
            self.assertEqual(manifest_record["wiki_gate"]["action"], "COMPILE")

    def test_official_subtitles_are_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            save_manifest(root / "manifest" / "videos.json", {
                "abc123": {
                    "video_id": "abc123", "verified": True,
                    "transcript_downloaded": True, "transcript_type": "official",
                }
            })
            with patch("channel_distill.cli.transcribe_local_asr", side_effect=AssertionError("ASR attempted")):
                self.assertEqual(main(["transcribe", "--video-id", "abc123", "--workspace", str(root.parent)]), 0)

    def test_failure_is_persisted_but_not_called_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            save_manifest(root / "manifest" / "videos.json", {
                "abc123": {
                    "video_id": "abc123", "verified": True,
                    "transcript_downloaded": False, "transcript_status": "ASR_NEEDED",
                }
            })
            with patch("channel_distill.cli.transcribe_local_asr") as transcribe:
                transcribe.side_effect = lambda record, **kwargs: {
                    **record, "transcript_downloaded": False, "transcript_status": "ASR_MODEL_MISSING"
                }
                self.assertEqual(main(["transcribe", "--video-id", "abc123", "--workspace", str(root.parent)]), 1)
            record = load_manifest(root / "manifest" / "videos.json")["abc123"]
            self.assertFalse(record["transcript_downloaded"])
            self.assertEqual(record["transcript_status"], "ASR_MODEL_MISSING")

    def test_postprocess_runs_text_pipeline_once_after_asr_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            video_path = root / "videos" / "abc123.mp4"
            video_path.parent.mkdir(parents=True)
            video_path.write_bytes(b"sample")
            save_manifest(root / "manifest" / "videos.json", {
                "abc123": {
                    "video_id": "abc123", "url": "https://www.youtube.com/watch?v=abc123",
                    "verified": True, "canonical_video_path": str(video_path),
                    "transcript_downloaded": False, "transcript_status": "ASR_NEEDED",
                }
            })
            model = root / "model"
            model.mkdir()
            with patch("channel_distill.cli.transcribe_local_asr") as transcribe, patch(
                "channel_distill.cli._prepare_sources", return_value=0
            ) as prepare, patch(
                "channel_distill.cli._build_reading_views", return_value=0
            ) as reading, patch(
                "channel_distill.cli._audit_coverage", return_value=0
            ) as coverage, patch(
                "channel_distill.cli._sync_wiki_after_text", return_value=True
            ) as wiki_sync:
                transcribe.return_value = {
                    "video_id": "abc123", "url": "https://www.youtube.com/watch?v=abc123",
                    "verified": True, "canonical_video_path": str(video_path),
                    "transcript_downloaded": True, "transcript_type": "ASR",
                    "transcript_status": "READY", "transcript_chunks_path": "asr.json",
                }
                result = main([
                    "transcribe", "--video-id", "abc123", "--workspace", str(root.parent),
                    "--model-path", str(model), "--postprocess",
                ])
            self.assertEqual(result, 0)
            prepare.assert_called_once()
            reading.assert_called_once()
            coverage.assert_called_once()
            wiki_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
