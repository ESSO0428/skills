import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from channel_distill.manifest import export_csv, load_manifest, save_manifest


REQUIRED_FIELDS = {
    "video_id",
    "title",
    "url",
    "duration",
    "upload_date",
    "playlist",
    "series",
    "topics",
    "topic_priority",
    "download_priority",
    "estimated_size",
    "actual_size",
    "video_downloaded",
    "transcript_downloaded",
    "verified",
    "transcript_type",
    "canonical_video_path",
    "transcript_path",
    "status",
    "error",
    "retryable",
    "last_attempt",
}


class ManifestTests(unittest.TestCase):
    def test_save_and_load_fills_unknown_fields_without_inventing_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest" / "videos.json"
            playlist = {"id": "PL1", "title": "ML 2021", "url": "https://youtube.com/playlist?list=PL1"}
            topic = {"topic": "optimization", "priority": "P0", "confidence": 0.8, "reason": "title"}
            videos = {
                "alpha": {
                    "video_id": "alpha",
                    "title": "Optimization",
                    "url": "https://www.youtube.com/watch?v=alpha",
                    "playlist": [playlist],
                    "topics": [topic],
                    "verified": False,
                    "source_origin": "channel",
                },
                "beta": {"title": "Generalization", "video_downloaded": False},
            }

            save_manifest(path, videos)
            loaded = load_manifest(path)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(set(loaded), {"alpha", "beta"})
            self.assertEqual(payload["schema_version"], 1)
            self.assertTrue(payload["generated_at"])
            self.assertEqual(payload["videos"], loaded)
            for record in loaded.values():
                self.assertTrue(REQUIRED_FIELDS <= set(record))
            self.assertEqual(loaded["alpha"]["playlist"], [playlist])
            self.assertEqual(loaded["alpha"]["topics"], [topic])
            self.assertEqual(loaded["alpha"]["source_origin"], "channel")
            self.assertIsNone(loaded["alpha"]["duration"])
            self.assertIsNone(loaded["alpha"]["transcript_type"])
            self.assertIsNone(loaded["beta"]["verified"])
            self.assertEqual(loaded["beta"]["playlist"], [])
            self.assertEqual(loaded["beta"]["topics"], [])
            self.assertEqual(loaded["beta"]["video_id"], "beta")

    def test_duplicate_video_id_merges_memberships_without_second_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "videos.json"
            first_playlist = {"id": "PL1", "title": "ML", "url": "https://youtube.com/playlist?list=PL1"}
            second_playlist = {"id": "PL2", "title": "DL", "url": "https://youtube.com/playlist?list=PL2"}
            videos = {
                "channel:alpha": {
                    "video_id": "alpha",
                    "title": "Optimization",
                    "playlist": [first_playlist],
                    "topics": [{"topic": "optimization", "priority": "P0", "confidence": 0.8, "reason": "title"}],
                },
                "playlist:alpha": {
                    "video_id": "alpha",
                    "url": "https://www.youtube.com/watch?v=alpha",
                    "playlist": [first_playlist, second_playlist],
                    "topics": [{"topic": "training", "priority": "P0", "confidence": 0.7, "reason": "playlist"}],
                },
            }

            save_manifest(path, videos)
            loaded = load_manifest(path)

            self.assertEqual(set(loaded), {"alpha"})
            self.assertEqual(loaded["alpha"]["title"], "Optimization")
            self.assertEqual(loaded["alpha"]["url"], "https://www.youtube.com/watch?v=alpha")
            self.assertEqual(loaded["alpha"]["playlist"], [first_playlist, second_playlist])
            self.assertEqual([item["topic"] for item in loaded["alpha"]["topics"]], ["optimization", "training"])

    def test_csv_export_uses_same_normalized_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "videos.csv"
            playlist = [{"id": "PL1", "title": "ML", "url": "https://youtube.com/playlist?list=PL1"}]
            videos = {"alpha": {"title": "Optimization", "playlist": playlist}}

            export_csv(path, videos)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 1)
            self.assertTrue(REQUIRED_FIELDS <= set(rows[0]))
            self.assertEqual(rows[0]["video_id"], "alpha")
            self.assertEqual(json.loads(rows[0]["playlist"]), playlist)
            self.assertEqual(json.loads(rows[0]["topics"]), [])
            self.assertEqual(rows[0]["duration"], "")

    def test_failed_atomic_replace_preserves_previous_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "videos.json"
            save_manifest(path, {"alpha": {"title": "Original"}})
            previous_bytes = path.read_bytes()

            with patch("channel_distill.manifest.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaisesRegex(OSError, "disk failure"):
                    save_manifest(path, {"alpha": {"title": "Replacement"}})

            self.assertEqual(path.read_bytes(), previous_bytes)
            self.assertEqual(load_manifest(path)["alpha"]["title"], "Original")
            self.assertEqual(list(Path(temporary).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
