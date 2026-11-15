import unittest

from channel_distill.transcripts import parse_subtitles


class ParseSubtitlesTests(unittest.TestCase):
    def test_vtt_cue_preserves_timing_and_provenance(self) -> None:
        content = "WEBVTT\n\n00:00:01.250 --> 00:00:03.500\nModel bias matters.\n"

        chunks = parse_subtitles(
            content,
            format="vtt",
            video_id="abc123",
            title="Training guidance",
            source_url="https://www.youtube.com/watch?v=abc123",
            transcript_type="official",
        )

        self.assertEqual(
            chunks,
            [
                {
                    "start_seconds": 1.25,
                    "end_seconds": 3.5,
                    "text": "Model bias matters.",
                    "video_id": "abc123",
                    "title": "Training guidance",
                    "source_url": "https://www.youtube.com/watch?v=abc123",
                    "transcript_type": "official",
                }
            ],
        )

    def test_vtt_rolling_captions_keep_only_new_words_at_their_own_times(self) -> None:
        content = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\nModel\n\n"
            "00:00:01.000 --> 00:00:02.000\nModel capacity\n\n"
            "00:00:02.000 --> 00:00:03.000\ncapacity matters\n"
        )

        chunks = parse_subtitles(
            content,
            format="vtt",
            video_id="abc123",
            title="Training guidance",
            source_url="https://www.youtube.com/watch?v=abc123",
            transcript_type="auto",
        )

        self.assertEqual(
            [(c["start_seconds"], c["end_seconds"], c["text"]) for c in chunks],
            [(0.0, 1.0, "Model"), (1.0, 2.0, "capacity"), (2.0, 3.0, "matters")],
        )

    def test_srt_cues_decode_markup_and_keep_comma_timestamps(self) -> None:
        content = (
            "1\n00:00:00,500 --> 00:00:02,000\n"
            "<i>train</i> &amp; validation\n\n"
            "2\n00:00:04,000 --> 00:00:05,250\n"
            "test data\n"
        )

        chunks = parse_subtitles(
            content,
            format="srt",
            video_id="abc123",
            title="Training guidance",
            source_url="https://www.youtube.com/watch?v=abc123",
            transcript_type="ASR",
        )

        self.assertEqual(
            [(c["start_seconds"], c["end_seconds"], c["text"]) for c in chunks],
            [(0.5, 2.0, "train & validation"), (4.0, 5.25, "test data")],
        )
        self.assertEqual([c["transcript_type"] for c in chunks], ["ASR", "ASR"])

    def test_vtt_repeated_line_within_one_cue_is_not_doubled(self) -> None:
        content = (
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000 align:start position:0%\n"
            "<c>Model bias</c>\n<c>Model bias</c>\n"
        )

        chunks = parse_subtitles(
            content,
            format="vtt",
            video_id="abc123",
            title="Training guidance",
            source_url="https://www.youtube.com/watch?v=abc123",
            transcript_type="auto",
        )

        self.assertEqual([c["text"] for c in chunks], ["Model bias"])

    def test_vtt_note_is_not_mistaken_for_a_cue(self) -> None:
        content = (
            "WEBVTT\n\nNOTE editor reminder\n"
            "00:00:01.000 --> 00:00:02.000\nnot spoken\n\n"
            "00:00:03.000 --> 00:00:04.000\nspoken\n"
        )

        chunks = parse_subtitles(
            content,
            format="vtt",
            video_id="abc123",
            title="Training guidance",
            source_url="https://www.youtube.com/watch?v=abc123",
            transcript_type="official",
        )

        self.assertEqual([(c["start_seconds"], c["text"]) for c in chunks], [(3.0, "spoken")])

    def test_unknown_subtitle_format_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "format"):
            parse_subtitles(
                "00:00:01.000 --> 00:00:02.000\ntext\n",
                format="txt",
                video_id="abc123",
                title="Training guidance",
                source_url="https://www.youtube.com/watch?v=abc123",
                transcript_type="official",
            )

    def test_unknown_transcript_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "transcript_type"):
            parse_subtitles(
                "00:00:01.000 --> 00:00:02.000\ntext\n",
                format="vtt",
                video_id="abc123",
                title="Training guidance",
                source_url="https://www.youtube.com/watch?v=abc123",
                transcript_type="unknown",
            )

    def test_reversed_cue_timing_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cue timing"):
            parse_subtitles(
                "WEBVTT\n\n00:00:03.000 --> 00:00:02.000\ntext\n",
                format="vtt",
                video_id="abc123",
                title="Training guidance",
                source_url="https://www.youtube.com/watch?v=abc123",
                transcript_type="auto",
            )

    def test_vtt_chinese_rolling_caption_preserves_new_characters_and_times(self) -> None:
        content = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n模型\n\n"
            "00:00:01.000 --> 00:00:02.000\n模型太大\n\n"
            "00:00:02.000 --> 00:00:03.000\n太大會過擬合\n"
        )

        chunks = parse_subtitles(
            content,
            format="vtt",
            video_id="abc123",
            title="Training guidance",
            source_url="https://www.youtube.com/watch?v=abc123",
            transcript_type="auto",
        )

        self.assertEqual(
            [(c["start_seconds"], c["end_seconds"], c["text"]) for c in chunks],
            [(0.0, 1.0, "模型"), (1.0, 2.0, "太大"), (2.0, 3.0, "會過擬合")],
        )


if __name__ == "__main__":
    unittest.main()
