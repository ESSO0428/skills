import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from channel_distill.cli import main

RULES = str(Path(__file__).parents[1] / "examples" / "topic-rules.ml-course.json")
from channel_distill.manifest import save_manifest


class InventoryCliTests(unittest.TestCase):
    @patch("channel_distill.inventory.subprocess.run")
    def test_skip_playlists_checkpoints_classified_video_manifest_and_csv(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"entries": [{"id": "v1", "title": "局部最小值與鞍點"}]}),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temporary:
            code = main(["inventory", "--channel-id", "UCtest", "--workspace", temporary, "--skip-playlists", "--topic-rules", RULES])

            manifest_dir = Path(temporary) / "data" / "manifest"
            saved = json.loads((manifest_dir / "videos.json").read_text(encoding="utf-8"))
            with (manifest_dir / "videos.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(code, 0)
        self.assertEqual(list(saved["videos"]), ["v1"])
        self.assertEqual(saved["videos"]["v1"]["topic_priority"], "P0")
        self.assertEqual(saved["videos"]["v1"]["playlist"], [])
        self.assertEqual(rows[0]["video_id"], "v1")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-1], "https://www.youtube.com/channel/UCtest/videos")

    @patch("channel_distill.inventory.subprocess.run")
    def test_rerun_merges_true_playlist_memberships_without_losing_existing_verification(self, run):
        payloads = {
            "https://www.youtube.com/channel/UCtest/videos": {"entries": [{"id": "v1", "title": "Validation"}]},
            "https://www.youtube.com/channel/UCtest/playlists": {"entries": [{"id": "PL-new", "title": "New course"}]},
            "https://www.youtube.com/playlist?list=PL-new": {"id": "PL-new", "title": "New course", "entries": [{"id": "v1", "title": "Validation"}]},
        }
        run.side_effect = lambda command, **kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps(payloads[command[-1]]), stderr=""
        )
        with tempfile.TemporaryDirectory() as temporary:
            manifest_dir = Path(temporary) / "data" / "manifest"
            save_manifest(manifest_dir / "videos.json", {"v1": {
                "video_id": "v1", "title": "Old title", "playlist": [{"id": "PL-old", "title": "Old course", "url": "https://www.youtube.com/playlist?list=PL-old"}],
                "verified": True, "video_downloaded": True, "status": "VERIFIED", "canonical_video_path": "data/videos/v1.mp4",
            }})

            code = main(["inventory", "--channel-id", "UCtest", "--workspace", temporary, "--topic-rules", RULES])

            record = json.loads((manifest_dir / "videos.json").read_text(encoding="utf-8"))["videos"]["v1"]

        self.assertEqual(code, 0)
        self.assertEqual([p["id"] for p in record["playlist"]], ["PL-old", "PL-new"])
        self.assertTrue(record["verified"])
        self.assertEqual(record["status"], "VERIFIED")
        self.assertEqual(record["canonical_video_path"], "data/videos/v1.mp4")
        self.assertEqual(record["topic_priority"], "P0")
        self.assertEqual(run.call_count, 3)

    @patch("channel_distill.inventory.subprocess.run")
    def test_failed_inventory_leaves_manifest_unmodified(self, run):
        run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="rate limited")
        with tempfile.TemporaryDirectory() as temporary:
            code = main(["inventory", "--channel-id", "UCtest", "--workspace", temporary, "--skip-playlists"])
            manifest_path = Path(temporary) / "data" / "manifest" / "videos.json"

            self.assertEqual(code, 1)
            self.assertFalse(manifest_path.exists())


if __name__ == "__main__":
    unittest.main()
