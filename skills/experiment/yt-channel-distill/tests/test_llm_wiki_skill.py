import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
SKILL = ROOT / "skills" / "llm-wiki"


class LlmWikiSkillTests(unittest.TestCase):
    def test_skill_compiles_and_validates_traceable_fixture_idempotently(self):
        self.assertTrue((SKILL / "SKILL.md").is_file())
        self.assertTrue((SKILL / "scripts" / "compile_wiki.py").is_file())
        self.assertTrue((SKILL / "scripts" / "validate_wiki.py").is_file())

        candidates = {
            "schema_version": 1,
            "principles": [{
                "id": "P0-TEST-001",
                "domain": "training-diagnosis",
                "principle": "先分辨訓練與驗證的失敗位置。",
                "decision_rule": "先比較 train 與 validation 表現。",
                "evidence_level": "EXPLICIT",
                "applicable_when": "train 與 validation 指標同時可取得時。",
                "limitations": "不能單靠一個 epoch 的數值下結論。",
                "coverage_gap": "formula-slide-review",
                "uncertainty": "需確認資料切分與評估設定。",
                "sources": [{
                    "video_id": "fixture123",
                    "title": "Fixture lecture",
                    "url": "https://example.test/watch?v=fixture123",
                    "timestamp_start": 12.5,
                    "timestamp_end": 18.0,
                    "transcript_type": "official",
                    "source_chunk": "fixture123:1-2",
                }],
            }],
        }
        coverage = {"schema_version": 1, "topics": {"training-diagnosis": {
            "course_years": [2021],
            "ready_transcript_ids": ["fixture123"],
            "source_chunk_count": 2,
            "coverage_gaps": ["formula-slide-review"],
        }}}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates_path = root / "candidates.json"
            coverage_path = root / "coverage.json"
            wiki_dir = root / "wiki"
            candidates_path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
            coverage_path.write_text(json.dumps(coverage, ensure_ascii=False), encoding="utf-8")

            compile_cmd = [
                sys.executable,
                str(SKILL / "scripts" / "compile_wiki.py"),
                "--candidates", str(candidates_path),
                "--coverage", str(coverage_path),
                "--wiki-dir", str(wiki_dir),
            ]
            first = subprocess.run(compile_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_index = (wiki_dir / "index.md").read_text(encoding="utf-8")
            first_card = (wiki_dir / "principles" / "P0-TEST-001.md").read_text(encoding="utf-8")
            self.assertIn("fixture123&t=12", first_card)
            self.assertIn("fixture123:1-2", first_card)
            self.assertIn("formula-slide-review", first_card)
            self.assertIn("formula-slide-review", first_index + (wiki_dir / "topics" / "training-diagnosis.md").read_text(encoding="utf-8"))

            second = subprocess.run(compile_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first_card, (wiki_dir / "principles" / "P0-TEST-001.md").read_text(encoding="utf-8"))

            validate_cmd = [
                sys.executable,
                str(SKILL / "scripts" / "validate_wiki.py"),
                "--candidates", str(candidates_path),
                "--coverage", str(coverage_path),
                "--wiki-dir", str(wiki_dir),
            ]
            validated = subprocess.run(validate_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertIn('"status": "pass"', validated.stdout.lower())


if __name__ == "__main__":
    unittest.main()
