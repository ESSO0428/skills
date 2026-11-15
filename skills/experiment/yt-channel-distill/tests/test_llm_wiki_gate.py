import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT_DIR = ROOT / "skills" / "llm-wiki" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from wiki_gate import decide_evidence_gate, decide_gate  # noqa: E402


class LlmWikiGateTests(unittest.TestCase):
    def test_four_terminal_states_have_deterministic_actions(self):
        ready = decide_gate({"video_id": "ready", "status": "VERIFIED", "transcript_status": "READY"})
        self.assertEqual((ready["terminal_state"], ready["action"]), ("READY", "COMPILE"))

        partial = decide_gate({
            "video_id": "partial",
            "status": "VERIFIED",
            "transcript_status": "READY",
            "transcript_unavailable_segments": [{"start": 10, "end": 20}],
        })
        self.assertEqual((partial["terminal_state"], partial["action"]), ("READY_PARTIAL", "COMPILE_WITH_GAPS"))

        failed = decide_gate({"video_id": "failed", "status": "DOWNLOAD_FAILED"})
        self.assertEqual((failed["terminal_state"], failed["action"]), ("FAILED", "RECORD_BLOCKED"))

        agy_blocked = decide_gate({
            "video_id": "agy",
            "status": "VERIFIED",
            "transcript_status": "READY",
            "agy_status": "VIDEO_DOWNLOAD_BLOCKED",
        })
        self.assertEqual((agy_blocked["terminal_state"], agy_blocked["action"]), ("AGY_BLOCKED", "RECORD_BLOCKED"))

    def test_fingerprint_ignores_persisted_derived_gate_state(self):
        record = {"video_id": "ready", "status": "VERIFIED", "transcript_status": "READY"}
        first = decide_gate(record)
        persisted = {**record, "wiki_gate": first}
        second = decide_gate(persisted)
        self.assertEqual(second["record_sha256"], first["record_sha256"])

    def test_duration_mismatch_marks_supplement_for_review_without_canonical_merge(self):
        event = decide_evidence_gate(
            {
                "packet_type": "AGY_SUPPLEMENTAL_OBSERVATION",
                "video_id": "mismatch",
                "agy": {
                    "status": "SUCCESS",
                    "coverage_status": "PARTIAL_DURATION_MISMATCH",
                    "reported_duration_seconds": 637,
                    "canonical_duration_seconds": 5351,
                },
                "merge_decision": "NOT_MERGED_AS_CANONICAL",
            },
            {"video_id": "mismatch", "status": "VERIFIED", "transcript_status": "READY"},
        )
        self.assertEqual((event["terminal_state"], event["action"]), ("READY", "RECORD_SUPPLEMENT"))
        self.assertTrue(event["supplement_review_required"])
        self.assertIn("duration", event["supplement_review_reason"])

    def test_cli_can_record_one_gate_event_without_touching_manifest(self):
        record = {"video_id": "ready", "status": "VERIFIED", "transcript_status": "READY"}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "record.json"
            log = root / "wiki-gate.jsonl"
            manifest.write_text(json.dumps(record), encoding="utf-8")
            original = manifest.read_bytes()
            result = subprocess.run([
                sys.executable, str(SCRIPT_DIR / "wiki_gate.py"),
                "--record", str(manifest), "--log", str(log),
            ], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(manifest.read_bytes(), original)
            event = json.loads(log.read_text(encoding="utf-8").strip())
            self.assertEqual(event["terminal_state"], "READY")
            self.assertEqual(event["action"], "COMPILE")

    def test_manifest_sync_compiles_once_and_preserves_all_terminal_gaps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "videos.json"
            candidates = root / "candidates.json"
            coverage = root / "coverage.json"
            wiki = root / "wiki"
            log = root / "gate.jsonl"
            payload = {"videos": {
                "ready": {"video_id": "ready", "verified": True, "transcript_status": "READY"},
                "partial": {"video_id": "partial", "status": "VERIFIED", "transcript_status": "READY_PARTIAL", "transcript_unavailable_segments": [{"start": 1, "end": 2}]},
                "failed": {"video_id": "failed", "status": "DOWNLOAD_FAILED"},
                "agy": {"video_id": "agy", "status": "VERIFIED", "transcript_status": "READY", "agy_status": "VIDEO_DOWNLOAD_BLOCKED"},
            }}
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            original = manifest.read_bytes()
            candidates.write_text(json.dumps({"principles": [{
                "id": "P0-SYNC-001", "domain": "evaluation", "principle": "p", "decision_rule": "d",
                "evidence_level": "EXPLICIT", "sources": [{
                    "video_id": "ready", "url": "https://example.test/?v=ready",
                    "timestamp_start": 0, "timestamp_end": 1, "transcript_type": "official", "source_chunk": "ready:1",
                }],
            }]}), encoding="utf-8")
            coverage.write_text(json.dumps({"topics": {"evaluation": {"coverage_gaps": ["partial:1-2"]}}}), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT_DIR / "wiki_sync.py"),
                "--manifest", str(manifest), "--log", str(log),
                "--candidates", str(candidates), "--coverage", str(coverage), "--wiki-dir", str(wiki),
            ], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(manifest.read_bytes(), original)
            events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({event["terminal_state"] for event in events}, {"READY", "READY_PARTIAL", "FAILED", "AGY_BLOCKED"})
            self.assertTrue((wiki / "state.json").is_file())

    def test_manifest_sync_records_successful_evidence_packet_without_canonical_merge(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "videos.json"
            candidates = root / "candidates.json"
            coverage = root / "coverage.json"
            wiki = root / "wiki"
            log = root / "gate.jsonl"
            evidence = root / "evidence"
            evidence.mkdir()
            manifest.write_text(json.dumps({"videos": {
                "ready": {"video_id": "ready", "verified": True, "transcript_status": "READY"},
            }}), encoding="utf-8")
            candidates.write_text(json.dumps({"principles": []}), encoding="utf-8")
            coverage.write_text(json.dumps({"topics": {}}), encoding="utf-8")
            (evidence / "ready.packet.json").write_text(json.dumps({
                "packet_type": "AGY_SUPPLEMENTAL_OBSERVATION",
                "video_id": "ready",
                "agy": {"status": "SUCCESS"},
                "merge_decision": "NOT_MERGED_AS_CANONICAL",
            }), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT_DIR / "wiki_sync.py"),
                "--manifest", str(manifest), "--log", str(log),
                "--candidates", str(candidates), "--coverage", str(coverage),
                "--wiki-dir", str(wiki), "--evidence-dir", str(evidence),
            ], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            packet_events = [event for event in events if event.get("event_type") == "evidence_packet"]
            self.assertEqual(len(packet_events), 1)
            self.assertEqual(packet_events[0]["terminal_state"], "READY")
            self.assertEqual(packet_events[0]["action"], "RECORD_SUPPLEMENT")
            self.assertEqual(packet_events[0]["merge_decision"], "NOT_MERGED_AS_CANONICAL")
            self.assertTrue(packet_events[0]["packet_sha256"])

    def test_manifest_sync_records_blocked_evidence_packet_as_agy_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "videos.json"
            log = root / "gate.jsonl"
            evidence = root / "evidence"
            evidence.mkdir()
            manifest.write_text(json.dumps({"videos": {
                "blocked": {"video_id": "blocked", "verified": True, "transcript_status": "READY"},
            }}), encoding="utf-8")
            (evidence / "blocked.packet.json").write_text(json.dumps({
                "packet_type": "AGY_SUPPLEMENTAL_OBSERVATION",
                "video_id": "blocked",
                "agy": {"status": "VIDEO_DOWNLOAD_BLOCKED"},
            }), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT_DIR / "wiki_sync.py"),
                "--manifest", str(manifest), "--log", str(log),
                "--evidence-dir", str(evidence), "--dry-run",
            ], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            result_payload = json.loads(result.stdout)
            self.assertEqual(result_payload["evidence_packet_count"], 1)
            self.assertEqual(result_payload["evidence_blocked_count"], 1)


if __name__ == "__main__":
    unittest.main()
