"""One bounded local-ASR batch, run in a disposable Python process.

The parent process extracts a short set of WAV windows and invokes this module.
Letting the process exit after each batch releases oneMKL allocations that are
not reliably returned by the in-process backend on this host.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .asr import _atomic_json, _collect_chunks, _make_model, _offset_chunks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one local faster-whisper ASR batch")
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _failure(output: Path, status: str, error: Exception) -> int:
    _atomic_json(output, {"status": status, "error": str(error)[:2000]})
    return 2


def main() -> int:
    args = _parse_args()
    try:
        request = json.loads(args.jobs.read_text(encoding="utf-8"))
        record = request["record"]
        jobs = request["jobs"]
        if not isinstance(record, dict) or not isinstance(jobs, list) or not jobs:
            raise ValueError("jobs request must contain a record and a non-empty jobs list")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _failure(args.output, "ASR_WORKER_INVALID_REQUEST", exc)

    try:
        model = _make_model(args.model_path)
        chunks: list[dict[str, Any]] = []
        zero_duration_words = 0
        language = None
        for job in jobs:
            if not isinstance(job, dict):
                raise ValueError("ASR job must be an object")
            audio_path = Path(job["audio_path"])
            offset = float(job["offset_seconds"])
            if not audio_path.is_file() or audio_path.stat().st_size <= 0:
                raise ValueError(f"ASR audio window missing: {audio_path}")
            segments, info = model.transcribe(str(audio_path), word_timestamps=True, vad_filter=True)
            window_chunks, window_warnings = _collect_chunks(segments, record)
            _offset_chunks(window_chunks, offset)
            chunks.extend(window_chunks)
            zero_duration_words += window_warnings
            language = language or getattr(info, "language", None)
    except ImportError as exc:
        return _failure(args.output, "ASR_BACKEND_MISSING", exc)
    except (AttributeError, TypeError, ValueError) as exc:
        return _failure(args.output, "ASR_INVALID_OUTPUT", exc)
    except Exception as exc:  # backend/device failures are intentionally explicit and retryable
        return _failure(args.output, "ASR_FAILED", exc)

    _atomic_json(
        args.output,
        {
            "status": "READY",
            "video_id": record["video_id"],
            "offsets": [job["offset_seconds"] for job in jobs],
            "language": language,
            "zero_duration_words": zero_duration_words,
            "chunks": chunks,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
