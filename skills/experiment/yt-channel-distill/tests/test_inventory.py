import unittest
from unittest.mock import patch
import json
from types import SimpleNamespace

from channel_distill.inventory import (
    fetch_channel_inventory,
    fetch_video_details,
    hydrate_priority_metadata,
    merge_inventory,
    parse_flat_entries,
    parse_upstream_snapshot,
)


class ParseFlatEntriesTests(unittest.TestCase):
    def test_channel_entries_are_keyed_by_video_id_without_invented_playlists(self):
        payload = {
            "id": "UCexamplechannel0000000",
            "title": "Example Channel - Videos",
            "entries": [
                {"id": "WeHM2xpYQpw", "title": "機器學習任務攻略", "url": "https://www.youtube.com/watch?v=WeHM2xpYQpw"},
                {"id": "WeHM2xpYQpw", "title": "機器學習任務攻略", "url": "https://www.youtube.com/watch?v=WeHM2xpYQpw"},
            ],
        }

        videos = parse_flat_entries(payload, origin="channel/videos")

        self.assertEqual(list(videos), ["WeHM2xpYQpw"])
        self.assertEqual(videos["WeHM2xpYQpw"]["url"], "https://www.youtube.com/watch?v=WeHM2xpYQpw")
        self.assertEqual(videos["WeHM2xpYQpw"]["playlist"], [])
        self.assertIsNone(videos["WeHM2xpYQpw"]["series"])

    def test_playlist_entry_records_real_membership_without_guessing_missing_metadata(self):
        payload = {
            "id": "PL-ml-2021",
            "title": "機器學習 2021",
            "webpage_url": "https://www.youtube.com/playlist?list=PL-ml-2021",
            "entries": [{"id": "QW6uINn7uGk", "title": "局部最小值與鞍點"}],
        }

        record = parse_flat_entries(payload, origin="playlist")["QW6uINn7uGk"]

        self.assertEqual(record["playlist"], [{
            "id": "PL-ml-2021",
            "title": "機器學習 2021",
            "url": "https://www.youtube.com/playlist?list=PL-ml-2021",
        }])
        self.assertIsNone(record["series"])
        self.assertIsNone(record["duration"])
        self.assertIsNone(record["upload_date"])

    def test_private_and_short_entries_remain_in_inventory_with_explicit_status(self):
        payload = {"entries": [
            {"id": "private-id1", "title": "[Private video]", "availability": "private"},
            {"id": "short-video", "title": "A short clip", "url": "https://www.youtube.com/shorts/short-video"},
        ]}

        videos = parse_flat_entries(payload, origin="channel/videos")

        self.assertEqual(videos["private-id1"]["status"], "UNAVAILABLE")
        self.assertFalse(videos["private-id1"]["retryable"])
        self.assertEqual(videos["short-video"]["media_type"], "short")
        self.assertEqual(videos["short-video"]["status"], "DISCOVERED")
        self.assertTrue(videos["short-video"]["retryable"])


class MergeInventoryTests(unittest.TestCase):
    def test_same_video_in_two_playlists_keeps_both_and_one_canonical_record(self):
        first = parse_flat_entries({
            "id": "PL-one", "title": "First", "entries": [{"id": "same-video", "title": "Old title"}],
        }, origin="playlist")
        second = parse_flat_entries({
            "id": "PL-two", "title": "Second", "entries": [{"id": "same-video", "title": "New title"}],
        }, origin="playlist")

        merged = merge_inventory(first, second)

        self.assertEqual(list(merged), ["same-video"])
        self.assertEqual([p["id"] for p in merged["same-video"]["playlist"]], ["PL-one", "PL-two"])
        self.assertEqual(merged["same-video"]["title"], "New title")

    def test_refresh_does_not_erase_verified_file_or_replace_known_values_with_null(self):
        existing = {"v1": {
            "video_id": "v1", "title": "Known", "duration": 1920,
            "playlist": [], "verified": True, "video_downloaded": True,
            "canonical_video_path": "data/videos/v1.mp4",
        }}
        incoming = parse_flat_entries({"entries": [{"id": "v1", "title": None}]}, "channel/videos")

        merged = merge_inventory(existing, incoming)

        self.assertEqual(merged["v1"]["title"], "Known")
        self.assertEqual(merged["v1"]["duration"], 1920)
        self.assertTrue(merged["v1"]["verified"])
        self.assertEqual(merged["v1"]["canonical_video_path"], "data/videos/v1.mp4")

    def test_weak_snapshot_does_not_erase_unavailable_status(self):
        unavailable = parse_flat_entries({"entries": [{
            "id": "v1", "title": "[Private video]", "availability": "private",
        }]}, "channel/videos")
        weak_update = parse_flat_entries({"entries": [{"id": "v1", "title": None}]}, "playlist")

        merged = merge_inventory(unavailable, weak_update)

        self.assertEqual(merged["v1"]["status"], "UNAVAILABLE")
        self.assertFalse(merged["v1"]["retryable"])


class ImportMetadataTests(unittest.TestCase):
    def test_upstream_snapshot_does_not_promote_title_guesses_to_playlist_or_series(self):
        payload = {
            "generated_at": "2026-04-08T08:43:38+00:00",
            "channel_url": "https://www.youtube.com/channel/UCexamplechannel0000000/videos",
            "videos": [{
                "video_id": "v1", "title": "類神經網路訓練不起來怎麼辦", "url": "https://www.youtube.com/watch?v=v1",
                "series": "類神經網路訓練不起來怎麼辦", "topics": ["ml-fundamentals"],
            }],
        }

        videos = parse_upstream_snapshot(payload)

        self.assertEqual(list(videos), ["v1"])
        self.assertEqual(videos["v1"]["playlist"], [])
        self.assertIsNone(videos["v1"]["series"])
        self.assertEqual(videos["v1"]["topics"], [])
        self.assertEqual(videos["v1"]["status"], "DISCOVERED")
        self.assertIn("upstream_snapshot", videos["v1"]["inventory_sources"])


class LiveMetadataTests(unittest.TestCase):
    @patch("channel_distill.inventory.subprocess.run")
    def test_channel_scan_fetches_videos_and_real_playlists_without_media_download(self, run):
        payloads = {
            "https://www.youtube.com/channel/UCexamplechannel0000000/videos": {
                "entries": [{"id": "v1", "title": "Lecture"}],
            },
            "https://www.youtube.com/channel/UCexamplechannel0000000/playlists": {
                "entries": [{"id": "PL-one", "title": "Course"}],
            },
            "https://www.youtube.com/playlist?list=PL-one": {
                "id": "PL-one", "title": "Course", "entries": [{"id": "v1", "title": "Lecture"}],
            },
        }

        def fake_run(command, **kwargs):
            self.assertIn("--skip-download", command)
            self.assertIn("--flat-playlist", command)
            self.assertEqual(kwargs["capture_output"], True)
            return SimpleNamespace(returncode=0, stdout=json.dumps(payloads[command[-1]]), stderr="")

        run.side_effect = fake_run
        videos = fetch_channel_inventory("UCexamplechannel0000000")

        self.assertEqual(len(videos), 1)
        self.assertEqual(videos["v1"]["playlist"][0]["id"], "PL-one")
        self.assertIn("https://www.youtube.com/channel/UCexamplechannel0000000/videos", videos["v1"]["inventory_sources"])
        self.assertIn("https://www.youtube.com/playlist?list=PL-one", videos["v1"]["inventory_sources"])
        self.assertEqual(run.call_count, 3)

    @patch("channel_distill.inventory.subprocess.run")
    def test_video_hydration_reads_duration_and_upload_date_without_downloading(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"id": "v1", "duration": 1800, "upload_date": "20210301", "channel_id": "UCexamplechannel0000000"}),
            stderr="",
        )

        details = fetch_video_details("v1")

        self.assertEqual(details["duration"], 1800)
        self.assertEqual(details["upload_date"], "20210301")
        command = run.call_args.args[0]
        self.assertIn("--skip-download", command)
        self.assertIn("--no-playlist", command)
        self.assertNotIn("--flat-playlist", command)

    @patch("channel_distill.inventory.subprocess.run")
    def test_channel_videos_can_be_checkpointed_before_playlist_expansion(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"entries": [{"id": "v1", "title": "Lecture"}]}),
            stderr="",
        )

        videos = fetch_channel_inventory("UCtest", include_playlists=False)

        self.assertEqual(list(videos), ["v1"])
        self.assertEqual(videos["v1"]["playlist"], [])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-1], "https://www.youtube.com/channel/UCtest/videos")

    @patch("channel_distill.inventory.subprocess.run")
    def test_hydration_selects_only_priority_videos_missing_metadata(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"id": "p0", "duration": 600, "upload_date": "20210401"}),
            stderr="",
        )
        videos = {
            "p0": {"video_id": "p0", "topic_priority": "P0", "duration": None, "upload_date": None},
            "p1": {"video_id": "p1", "topic_priority": "P1", "duration": None, "upload_date": None},
            "done": {"video_id": "done", "topic_priority": "P0", "duration": 100, "upload_date": "20210301"},
        }

        hydrated = hydrate_priority_metadata(videos, priority="P0")

        self.assertEqual(hydrated["p0"]["duration"], 600)
        self.assertEqual(hydrated["p0"]["upload_date"], "20210401")
        self.assertIsNone(hydrated["p1"]["duration"])
        self.assertEqual(run.call_count, 1)
        self.assertIsNone(videos["p0"]["duration"])


if __name__ == "__main__":
    unittest.main()
