import unittest

from channel_distill.source_chunks import group_cues, order_cues


def cue(start, end, text, video_id="vid"):
    return {
        "video_id": video_id,
        "title": "Lecture",
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "transcript_type": "official",
        "start_seconds": start,
        "end_seconds": end,
        "text": text,
    }


class SourceChunkTests(unittest.TestCase):
    def test_order_cues_stably_sorts_asr_copy_without_mutating_input(self):
        cues = [cue(2, 3, "second"), cue(1, 1.5, "first"), cue(2, 2.5, "same-start")]
        ordered = order_cues(cues)
        self.assertEqual([item["start_seconds"] for item in ordered], [1, 2, 2])
        self.assertEqual([item["text"] for item in ordered], ["first", "same-start", "second"])
        self.assertEqual([item["start_seconds"] for item in cues], [2, 1, 2])

    def test_preserves_all_cues_and_exact_provenance(self):
        result = group_cues([cue(1, 2, "train loss"), cue(2.2, 3, "is high")])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "train loss is high")
        self.assertEqual(result[0]["start_seconds"], 1)
        self.assertEqual(result[0]["end_seconds"], 3)
        self.assertEqual(result[0]["cue_start_index"], 0)
        self.assertEqual(result[0]["cue_end_index"], 1)
        self.assertEqual(result[0]["source_url"], "https://www.youtube.com/watch?v=vid")

    def test_pause_and_section_marker_create_boundaries(self):
        cues = [cue(1, 2, "one"), cue(2.1, 3, "two"), cue(8, 9, "three"), cue(10, 11, "four")]
        result = group_cues(cues, pause_seconds=3, section_boundaries=[9.5])
        self.assertEqual([x["text"] for x in result], ["one two", "three", "four"])

    def test_duration_cap_splits_without_dropping_text(self):
        cues = [cue(0, 2, "alpha"), cue(20, 21, "beta"), cue(40, 41, "gamma")]
        result = group_cues(cues, pause_seconds=100, max_duration_seconds=30)
        self.assertEqual([x["text"] for x in result], ["alpha beta", "gamma"])

    def test_mixed_sources_are_rejected(self):
        with self.assertRaises(ValueError):
            group_cues([cue(1, 2, "one"), cue(3, 4, "two", video_id="other")])

    def test_overlapping_caption_times_keep_latest_end(self):
        result = group_cues([cue(1, 3, "one"), cue(2.5, 2.9, "two")])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["end_seconds"], 3)

    def test_empty_cues_return_empty_chunks(self):
        self.assertEqual(group_cues([]), [])


if __name__ == "__main__":
    unittest.main()
