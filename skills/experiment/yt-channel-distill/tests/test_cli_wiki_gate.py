import json
from pathlib import Path
import tempfile
import unittest

from channel_distill.cli import main


class WikiGateCliTests(unittest.TestCase):
    def test_cli_wiki_gate_records_terminal_event_without_mutating_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_path = root / "record.json"
            log_path = root / "wiki-gate.jsonl"
            record = {"video_id": "abc123", "status": "VERIFIED", "transcript_status": "READY"}
            record_path.write_text(json.dumps(record), encoding="utf-8")
            original = record_path.read_bytes()

            result = main(["wiki-gate", "--record", str(record_path), "--log", str(log_path)])

            self.assertEqual(result, 0)
            self.assertEqual(record_path.read_bytes(), original)
            event = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(event["terminal_state"], "READY")
            self.assertEqual(event["action"], "COMPILE")

    def test_compile_wiki_cli_uses_hash_tracked_standalone_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.json"
            coverage = root / "coverage.json"
            wiki = root / "wiki"
            candidates.write_text(json.dumps({
                "principles": [{
                    "id": "P0-CLI-001", "domain": "evaluation", "principle": "p",
                    "decision_rule": "d", "evidence_level": "EXPLICIT", "uncertainty": "u",
                    "sources": [{
                        "video_id": "v", "url": "https://example.test/?v=v",
                        "timestamp_start": 0, "timestamp_end": 1,
                        "transcript_type": "official", "source_chunk": "v:1",
                    }],
                }],
            }), encoding="utf-8")
            coverage.write_text(json.dumps({"topics": {"evaluation": {"coverage_gaps": []}}}), encoding="utf-8")
            result = main([
                "compile-wiki", "--candidates", str(candidates),
                "--coverage", str(coverage), "--wiki-dir", str(wiki),
            ])
            self.assertEqual(result, 0)
            self.assertTrue((wiki / "state.json").is_file())

    def test_compile_failure_preserves_existing_wiki_and_source_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.json"
            coverage = root / "coverage.json"
            wiki = root / "wiki"
            transcript = root / "transcript.asr.json"
            source_chunks = root / "source-chunks.jsonl"
            media = root / "video.mp4"
            valid = {
                "principles": [{
                    "id": "P0-PRESERVE-001", "domain": "evaluation", "principle": "p",
                    "decision_rule": "d", "evidence_level": "EXPLICIT", "sources": [{
                        "video_id": "v", "url": "https://example.test/?v=v",
                        "timestamp_start": 0, "timestamp_end": 1,
                        "transcript_type": "official", "source_chunk": "v:1",
                    }],
                }],
            }
            candidates.write_text(json.dumps(valid), encoding="utf-8")
            coverage.write_text(json.dumps({"topics": {"evaluation": {"coverage_gaps": []}}}), encoding="utf-8")
            for path, content in ((transcript, b"transcript"), (source_chunks, b"chunks"), (media, b"media")):
                path.write_bytes(content)
            self.assertEqual(main(["compile-wiki", "--candidates", str(candidates), "--coverage", str(coverage), "--wiki-dir", str(wiki)]), 0)
            before = {path.relative_to(wiki): path.read_bytes() for path in wiki.rglob("*") if path.is_file()}
            source_before = {path: path.read_bytes() for path in (transcript, source_chunks, media)}

            invalid = json.loads(candidates.read_text(encoding="utf-8"))
            invalid["principles"][0]["sources"][0]["timestamp_end"] = -1
            candidates.write_text(json.dumps(invalid), encoding="utf-8")
            self.assertEqual(main(["compile-wiki", "--candidates", str(candidates), "--coverage", str(coverage), "--wiki-dir", str(wiki)]), 1)

            after = {path.relative_to(wiki): path.read_bytes() for path in wiki.rglob("*") if path.is_file()}
            self.assertEqual(after, before)
            self.assertEqual({path: path.read_bytes() for path in source_before}, source_before)

    def test_incremental_candidate_rebuild_preserves_existing_p0_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.json"
            coverage = root / "coverage.json"
            wiki = root / "wiki"
            p0 = {
                "id": "P0-INCREMENT-001", "domain": "evaluation", "principle": "p0",
                "decision_rule": "d0", "evidence_level": "EXPLICIT", "sources": [{
                    "video_id": "p0", "url": "https://example.test/?v=p0",
                    "timestamp_start": 0, "timestamp_end": 1,
                    "transcript_type": "official", "source_chunk": "p0:1",
                }],
            }
            p1 = {
                "id": "P1-INCREMENT-001", "domain": "representation", "principle": "p1",
                "decision_rule": "d1", "evidence_level": "CANDIDATE", "sources": [{
                    "video_id": "p1", "url": "https://example.test/?v=p1",
                    "timestamp_start": 2, "timestamp_end": 3,
                    "transcript_type": "ASR", "source_chunk": "p1:1",
                }],
            }
            candidates.write_text(json.dumps({"principles": [p0]}), encoding="utf-8")
            coverage.write_text(json.dumps({"topics": {"evaluation": {"coverage_gaps": []}}}), encoding="utf-8")
            self.assertEqual(main(["compile-wiki", "--candidates", str(candidates), "--coverage", str(coverage), "--wiki-dir", str(wiki)]), 0)
            p0_path = wiki / "principles" / "P0-INCREMENT-001.md"
            p0_before = p0_path.read_bytes()

            candidates.write_text(json.dumps({"principles": [p0, p1]}), encoding="utf-8")
            coverage.write_text(json.dumps({"topics": {
                "evaluation": {"coverage_gaps": []},
                "representation": {"coverage_gaps": ["P1 source remains candidate review required"]},
            }}), encoding="utf-8")
            self.assertEqual(main(["compile-wiki", "--candidates", str(candidates), "--coverage", str(coverage), "--wiki-dir", str(wiki)]), 0)
            self.assertEqual(p0_path.read_bytes(), p0_before)
            self.assertTrue((wiki / "principles" / "P1-INCREMENT-001.md").is_file())
            self.assertIn("P1-INCREMENT-001", (wiki / "index.md").read_text(encoding="utf-8"))
