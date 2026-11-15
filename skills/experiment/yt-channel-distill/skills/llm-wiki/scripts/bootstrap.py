#!/usr/bin/env python3
"""Check that a copied llm-wiki skill has the files needed for a dry run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()
    root = args.skill_root.resolve()
    required = [
        root / "SKILL.md",
        root / "README.md",
        root.parents[1] / "pyproject.toml",  # collection root
        root / "references" / "schema.md",
        root / "references" / "provenance-policy.md",
        root / "references" / "karpathy-method.md",
        root / "scripts" / "compile_wiki.py",
        root / "scripts" / "validate_wiki.py",
        root / "scripts" / "wiki_gate.py",
        root / "scripts" / "wiki_sync.py",
        root / "scripts" / "_wiki_core.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    result = {
        "status": "PASS" if not missing and sys.version_info >= (3, 11) else "FAIL",
        "python": platform.python_version(),
        "skill_root": str(root),
        "missing": missing,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"{result['status']}: llm-wiki bootstrap ({result['python']})")
        if missing:
            print("Missing:")
            print("\n".join(f"- {path}" for path in missing))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
