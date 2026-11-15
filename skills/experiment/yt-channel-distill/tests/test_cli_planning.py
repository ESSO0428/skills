import json
from collections import namedtuple
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from channel_distill.cli import main
from channel_distill.manifest import save_manifest


GIB = 1024**3
DiskUsage = namedtuple("DiskUsage", "total used free")


class PlanDownloadCommandTests(unittest.TestCase):
    def test_generates_topic_plan_without_downloading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            save_manifest(
                root / "manifest" / "videos.json",
                {
                    "abc123": {
                        "video_id": "abc123",
                        "title": "Validation",
                        "duration": 100,
                        "topics": [{"topic": "evaluation", "priority": "P0"}],
                        "verified": False,
                    }
                },
            )
            output = root / "DOWNLOAD_PLAN.md"
            with patch("channel_distill.cli.shutil.disk_usage") as usage:
                usage.return_value = DiskUsage(100 * GIB, 90 * GIB, 10 * GIB)
                result = main(
                    [
                        "plan-download",
                        "--workspace",
                        str(root.parent),
                        "--output",
                        str(output),
                        "--min-free-space-gb",
                        "2",
                        "--safety-reserve-percent",
                        "0.25",
                    ]
                )
            self.assertEqual(result, 0)
            self.assertIn("evaluation", output.read_text(encoding="utf-8"))
            topics = json.loads((root / "manifest" / "topics.json").read_text(encoding="utf-8"))
            self.assertEqual(topics["free_bytes"], 10 * GIB)
            self.assertEqual(topics["safety_reserve_bytes"], int(2.5 * GIB))
            self.assertEqual(topics["topics"]["evaluation"]["remaining_ids"], ["abc123"])
            self.assertFalse((root / "videos").exists())

    def test_inadequate_disk_space_is_visible_in_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            save_manifest(
                root / "manifest" / "videos.json",
                {
                    "abc123": {
                        "video_id": "abc123",
                        "title": "Validation",
                        "duration": None,
                        "topics": [{"topic": "evaluation", "priority": "P0"}],
                        "verified": False,
                    }
                },
            )
            output = root / "DOWNLOAD_PLAN.md"
            with patch("channel_distill.cli.shutil.disk_usage") as usage:
                usage.return_value = DiskUsage(100 * GIB, 98 * GIB, 2 * GIB)
                result = main(["plan-download", "--workspace", str(root.parent), "--output", str(output)])
            self.assertEqual(result, 0)
            self.assertIn("UNSAFE", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
