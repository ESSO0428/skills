import json
from pathlib import Path
import tempfile
import unittest

from channel_distill.cli import main
from channel_distill.manifest import save_manifest


class PrepareSourcesCommandTests(unittest.TestCase):
    def test_only_ready_transcripts_create_provenance_preserving_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            transcript = root / "transcripts" / "abc123.chunks.json"
            transcript.parent.mkdir(parents=True)
            cues = [
                {
                    "video_id": "abc123", "title": "Lecture",
                    "source_url": "https://www.youtube.com/watch?v=abc123",
                    "transcript_type": "official", "start_seconds": 1,
                    "end_seconds": 2, "text": "first",
                },
                {
                    "video_id": "abc123", "title": "Lecture",
                    "source_url": "https://www.youtube.com/watch?v=abc123",
                    "transcript_type": "official", "start_seconds": 2.1,
                    "end_seconds": 3, "text": "second",
                },
            ]
            transcript.write_text(json.dumps({"chunks": cues}), encoding="utf-8")
            save_manifest(root / "manifest" / "videos.json", {
                "abc123": {
                    "video_id": "abc123", "transcript_downloaded": True,
                    "transcript_chunks_path": str(transcript),
                },
                "missing": {"video_id": "missing", "transcript_downloaded": False},
            })
            self.assertEqual(main(["prepare-sources", "--workspace", str(root.parent)]), 0)
            outputs = list((root / "processing" / "source_chunks").glob("*.json"))
            self.assertEqual(len(outputs), 1)
            result = json.loads(outputs[0].read_text(encoding="utf-8"))
            self.assertEqual(result["video_id"], "abc123")
            self.assertEqual(result["chunks"][0]["text"], "first second")
            self.assertEqual(result["chunks"][0]["cue_end_index"], 1)

    def test_missing_claimed_transcript_is_error_not_silent_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            save_manifest(root / "manifest" / "videos.json", {
                "abc123": {
                    "video_id": "abc123", "transcript_downloaded": True,
                    "transcript_chunks_path": str(root / "missing.json"),
                }
            })
            self.assertEqual(main(["prepare-sources", "--workspace", str(root.parent)]), 1)

    def test_out_of_order_asr_cues_are_normalized_before_grouping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            transcript = root / "transcripts" / "asr123.chunks.json"
            transcript.parent.mkdir(parents=True)
            base = {
                "video_id": "asr123", "title": "Lecture",
                "source_url": "https://www.youtube.com/watch?v=asr123",
                "transcript_type": "ASR",
            }
            cues = [
                {**base, "start_seconds": 20, "end_seconds": 21, "text": "late"},
                {**base, "start_seconds": 10, "end_seconds": 11, "text": "early"},
            ]
            transcript.write_text(json.dumps({"chunks": cues}), encoding="utf-8")
            save_manifest(root / "manifest" / "videos.json", {
                "asr123": {
                    "video_id": "asr123", "transcript_downloaded": True,
                    "transcript_chunks_path": str(transcript),
                }
            })
            self.assertEqual(main(["prepare-sources", "--workspace", str(root.parent)]), 0)
            result = json.loads((root / "processing" / "source_chunks" / "asr123.json").read_text(encoding="utf-8"))
            self.assertEqual([chunk["start_seconds"] for chunk in result["chunks"]], [10, 20])
            self.assertEqual([chunk["text"] for chunk in result["chunks"]], ["early", "late"])


if __name__ == "__main__":
    unittest.main()
