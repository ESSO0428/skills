#!/usr/bin/env python3
"""Run a dependency-light smoke test for a copied llm-wiki skill."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


def _fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = {
        "schema_version": 1,
        "principles": [{
            "id": "P0-SMOKE-001",
            "domain": "training-diagnosis",
            "principle": "先分辨訓練與驗證的失敗位置。",
            "decision_rule": "先比較 train 與 validation 表現。",
            "evidence_level": "EXPLICIT",
            "applicable_when": "train 與 validation 指標同時可取得時。",
            "limitations": "不能單靠一個 epoch 的數值下結論。",
            "coverage_gap": "formula-slide-review",
            "uncertainty": "需確認資料切分與評估設定。",
            "sources": [{
                "video_id": "fixture-smoke",
                "title": "Fixture lecture",
                "url": "https://example.test/watch?v=fixture-smoke",
                "timestamp_start": 12.5,
                "timestamp_end": 18.0,
                "transcript_type": "official",
                "source_chunk": "fixture-smoke:1-2",
            }],
        }],
    }
    coverage = {"schema_version": 1, "topics": {"training-diagnosis": {
        "course_years": [2021],
        "ready_transcript_ids": ["fixture-smoke"],
        "source_chunk_count": 2,
        "coverage_gaps": ["formula-slide-review"],
    }}}
    return candidates, coverage


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_json(command: list[str], *, cwd: Path) -> tuple[int, dict[str, Any], str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    stdout = completed.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {"raw_stdout": stdout}
    return completed.returncode, payload, completed.stderr.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)
    skill_root = args.skill_root.resolve()
    scripts = skill_root / "scripts"
    with tempfile.TemporaryDirectory(prefix="llm-wiki-smoke-") as temporary:
        temporary_path = Path(temporary)
        candidates = temporary_path / "candidates.json"
        coverage = temporary_path / "coverage.json"
        wiki_dir = temporary_path / "wiki"
        fixture_candidates, fixture_coverage = _fixture()
        candidates.write_text(json.dumps(fixture_candidates, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        coverage.write_text(json.dumps(fixture_coverage, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        input_hashes_before = (_sha256(candidates), _sha256(coverage))

        bootstrap_returncode, bootstrap, bootstrap_stderr = _run_json(
            [sys.executable, str(scripts / "bootstrap.py"), "--skill-root", str(skill_root), "--json"],
            cwd=skill_root,
        )
        compile_command = [
            sys.executable,
            str(scripts / "compile_wiki.py"),
            "--candidates", str(candidates),
            "--coverage", str(coverage),
            "--wiki-dir", str(wiki_dir),
        ]
        first_returncode, first_compile, first_stderr = _run_json(compile_command, cwd=skill_root)
        first_snapshot = sorted(
            (path.relative_to(wiki_dir).as_posix(), _sha256(path))
            for path in wiki_dir.rglob("*")
            if path.is_file()
        ) if wiki_dir.exists() else []
        second_returncode, second_compile, second_stderr = _run_json(compile_command, cwd=skill_root)
        second_snapshot = sorted(
            (path.relative_to(wiki_dir).as_posix(), _sha256(path))
            for path in wiki_dir.rglob("*")
            if path.is_file()
        ) if wiki_dir.exists() else []
        validate_returncode, validate, validate_stderr = _run_json(
            [
                sys.executable,
                str(scripts / "validate_wiki.py"),
                "--candidates", str(candidates),
                "--coverage", str(coverage),
                "--wiki-dir", str(wiki_dir),
            ],
            cwd=skill_root,
        )
        inputs_unchanged = input_hashes_before == (_sha256(candidates), _sha256(coverage))

    idempotent = first_snapshot == second_snapshot and first_compile.get("input_sha256") == second_compile.get("input_sha256")
    status = "PASS" if all([
        bootstrap_returncode == 0,
        bootstrap.get("status") == "PASS",
        first_returncode == 0,
        second_returncode == 0,
        validate_returncode == 0,
        str(validate.get("status", "")).lower() == "pass",
        idempotent,
        inputs_unchanged,
    ]) else "FAIL"
    result = {
        "status": status,
        "python": sys.version.split()[0],
        "skill_root": str(skill_root),
        "bootstrap": {"status": bootstrap.get("status"), "returncode": bootstrap_returncode, "stderr": bootstrap_stderr},
        "compile": {
            "first_returncode": first_returncode,
            "second_returncode": second_returncode,
            "first": first_compile,
            "second": second_compile,
            "idempotent": idempotent,
            "stderr": [item for item in (first_stderr, second_stderr) if item],
        },
        "validate": {"status": validate.get("status"), "returncode": validate_returncode, "stderr": validate_stderr},
        "inputs_unchanged": inputs_unchanged,
        "temporary_workspace_cleaned": not temporary_path.exists(),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"{status}: llm-wiki package smoke test ({result['python']})")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
