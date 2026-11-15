from collections import namedtuple
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from channel_distill.download import download_one
from channel_distill.verify import VerificationResult


GIB = 1024**3
DiskUsage = namedtuple("DiskUsage", "total used free")


class DownloadOneTests(unittest.TestCase):
    def test_verified_existing_file_is_skipped_after_reverification(self):
        with tempfile.TemporaryDirectory() as directory:
            video_dir = Path(directory) / "videos"
            video_dir.mkdir()
            existing = video_dir / "abc123.mp4"
            existing.write_bytes(b"synthetic-video")
            record = {
                "video_id": "abc123",
                "url": "https://www.youtube.com/watch?v=abc123",
                "duration": 10,
                "verified": True,
                "canonical_video_path": str(existing),
            }
            with patch("channel_distill.download.verify_video") as verify:
                verify.return_value = VerificationResult(True, None, 10.0, existing.stat().st_size)
                with patch("channel_distill.download._run_yt_dlp", side_effect=AssertionError("redownloaded")):
                    result = download_one(record, video_dir=video_dir, ffprobe=Path("ffprobe"))
            self.assertTrue(result["verified"])
            self.assertEqual(result["status"], "VERIFIED")

    def test_insufficient_storage_stops_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            video_dir = Path(directory) / "videos"
            record = {
                "video_id": "abc123",
                "url": "https://www.youtube.com/watch?v=abc123",
                "duration": 3600,
                "verified": False,
            }
            with patch("channel_distill.download.shutil.disk_usage") as usage:
                usage.return_value = DiskUsage(100 * GIB, 99 * GIB, 1 * GIB)
                with patch("channel_distill.download._run_yt_dlp", side_effect=AssertionError("downloaded")):
                    result = download_one(
                        record,
                        video_dir=video_dir,
                        ffprobe=Path("ffprobe"),
                        min_free_bytes=2 * GIB,
                    )
            self.assertEqual(result["status"], "INSUFFICIENT_STORAGE")
            self.assertFalse(result["verified"])
            self.assertFalse(video_dir.exists())

    def test_success_needs_verified_canonical_file(self):
        with tempfile.TemporaryDirectory() as directory:
            video_dir = Path(directory) / "videos"
            record = {
                "video_id": "abc123",
                "url": "https://www.youtube.com/watch?v=abc123",
                "duration": 10,
                "verified": False,
            }
            seen_commands = []

            def fake_download(command):
                seen_commands.append(command)
                (video_dir / "abc123.mp4").write_bytes(b"synthetic-video")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("channel_distill.download.shutil.disk_usage") as usage:
                usage.return_value = DiskUsage(100 * GIB, 20 * GIB, 80 * GIB)
                with patch("channel_distill.download._run_yt_dlp", side_effect=fake_download):
                    with patch("channel_distill.download.verify_video") as verify:
                        verify.return_value = VerificationResult(True, None, 10.0, 15)
                        result = download_one(
                            record,
                            video_dir=video_dir,
                            ffprobe=Path("ffprobe"),
                            min_free_bytes=2 * GIB,
                        )
            self.assertEqual(result["status"], "VERIFIED")
            self.assertEqual(result["actual_size"], 15)
            self.assertEqual(result["canonical_video_path"], str(video_dir / "abc123.mp4"))
            self.assertTrue(result["video_downloaded"])
            self.assertTrue(result["verified"])
            self.assertEqual(seen_commands[0][seen_commands[0].index("--js-runtimes") + 1], "node")

    def test_failed_download_keeps_retryable_incomplete_state(self):
        with tempfile.TemporaryDirectory() as directory:
            video_dir = Path(directory) / "videos"
            record = {
                "video_id": "abc123",
                "url": "https://www.youtube.com/watch?v=abc123",
                "duration": 10,
                "verified": False,
            }
            with patch("channel_distill.download.shutil.disk_usage") as usage:
                usage.return_value = DiskUsage(100 * GIB, 20 * GIB, 80 * GIB)
                with patch("channel_distill.download._run_yt_dlp") as run:
                    run.return_value = subprocess.CompletedProcess([], 1, "", "temporary network failure")
                    result = download_one(record, video_dir=video_dir, ffprobe=Path("ffprobe"))
            self.assertEqual(result["status"], "DOWNLOAD_FAILED")
            self.assertTrue(result["retryable"])
            self.assertFalse(result["verified"])
            self.assertFalse(result["video_downloaded"])


if __name__ == "__main__":
    unittest.main()
