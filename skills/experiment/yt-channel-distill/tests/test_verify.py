import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from channel_distill.verify import VerificationResult, verify_video


class VerifyVideoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "abc123.mp4"
        self.path.write_bytes(b"sample bytes")
        self.ffprobe = Path(self.temporary.name) / "ffprobe.exe"

    def probe_output(self, *, duration="120.0", streams=None, format_data=None):
        if streams is None:
            streams = [{"codec_type": "video", "codec_name": "h264"}]
        if format_data is None:
            format_data = {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": duration}
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"format": format_data, "streams": streams}), stderr=""
        )

    def test_missing_file_never_verifies(self):
        self.path.unlink()
        with patch("channel_distill.verify.subprocess.run") as run:
            result = verify_video(self.path, "abc123", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "file_missing")
        self.assertEqual(result.size_bytes, 0)
        run.assert_not_called()

    def test_zero_length_file_never_verifies(self):
        self.path.write_bytes(b"")
        result = verify_video(self.path, "abc123", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "empty_file")

    def test_canonical_filename_must_match_video_id(self):
        result = verify_video(self.path, "different", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "filename_mismatch")

    def test_part_file_is_not_a_canonical_video(self):
        part = self.path.with_suffix(".part")
        part.write_bytes(b"partial")
        result = verify_video(part, "abc123", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "filename_mismatch")

    def test_readable_video_within_duration_tolerance_verifies(self):
        with patch("channel_distill.verify.subprocess.run", return_value=self.probe_output(duration="149.0")) as run:
            result = verify_video(self.path, "abc123", 120.0, self.ffprobe)
        self.assertIsInstance(result, VerificationResult)
        self.assertTrue(result.ok)
        self.assertIsNone(result.reason)
        self.assertEqual(result.duration, 149.0)
        self.assertEqual(result.size_bytes, 12)
        command = run.call_args.args[0]
        self.assertEqual(command[0], str(self.ffprobe))
        self.assertEqual(command[-1], str(self.path))

    def test_duration_outside_max_30_seconds_or_five_percent_fails(self):
        with patch("channel_distill.verify.subprocess.run", return_value=self.probe_output(duration="231.0")):
            result = verify_video(self.path, "abc123", 200.0, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "duration_mismatch")
        self.assertEqual(result.duration, 231.0)

    def test_missing_ffprobe_cannot_verify(self):
        with patch("channel_distill.verify.subprocess.run", side_effect=FileNotFoundError("ffprobe")):
            result = verify_video(self.path, "abc123", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "ffprobe_missing")

    def test_failed_ffprobe_cannot_verify(self):
        failure = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="bad container")
        with patch("channel_distill.verify.subprocess.run", return_value=failure):
            result = verify_video(self.path, "abc123", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "ffprobe_failed")

    def test_invalid_probe_json_cannot_verify(self):
        malformed = subprocess.CompletedProcess(args=[], returncode=0, stdout="not-json", stderr="")
        with patch("channel_distill.verify.subprocess.run", return_value=malformed):
            result = verify_video(self.path, "abc123", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "ffprobe_invalid_json")

    def test_container_without_video_stream_cannot_verify(self):
        with patch("channel_distill.verify.subprocess.run", return_value=self.probe_output(streams=[{"codec_type": "audio"}])):
            result = verify_video(self.path, "abc123", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "no_video_stream")

    def test_expected_duration_requires_probe_duration(self):
        with patch("channel_distill.verify.subprocess.run", return_value=self.probe_output(duration=None)):
            result = verify_video(self.path, "abc123", 120.0, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "duration_missing")

    def test_invalid_probe_duration_cannot_verify(self):
        with patch("channel_distill.verify.subprocess.run", return_value=self.probe_output(duration="0")):
            result = verify_video(self.path, "abc123", None, self.ffprobe)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "duration_invalid")


if __name__ == "__main__":
    unittest.main()
