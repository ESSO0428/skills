from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from channel_distill.coverage import build_p0_coverage_report


class CoverageAuditTests(unittest.TestCase):
    def test_reports_source_facts_and_explicit_gaps(self) -> None:
        records = {
            "ready": {
                "topic_priority": "P0",
                "topics": [{"topic": "evaluation", "priority": "P0"}],
                "verified": True,
                "transcript_downloaded": True,
                "transcript_status": "READY",
                "transcript_type": "official",
                "course_associations": [{"course": "ML 2021", "course_year": 2021}],
            },
            "needs_asr": {
                "topic_priority": "P0",
                "topics": [{"topic": "evaluation", "priority": "P0"}],
                "verified": True,
                "transcript_downloaded": False,
                "transcript_status": "ASR_NEEDED",
                "course_associations": [{"course": "ML 2023", "course_year": 2023}],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            chunks_dir = Path(temporary_directory)
            (chunks_dir / "ready.json").write_text(
                json.dumps({"chunks": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8"
            )
            report = build_p0_coverage_report(records, chunks_dir)

        evaluation = report["topics"]["evaluation"]
        self.assertEqual(evaluation["source_chunk_count"], 2)
        self.assertEqual(evaluation["course_years"], [2021, 2023])
        self.assertEqual(evaluation["transcript_types"], {"official": 1})
        self.assertEqual(evaluation["asr_needed_ids"], ["needs_asr"])
        self.assertEqual(evaluation["transcript_unavailable_ids"], ["needs_asr"])
        self.assertEqual(evaluation["coverage_gaps"], ["ASR_NEEDED", "TRANSCRIPT_UNAVAILABLE"])

    def test_fetch_failure_is_reported_as_unavailable_even_when_media_is_verified(self) -> None:
        records = {
            "subtitle_fetch_failed": {
                "topic_priority": "P0",
                "topics": [{"topic": "evaluation", "priority": "P0"}],
                "verified": True,
                "transcript_downloaded": False,
                "transcript_status": "FETCH_FAILED",
                "transcript_type": "missing",
            }
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = build_p0_coverage_report(records, Path(temporary_directory))

        evaluation = report["topics"]["evaluation"]
        self.assertEqual(evaluation["verified_media_ids"], ["subtitle_fetch_failed"])
        self.assertEqual(evaluation["asr_needed_ids"], [])
        self.assertEqual(evaluation["transcript_unavailable_ids"], ["subtitle_fetch_failed"])
        self.assertEqual(
            evaluation["coverage_gaps"],
            ["NO_READY_TRANSCRIPT", "TRANSCRIPT_UNAVAILABLE", "LIMITED_COURSE_YEAR_COVERAGE", "NO_SOURCE_CHUNKS"],
        )

    def test_retryable_asr_failure_remains_in_the_asr_queue(self) -> None:
        records = {
            "asr_failed": {
                "topic_priority": "P0",
                "topics": [{"topic": "evaluation", "priority": "P0"}],
                "verified": True,
                "transcript_downloaded": False,
                "transcript_status": "ASR_FAILED",
                "transcript_type": "missing",
            }
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = build_p0_coverage_report(records, Path(temporary_directory))

        evaluation = report["topics"]["evaluation"]
        self.assertEqual(evaluation["asr_needed_ids"], ["asr_failed"])
        self.assertIn("ASR_NEEDED", evaluation["coverage_gaps"])
