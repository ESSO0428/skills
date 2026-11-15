import unittest

from channel_distill.reading_view import build_reading_view


class ReadingViewTests(unittest.TestCase):
    def test_plain_reading_view_hides_times_but_preserves_reversible_anchors(self):
        document, anchors = build_reading_view(
            "abc123",
            [
                {
                    "chunk_id": "abc123:0-2",
                    "text": "先比較訓練與驗證的行為。",
                    "start_seconds": 0.0,
                    "end_seconds": 12.5,
                    "source_url": "https://www.youtube.com/watch?v=abc123",
                    "transcript_type": "official",
                },
                {
                    "chunk_id": "abc123:3-6",
                    "text": "再決定是否需要改變模型容量。",
                    "start_seconds": 12.5,
                    "end_seconds": 25.0,
                    "source_url": "https://www.youtube.com/watch?v=abc123",
                    "transcript_type": "official",
                },
            ],
        )

        self.assertIn("## S0001", document)
        self.assertIn("先比較訓練與驗證的行為。", document)
        self.assertNotIn("12.5", document)
        self.assertNotIn("start_seconds", document)
        self.assertEqual(
            anchors["anchors"]["S0002"],
            {
                "chunk_id": "abc123:3-6",
                "start_seconds": 12.5,
                "end_seconds": 25.0,
                "source_url": "https://www.youtube.com/watch?v=abc123",
                "transcript_type": "official",
            },
        )

    def test_anchor_input_must_match_requested_video(self):
        with self.assertRaises(ValueError):
            build_reading_view(
                "abc123",
                [{"chunk_id": "different:0-1", "text": "x", "start_seconds": 0.0, "end_seconds": 1.0}],
            )


if __name__ == "__main__":
    unittest.main()
