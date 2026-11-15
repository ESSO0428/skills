from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).parents[1]


class SkillScriptContractTests(unittest.TestCase):
    def test_packaged_cli_scripts_expose_help_without_project_cwd_assumptions(self):
        scripts = [
            ROOT / "skills" / "llm-wiki" / "scripts" / name
            for name in (
                "bootstrap.py",
                "compile_wiki.py",
                "validate_wiki.py",
                "wiki_gate.py",
                "wiki_sync.py",
                "smoke_test.py",
            )
        ]
        scripts.extend([
            ROOT / "skills" / "acquiring-video-sources" / "scripts" / "agy_batch_jobs.py",
            ROOT / "skills" / "acquiring-video-sources" / "scripts" / "acquire_video_batch.py",
            ROOT / "skills" / "acquiring-video-sources" / "scripts" / "video_batch_report.py",
            ROOT / "skills" / "acquiring-video-sources" / "scripts" / "extract_video_frames.py",
            ROOT / "skills" / "acquiring-video-sources" / "scripts" / "agy_zero_shot_batch.py",
            ROOT / "skills" / "distilling-youtube-channel" / "scripts" / "build_semantic_review.py",
        ])
        for script in scripts:
            result = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=ROOT.parent,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")
            self.assertIn("usage:", result.stdout.lower(), str(script))

    def test_packaged_scripts_do_not_embed_machine_specific_paths(self):
        roots = [
            ROOT / "skills" / "llm-wiki",
            ROOT / "skills" / "distilling-youtube-channel",
            ROOT / "skills" / "acquiring-video-sources",
        ]
        for root in roots:
            for script in root.rglob("*.py"):
                if ".venv" in script.parts:
                    continue
                text = script.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"[A-Za-z]:\\Users\\|/Users/|/home/")


if __name__ == "__main__":
    unittest.main()
