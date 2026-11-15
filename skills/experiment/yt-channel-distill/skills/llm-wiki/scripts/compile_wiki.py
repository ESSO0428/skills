#!/usr/bin/env python3
"""Compile a provenance-preserving LLM Wiki from canonical JSON inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from _wiki_core import WikiError, compile_wiki


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True, help="canonical candidate JSON")
    parser.add_argument("--coverage", type=Path, required=True, help="canonical coverage JSON")
    parser.add_argument("--wiki-dir", type=Path, required=True, help="derived Wiki output directory")
    args = parser.parse_args()
    try:
        result = compile_wiki(args.candidates, args.coverage, args.wiki_dir)
    except (OSError, WikiError) as exc:
        print(f"Wiki compilation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
