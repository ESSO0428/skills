import unittest

from channel_distill.planning import (
    build_download_plan,
    estimate_bytes,
    topic_is_safe,
)


GIB = 1024**3


class EstimateBytesTests(unittest.TestCase):
    def test_duration_uses_observed_rate_when_available(self):
        self.assertEqual(
            estimate_bytes({"duration": 100}, observed_bytes_per_second=1_000_000),
            100_000_000,
        )

    def test_actual_downloaded_size_is_not_an_estimate(self):
        self.assertEqual(estimate_bytes({"duration": 100, "actual_size": 50_000_000}), 50_000_000)

    def test_unknown_duration_gets_conservative_budget(self):
        self.assertGreaterEqual(estimate_bytes({"duration": None}), GIB)


class TopicSafetyTests(unittest.TestCase):
    def test_exact_reserve_boundary_is_unsafe(self):
        self.assertFalse(topic_is_safe(5 * GIB, 2 * GIB, 2 * GIB, 1.5))

    def test_headroom_allows_topic(self):
        self.assertTrue(topic_is_safe(6 * GIB, 2 * GIB, 2 * GIB, 1.5))

    def test_invalid_safety_margin_is_rejected(self):
        with self.assertRaises(ValueError):
            topic_is_safe(6 * GIB, 2 * GIB, 2 * GIB, 0.9)


class PlanTests(unittest.TestCase):
    def test_overlapping_topics_share_one_global_canonical_video(self):
        records = {
            "abc123": {
                "video_id": "abc123",
                "duration": 100,
                "topics": ["optimization", "generalization"],
                "topic_priority": "P0",
                "verified": False,
            },
            "xyz456": {
                "video_id": "xyz456",
                "duration": 100,
                "topics": ["optimization"],
                "topic_priority": "P0",
                "verified": True,
                "actual_size": 20_000_000,
            },
        }
        plan = build_download_plan(
            records,
            free_bytes=10 * GIB,
            min_free_bytes=2 * GIB,
            safety_reserve_percent=0.25,
            margin=1.5,
            observed_bytes_per_second=1_000_000,
        )
        self.assertEqual(plan["unique_remaining_count"], 1)
        self.assertEqual(plan["unique_remaining_estimate_bytes"], 100_000_000)
        self.assertEqual(plan["topics"]["optimization"]["remaining_ids"], ["abc123"])
        self.assertEqual(plan["topics"]["generalization"]["remaining_ids"], ["abc123"])
        self.assertEqual(plan["safety_reserve_bytes"], int(2.5 * GIB))

    def test_insufficient_space_marks_topic_unsafe(self):
        records = {
            "abc123": {
                "video_id": "abc123",
                "duration": None,
                "topics": ["optimization"],
                "topic_priority": "P0",
                "verified": False,
            }
        }
        plan = build_download_plan(
            records,
            free_bytes=3 * GIB,
            min_free_bytes=2 * GIB,
            safety_reserve_percent=0.25,
            margin=1.5,
        )
        self.assertFalse(plan["topics"]["optimization"]["safe_to_start"])


if __name__ == "__main__":
    unittest.main()
