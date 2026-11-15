import json
from collections import namedtuple
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from channel_distill.cli import main
from channel_distill.manifest import load_manifest, save_manifest


GIB = 1024**3
DiskUsage = namedtuple("DiskUsage", "total used free")


class TopicDownloadCommandTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("channel_distill.cli.find_binary", side_effect=lambda name, flag=None, env="": Path(name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fixture(self, root, count=2):
        records = {
            f"id{index}": {
                "video_id": f"id{index}",
                "title": f"Video {index}",
                "url": f"https://www.youtube.com/watch?v=id{index}",
                "duration": 60,
                "topics": [{"topic": "evaluation", "priority": "P0"}],
                "verified": False,
            }
            for index in range(count)
        }
        save_manifest(root / "manifest" / "videos.json", records)

    def test_unsafe_topic_aborts_without_calling_downloader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            self._fixture(root)
            with patch("channel_distill.cli.shutil.disk_usage") as disk:
                disk.return_value = DiskUsage(100 * GIB, 99 * GIB, 1 * GIB)
                with patch("channel_distill.cli.download_one", side_effect=AssertionError("download attempted")):
                    result = main(["download", "--workspace", str(root.parent), "--topic", "evaluation"])
            self.assertEqual(result, 1)
            self.assertFalse((root / "videos").exists())

    def test_checkpoint_per_video_and_resume_later(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            self._fixture(root)
            calls = []

            def fake_download(record, **kwargs):
                calls.append(record["video_id"])
                return {**record, "video_downloaded": True, "verified": True, "status": "VERIFIED"}

            def fake_subtitles(record, **kwargs):
                return {**record, "transcript_downloaded": True, "transcript_status": "READY"}

            with patch("channel_distill.cli.shutil.disk_usage") as disk:
                disk.return_value = DiskUsage(100 * GIB, 20 * GIB, 80 * GIB)
                with patch("channel_distill.cli.download_one", side_effect=fake_download):
                    with patch("channel_distill.cli.collect_subtitles", side_effect=fake_subtitles):
                        first = main([
                            "download", "--workspace", str(root.parent), "--topic", "evaluation",
                            "--max-videos", "1",
                        ])
                        checkpoint = load_manifest(root / "manifest" / "videos.json")
                        second = main(["download", "--workspace", str(root.parent), "--topic", "evaluation"])
            self.assertEqual((first, second), (0, 0))
            self.assertEqual(calls, ["id0", "id1"])
            self.assertTrue(checkpoint["id0"]["verified"])
            self.assertFalse(checkpoint["id1"]["verified"])
            records = load_manifest(root / "manifest" / "videos.json")
            self.assertTrue(all(record["verified"] for record in records.values()))
            status = json.loads((root / "manifest" / "download-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["topics"]["evaluation"]["status"], "VERIFIED")
            gate_log = root / "processing" / "wiki-gate.jsonl"
            self.assertTrue(gate_log.is_file())
            self.assertEqual(len(gate_log.read_text(encoding="utf-8").splitlines()), 2)

    def test_video_id_targets_one_topic_item_without_touching_other_items(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            self._fixture(root)
            calls = []

            def fake_download(record, **kwargs):
                calls.append(record["video_id"])
                return {**record, "video_downloaded": True, "verified": True, "status": "VERIFIED"}

            def fake_subtitles(record, **kwargs):
                return {**record, "transcript_downloaded": True, "transcript_status": "READY"}

            with patch("channel_distill.cli.shutil.disk_usage") as disk:
                disk.return_value = DiskUsage(100 * GIB, 20 * GIB, 80 * GIB)
                with patch("channel_distill.cli.download_one", side_effect=fake_download):
                    with patch("channel_distill.cli.collect_subtitles", side_effect=fake_subtitles):
                        result = main([
                            "download", "--workspace", str(root.parent), "--topic", "evaluation",
                            "--video-id", "id1",
                        ])

            self.assertEqual(result, 0)
            self.assertEqual(calls, ["id1"])
            records = load_manifest(root / "manifest" / "videos.json")
            self.assertFalse(records["id0"]["verified"])
            self.assertTrue(records["id1"]["verified"])

    def test_exact_video_id_bypasses_unsafe_group_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            self._fixture(root)
            records = load_manifest(root / "manifest" / "videos.json")
            records["id0"]["duration"] = 200_000
            records["id1"]["duration"] = 60
            save_manifest(root / "manifest" / "videos.json", records)
            calls = []

            def fake_download(record, **kwargs):
                calls.append(record["video_id"])
                return {**record, "video_downloaded": True, "verified": True, "status": "VERIFIED"}

            def fake_subtitles(record, **kwargs):
                return {**record, "transcript_downloaded": True, "transcript_status": "READY"}

            with patch("channel_distill.cli.shutil.disk_usage") as disk:
                disk.return_value = DiskUsage(100 * GIB, 69 * GIB, 31 * GIB)
                with patch("channel_distill.cli.download_one", side_effect=fake_download):
                    with patch("channel_distill.cli.collect_subtitles", side_effect=fake_subtitles):
                        result = main([
                            "download", "--workspace", str(root.parent), "--topic", "evaluation",
                            "--video-id", "id1",
                        ])

            self.assertEqual(result, 0)
            self.assertEqual(calls, ["id1"])

    def test_failed_video_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            self._fixture(root, count=1)
            with patch("channel_distill.cli.shutil.disk_usage") as disk:
                disk.return_value = DiskUsage(100 * GIB, 20 * GIB, 80 * GIB)
                with patch("channel_distill.cli.download_one") as download:
                    download.side_effect = lambda record, **kwargs: {
                        **record, "verified": False, "status": "DOWNLOAD_FAILED", "retryable": True
                    }
                    result = main(["download", "--workspace", str(root.parent), "--topic", "evaluation"])
            self.assertEqual(result, 1)
            record = load_manifest(root / "manifest" / "videos.json")["id0"]
            self.assertFalse(record["verified"])
            status = json.loads((root / "manifest" / "download-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["topics"]["evaluation"]["status"], "PARTIAL")

    def test_unavailable_video_is_not_retried_or_silently_counted_as_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            self._fixture(root)
            records = load_manifest(root / "manifest" / "videos.json")
            records["id0"].update(verified=True, transcript_downloaded=True, status="VERIFIED")
            records["id1"].update(verified=False, status="UNAVAILABLE", error="removed", retryable=False)
            save_manifest(root / "manifest" / "videos.json", records)
            with patch("channel_distill.cli.shutil.disk_usage") as disk:
                disk.return_value = DiskUsage(100 * GIB, 20 * GIB, 80 * GIB)
                with patch("channel_distill.cli.download_one", side_effect=AssertionError("unavailable retried")):
                    result = main(["download", "--workspace", str(root.parent), "--topic", "evaluation"])
            self.assertEqual(result, 0)
            status = json.loads((root / "manifest" / "download-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["topics"]["evaluation"]["status"], "AVAILABLE_ITEMS_COMPLETE")
            self.assertEqual(status["topics"]["evaluation"]["unavailable_ids"], ["id1"])
            self.assertFalse(status["topics"]["evaluation"]["all_discovered_items_available"])


if __name__ == "__main__":
    unittest.main()
