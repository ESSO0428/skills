"""Opt-in, local-only ASR fallback for verified videos without usable subtitles.

The model must already exist on disk. This module never fetches model weights or
media from the network, and ASR output is never labelled as an official caption.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,32}$")
_AUDIO_BYTES_PER_SECOND = 16_000 * 2  # mono, signed 16-bit PCM
_GIB = 1024**3
# Some long recordings still exhaust oneMKL with 30-second windows despite
# serial CPU inference.  Fifteen seconds bounds the per-window feature allocation.
_ASR_WINDOW_SECONDS = 15
_MODEL_RESTART_EVERY_WINDOWS = 25
# A real subprocess releases oneMKL allocations reliably.  The shorter clips
# keep the lower-overhead in-process path; long videos use resumable batches.
_ASR_WORKER_MIN_DURATION_SECONDS = 900
_ASR_WORKER_BATCH_WINDOWS = 20
# If even a small fallback still exhausts oneMKL, single-window workers are
# the last bounded retry. This path is used only after an explicit allocator
# failure and keeps the normal 20-window throughput unchanged.
_ASR_MEMORY_FALLBACK_BATCH_WINDOWS = 1
_ASR_SEGMENT_RETRY_LIMIT = 2


def _run_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=7200)


def _run_asr_worker(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=7200)


def _make_model(model_path: Path) -> Any:
    """Load only already-present weights; never permit an implicit download."""
    from faster_whisper import WhisperModel  # optional, deliberately lazy dependency

    # This workspace has no CUDA device.  CPU int8 avoids a large float32
    # feature allocation on long recordings while retaining the local-only rule.
    return WhisperModel(
        str(model_path), device="cpu", compute_type="int8", local_files_only=True,
        cpu_threads=1, num_workers=1,
    )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class _AsrWorkerFailure(RuntimeError):
    def __init__(self, status: str, error: str) -> None:
        super().__init__(error)
        self.status = status


def _is_memory_allocation_failure(status: Any, error: Any) -> bool:
    """Recognize only explicit allocator failures eligible for bounded retry."""
    if status != "ASR_FAILED" or not isinstance(error, str):
        return False
    message = error.lower()
    return any(
        marker in message
        for marker in (
            "mkl_malloc",
            "out of memory",
            "cannot allocate memory",
            "memory allocation",
            "std::bad_alloc",
        )
    )


def _checkpoint_directory(
    transcript_dir: Path, video_id: str, video_path: Path, model_path: Path, duration: float
) -> Path:
    signature_data = {
        "video_path": str(video_path.resolve()),
        "video_size": video_path.stat().st_size,
        "video_mtime_ns": video_path.stat().st_mtime_ns,
        "model_path": str(model_path.resolve()),
        "model_mtime_ns": model_path.stat().st_mtime_ns,
        "duration": duration,
        "window_seconds": _ASR_WINDOW_SECONDS,
        "batch_windows": _ASR_WORKER_BATCH_WINDOWS,
    }
    encoded = json.dumps(signature_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return transcript_dir / ".asr-checkpoints" / f"{video_id}-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _read_ready_worker_payload(
    path: Path, *, expected_video_id: str, expected_source_url: str, expected_offsets: list[int], duration: float
) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "READY"
        or not isinstance(payload.get("chunks"), list)
        or not isinstance(payload.get("zero_duration_words"), int)
    ):
        return None
    legacy_payload = payload.get("video_id") is None and payload.get("offsets") is None
    if not legacy_payload and (
        payload.get("video_id") != expected_video_id or payload.get("offsets") != expected_offsets
    ):
        return None
    batch_start = float(expected_offsets[0])
    batch_end = min(duration, float(expected_offsets[-1] + _ASR_WINDOW_SECONDS))
    for chunk in payload["chunks"]:
        if (
            not isinstance(chunk, dict)
            or chunk.get("video_id") != expected_video_id
            or chunk.get("source_url") != expected_source_url
            or chunk.get("transcript_type") != "ASR"
            or not isinstance(chunk.get("words"), list)
        ):
            return None
        try:
            start, end = _valid_interval(chunk.get("start_seconds"), chunk.get("end_seconds"))
        except ValueError:
            return None
        # A small tolerance permits decoder boundary rounding but prevents a
        # valid-looking checkpoint from a different batch being silently used.
        if start < batch_start - 0.25 or end > batch_end + 0.25:
            return None
        for word in chunk["words"]:
            if not isinstance(word, dict) or not isinstance(word.get("text"), str):
                return None
            try:
                word_start, word_end = _valid_interval(
                    word.get("start_seconds"), word.get("end_seconds"), allow_zero=True
                )
            except ValueError:
                return None
            if word_start < start - 0.25 or word_end > end + 0.25:
                return None
    # Checkpoints written before identity fields were added are accepted only
    # after the same schema/timing validation, then atomically upgraded. This
    # preserves verified work from an interrupted local run without trusting a
    # mismatched batch in later runs.
    if legacy_payload:
        payload["video_id"] = expected_video_id
        payload["offsets"] = expected_offsets
        _atomic_json(path, payload)
    return payload


def _transcribe_worker_batches(
    updated: dict[str, Any],
    *,
    video_path: Path,
    transcript_dir: Path,
    ffmpeg: str | Path,
    model_path: Path,
    duration: float,
) -> tuple[list[dict[str, Any]], int, str | None, list[dict[str, Any]]]:
    """Run bounded ASR batches with durable, validated checkpoints.

    A failure leaves successful batch JSON files in a signature-specific
    directory.  Retrying the same verified media reuses only those complete
    batches; incomplete/error batches are re-run in a fresh child process.
    """
    video_id = str(updated["video_id"])
    checkpoint_dir = _checkpoint_directory(transcript_dir, video_id, video_path, model_path, duration)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(
        checkpoint_dir / "run.json",
        {
            "video_id": video_id,
            "video_path": str(video_path),
            "model_path": str(model_path),
            "duration": duration,
            "window_seconds": _ASR_WINDOW_SECONDS,
            "batch_windows": _ASR_WORKER_BATCH_WINDOWS,
        },
    )
    offsets = list(range(0, math.ceil(duration), _ASR_WINDOW_SECONDS))
    all_chunks: list[dict[str, Any]] = []
    zero_duration_words = 0
    language: str | None = None
    unavailable_segments: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"{video_id}-asr-", dir=transcript_dir) as scratch:
        scratch_path = Path(scratch)
        for batch_number, first in enumerate(range(0, len(offsets), _ASR_WORKER_BATCH_WINDOWS)):
            batch_offsets = offsets[first:first + _ASR_WORKER_BATCH_WINDOWS]
            result_path = checkpoint_dir / f"batch-{batch_number:04d}.json"
            payload = _read_ready_worker_payload(
                result_path,
                expected_video_id=video_id,
                expected_source_url=str(updated["url"]),
                expected_offsets=batch_offsets,
                duration=duration,
            )
            if payload is None:
                jobs: list[dict[str, Any]] = []
                for offset in batch_offsets:
                    window_duration = (
                        duration + 30.0
                        if duration <= _ASR_WINDOW_SECONDS
                        else min(_ASR_WINDOW_SECONDS, duration - offset)
                    )
                    audio_path = scratch_path / f"audio-{offset:08d}.wav"
                    command = [
                        str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", str(offset), "-i", str(video_path), "-t", str(window_duration),
                        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio_path),
                    ]
                    try:
                        ffmpeg_result = _run_ffmpeg(command)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        raise _AsrWorkerFailure("ASR_AUDIO_FAILED", str(exc)) from exc
                    if (
                        ffmpeg_result.returncode != 0
                        or not audio_path.is_file()
                        or audio_path.stat().st_size == 0
                    ):
                        raise _AsrWorkerFailure(
                            "ASR_AUDIO_FAILED", ffmpeg_result.stderr or "ffmpeg produced no audio"
                        )
                    jobs.append({"audio_path": str(audio_path), "offset_seconds": offset})
                jobs_path = scratch_path / f"batch-{batch_number:04d}.jobs.json"
                _atomic_json(jobs_path, {"record": updated, "jobs": jobs})
                worker_command = [
                    sys.executable, "-m", "channel_distill.asr_worker",
                    "--jobs", str(jobs_path), "--model-path", str(model_path), "--output", str(result_path),
                ]
                try:
                    worker_result = _run_asr_worker(worker_command)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise _AsrWorkerFailure("ASR_WORKER_FAILED", str(exc)) from exc
                payload = _read_ready_worker_payload(
                    result_path,
                    expected_video_id=video_id,
                    expected_source_url=str(updated["url"]),
                    expected_offsets=batch_offsets,
                    duration=duration,
                )
                if payload is None:
                    try:
                        failure_payload = json.loads(result_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        failure_payload = {}
                    status = failure_payload.get("status") if isinstance(failure_payload, dict) else None
                    error = failure_payload.get("error") if isinstance(failure_payload, dict) else None
                    error_text = str(error or worker_result.stderr or "ASR worker produced no valid checkpoint")
                    if _is_memory_allocation_failure(status, error_text):
                        fallback_chunks: list[dict[str, Any]] = []
                        fallback_zero_duration_words = 0
                        fallback_language: str | None = None
                        fallback_unavailable_segments: list[dict[str, Any]] = []
                        for fallback_number, sub_first in enumerate(
                            range(0, len(batch_offsets), _ASR_MEMORY_FALLBACK_BATCH_WINDOWS)
                        ):
                            sub_offsets = batch_offsets[sub_first:sub_first + _ASR_MEMORY_FALLBACK_BATCH_WINDOWS]
                            sub_jobs = jobs[sub_first:sub_first + _ASR_MEMORY_FALLBACK_BATCH_WINDOWS]
                            unavailable_path = checkpoint_dir / (
                                f"batch-{batch_number:04d}.fallback-{fallback_number:04d}.unavailable.json"
                            )
                            try:
                                unavailable_payload = json.loads(unavailable_path.read_text(encoding="utf-8"))
                            except (OSError, json.JSONDecodeError):
                                unavailable_payload = None
                            if isinstance(unavailable_payload, dict) and unavailable_payload.get("status") == "ASR_SEGMENT_UNAVAILABLE":
                                fallback_unavailable_segments.append(unavailable_payload["segment"])
                                continue

                            sub_payload = None
                            sub_error = "ASR fallback worker failed"
                            sub_status = "ASR_WORKER_FAILED"
                            for _attempt in range(1, _ASR_SEGMENT_RETRY_LIMIT + 1):
                                sub_jobs_path = scratch_path / (
                                    f"batch-{batch_number:04d}.fallback-{fallback_number:04d}.jobs.json"
                                )
                                sub_result_path = scratch_path / (
                                    f"batch-{batch_number:04d}.fallback-{fallback_number:04d}.json"
                                )
                                _atomic_json(sub_jobs_path, {"record": updated, "jobs": sub_jobs})
                                sub_worker_result = _run_asr_worker([
                                    sys.executable, "-m", "channel_distill.asr_worker",
                                    "--jobs", str(sub_jobs_path), "--model-path", str(model_path),
                                    "--output", str(sub_result_path),
                                ])
                                sub_payload = _read_ready_worker_payload(
                                    sub_result_path,
                                    expected_video_id=video_id,
                                    expected_source_url=str(updated["url"]),
                                    expected_offsets=sub_offsets,
                                    duration=duration,
                                )
                                if sub_payload is not None and sub_worker_result.returncode == 0:
                                    break
                                try:
                                    sub_failure = json.loads(sub_result_path.read_text(encoding="utf-8"))
                                except (OSError, json.JSONDecodeError):
                                    sub_failure = {}
                                sub_status = (
                                    sub_failure.get("status")
                                    if isinstance(sub_failure, dict) and isinstance(sub_failure.get("status"), str)
                                    else "ASR_WORKER_FAILED"
                                )
                                sub_error = str(
                                    sub_failure.get("error")
                                    if isinstance(sub_failure, dict) and sub_failure.get("error")
                                    else sub_worker_result.stderr or "ASR fallback worker failed"
                                )
                            if sub_payload is None or sub_worker_result.returncode != 0:
                                segment = {
                                    "offset_seconds": int(sub_offsets[0]),
                                    "end_seconds": int(min(duration, sub_offsets[-1] + _ASR_WINDOW_SECONDS)),
                                    "attempts": _ASR_SEGMENT_RETRY_LIMIT,
                                    "status": sub_status,
                                    "error": sub_error[:2000],
                                }
                                _atomic_json(
                                    unavailable_path,
                                    {"status": "ASR_SEGMENT_UNAVAILABLE", "segment": segment},
                                )
                                fallback_unavailable_segments.append(segment)
                                continue
                            fallback_chunks.extend(sub_payload["chunks"])
                            fallback_zero_duration_words += sub_payload["zero_duration_words"]
                            sub_language = sub_payload.get("language")
                            if fallback_language is None and isinstance(sub_language, str):
                                fallback_language = sub_language
                        _atomic_json(
                            result_path,
                            {
                                "status": "READY",
                                "video_id": video_id,
                                "offsets": batch_offsets,
                                "language": fallback_language,
                                "zero_duration_words": fallback_zero_duration_words,
                                "unavailable_segments": fallback_unavailable_segments,
                                "chunks": fallback_chunks,
                            },
                        )
                        payload = _read_ready_worker_payload(
                            result_path,
                            expected_video_id=video_id,
                            expected_source_url=str(updated["url"]),
                            expected_offsets=batch_offsets,
                            duration=duration,
                        )
                        if payload is not None:
                            # The original full-batch process failed, but the
                            # validated sub-batches collectively succeeded.
                            worker_result = subprocess.CompletedProcess(
                                worker_result.args, 0, worker_result.stdout, worker_result.stderr
                            )
                    if payload is None:
                        raise _AsrWorkerFailure(
                            status if isinstance(status, str) else "ASR_WORKER_FAILED",
                            error_text,
                        )
                if worker_result.returncode != 0:
                    raise _AsrWorkerFailure(
                        "ASR_WORKER_FAILED", worker_result.stderr or "ASR worker exited non-zero after success payload"
                    )
            all_chunks.extend(payload["chunks"])
            zero_duration_words += payload["zero_duration_words"]
            batch_unavailable = payload.get("unavailable_segments")
            if isinstance(batch_unavailable, list):
                unavailable_segments.extend(
                    item for item in batch_unavailable if isinstance(item, dict)
                )
            batch_language = payload.get("language")
            if language is None and isinstance(batch_language, str):
                language = batch_language
    return all_chunks, zero_duration_words, language, unavailable_segments


def _valid_interval(start: Any, end: Any, *, allow_zero: bool = False) -> tuple[float, float]:
    try:
        first, last = float(start), float(end)
    except (TypeError, ValueError) as exc:
        raise ValueError("ASR timestamp is not numeric") from exc
    if (
        not math.isfinite(first)
        or not math.isfinite(last)
        or first < 0
        or last < first
        or (last == first and not allow_zero)
    ):
        raise ValueError(f"invalid ASR timestamp interval: {first} to {last}")
    return first, last


def _collect_chunks(segments: Any, record: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    chunks: list[dict[str, Any]] = []
    zero_duration_words = 0
    previous_start = -1.0
    for segment in segments:
        start, end = _valid_interval(segment.start, segment.end)
        if start < previous_start:
            raise ValueError("ASR segments are not chronological")
        previous_start = start
        spoken = str(segment.text).strip()
        if not spoken:
            continue
        words: list[dict[str, Any]] = []
        for word in segment.words or []:
            word_start, word_end = _valid_interval(word.start, word.end, allow_zero=True)
            word_payload = {
                "start_seconds": word_start,
                "end_seconds": word_end,
                "text": str(word.word).strip(),
            }
            if word_start == word_end:
                zero_duration_words += 1
                word_payload["timing_quality"] = "zero_duration"
            words.append(word_payload)
        chunks.append(
            {
                "start_seconds": start,
                "end_seconds": end,
                "text": spoken,
                "video_id": record["video_id"],
                "title": record.get("title") or "",
                "source_url": record["url"],
                "transcript_type": "ASR",
                "words": words,
            }
        )
    return chunks, zero_duration_words


def _offset_chunks(chunks: list[dict[str, Any]], offset_seconds: float) -> None:
    """Translate window-local ASR timings to the original video's clock."""
    for chunk in chunks:
        chunk["start_seconds"] += offset_seconds
        chunk["end_seconds"] += offset_seconds
        for word in chunk["words"]:
            word["start_seconds"] += offset_seconds
            word["end_seconds"] += offset_seconds


def _failure(updated: dict[str, Any], status: str, error: str | None, *, retryable: bool) -> dict[str, Any]:
    updated.update(
        transcript_downloaded=False,
        transcript_type="missing",
        transcript_path=None,
        transcript_chunks_path=None,
        transcript_status=status,
        transcript_error=error[:2000] if error else None,
        transcript_retryable=retryable,
    )
    return updated


def _transcribe_local_source_asr(
    record: dict[str, Any],
    *,
    video_path: Path,
    transcript_dir: Path,
    ffmpeg: str | Path,
    model_path: Path,
    min_free_bytes: int = 30 * _GIB,
    require_verified_video: bool = True,
) -> dict[str, Any]:
    """Transcribe a local media source, preserving explicit provenance state.

    ``require_verified_video`` is true for the canonical video path. The
    audio-only runner may set it false for a temporary yt-dlp audio source;
    that path never changes the record's media verification fields.
    """
    updated = deepcopy(record)
    video_id = updated.get("video_id")
    source_url = updated.get("url")
    if not isinstance(video_id, str) or not _VIDEO_ID.fullmatch(video_id) or not source_url:
        raise ValueError("record needs a valid video_id and url")
    if min_free_bytes < 0:
        raise ValueError("min_free_bytes must not be negative")

    if updated.get("transcript_downloaded") and updated.get("transcript_type") in {"official", "auto"}:
        return updated
    if updated.get("transcript_downloaded") and updated.get("transcript_type") == "ASR":
        raw = updated.get("transcript_path")
        chunks = updated.get("transcript_chunks_path")
        if raw and chunks and Path(raw).is_file() and Path(chunks).is_file():
            return updated

    if require_verified_video and not updated.get("verified"):
        return _failure(updated, "ASR_VIDEO_UNVERIFIED", "video must pass verification first", retryable=True)
    video_path = Path(video_path)
    canonical = updated.get("canonical_video_path")
    if (
        not video_path.is_file()
        or video_path.stat().st_size <= 0
        or video_path.stem != video_id
        or (
            require_verified_video
            and (not canonical or video_path.resolve() != Path(canonical).resolve())
        )
    ):
        failure_code = "ASR_VIDEO_MISSING" if require_verified_video else "ASR_AUDIO_SOURCE_MISSING"
        failure_message = (
            "canonical local video missing or mismatched"
            if require_verified_video
            else "local audio source missing or mismatched"
        )
        return _failure(updated, failure_code, failure_message, retryable=True)

    model_path = Path(model_path)
    if not model_path.is_dir():
        return _failure(updated, "ASR_MODEL_MISSING", f"local model not found: {model_path}", retryable=True)
    try:
        duration = float(updated.get("duration"))
    except (TypeError, ValueError):
        duration = float("nan")
    if not math.isfinite(duration) or duration <= 0:
        return _failure(updated, "ASR_DURATION_UNKNOWN", "video duration required for audio space check", retryable=True)

    transcript_dir = Path(transcript_dir)
    try:
        transcript_dir.mkdir(parents=True, exist_ok=True)
        free_bytes = shutil.disk_usage(transcript_dir).free
    except OSError as exc:
        return _failure(updated, "ASR_WRITE_FAILED", str(exc), retryable=True)
    estimated_audio = math.ceil(
        min(duration + 30.0, _ASR_WINDOW_SECONDS) * _AUDIO_BYTES_PER_SECOND * 1.5
    )
    if free_bytes - min_free_bytes <= estimated_audio:
        return _failure(
            updated,
            "ASR_INSUFFICIENT_STORAGE",
            f"free={free_bytes}, reserve={min_free_bytes}, estimated_audio={estimated_audio}",
            retryable=True,
        )

    updated["transcript_last_attempt"] = datetime.now(timezone.utc).isoformat()
    if duration >= _ASR_WORKER_MIN_DURATION_SECONDS:
        try:
            all_chunks, zero_duration_words, language, unavailable_segments = _transcribe_worker_batches(
                updated,
                video_path=video_path,
                transcript_dir=transcript_dir,
                ffmpeg=ffmpeg,
                model_path=model_path,
                duration=duration,
            )
        except _AsrWorkerFailure as exc:
            return _failure(updated, exc.status, str(exc), retryable=True)
        except OSError as exc:
            return _failure(updated, "ASR_WRITE_FAILED", str(exc), retryable=True)
    else:
        with tempfile.TemporaryDirectory(prefix=f"{video_id}-asr-", dir=transcript_dir) as scratch:
            model = None
            all_chunks = []
            zero_duration_words = 0
            language = None
            unavailable_segments = []
            for window_index, offset in enumerate(range(0, math.ceil(duration), _ASR_WINDOW_SECONDS)):
                window_duration = (
                    duration + 30.0
                    if duration <= _ASR_WINDOW_SECONDS
                    else min(_ASR_WINDOW_SECONDS, duration - offset)
                )
                audio_path = Path(scratch) / f"audio-{offset:08d}.wav"
                command = [
                    str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(offset), "-i", str(video_path), "-t", str(window_duration),
                    "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio_path),
                ]
                try:
                    result = _run_ffmpeg(command)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    return _failure(updated, "ASR_AUDIO_FAILED", str(exc), retryable=True)
                if result.returncode != 0 or not audio_path.is_file() or audio_path.stat().st_size == 0:
                    return _failure(
                        updated, "ASR_AUDIO_FAILED", result.stderr or "ffmpeg produced no audio", retryable=True
                    )
                try:
                    # oneMKL can retain allocations across many sequential windows
                    # on this host. Restarting the local model bounds that growth.
                    if model is None or window_index % _MODEL_RESTART_EVERY_WINDOWS == 0:
                        if model is not None:
                            del model
                            gc.collect()
                        model = _make_model(model_path)
                    segments, info = model.transcribe(str(audio_path), word_timestamps=True, vad_filter=True)
                    chunks, window_zero_duration_words = _collect_chunks(segments, updated)
                    _offset_chunks(chunks, float(offset))
                    all_chunks.extend(chunks)
                    zero_duration_words += window_zero_duration_words
                    language = language or getattr(info, "language", None)
                except ImportError as exc:
                    return _failure(updated, "ASR_BACKEND_MISSING", str(exc), retryable=True)
                except (AttributeError, TypeError, ValueError) as exc:
                    return _failure(updated, "ASR_INVALID_OUTPUT", str(exc), retryable=True)
                except Exception as exc:  # inference/backend failures vary across devices and versions
                    return _failure(updated, "ASR_FAILED", str(exc), retryable=True)

    if not all_chunks:
        return _failure(updated, "ASR_NO_SPEECH", "model emitted no speech segments", retryable=True)
    timing_warnings = {
        "zero_duration_words": zero_duration_words,
        "unavailable_segment_count": len(unavailable_segments),
    }
    transcript_status = "READY_PARTIAL" if unavailable_segments else "READY"
    payload = {
        "video_id": video_id,
        "language": language,
        "transcript_type": "ASR",
        "backend": "faster-whisper",
        "model_path": str(model_path),
        "timing_warnings": timing_warnings,
        "unavailable_segments": unavailable_segments,
        "chunks": all_chunks,
    }
    raw_payload = {
        "video_id": video_id,
        "language": language,
        "transcript_type": "ASR",
        "backend": "faster-whisper",
        "model_path": str(model_path),
        "unavailable_segments": unavailable_segments,
        "segments": [
            {key: chunk[key] for key in ("start_seconds", "end_seconds", "text", "words")}
            for chunk in all_chunks
        ],
    }
    raw_path = transcript_dir / f"{video_id}.asr.json"
    chunks_path = transcript_dir / f"{video_id}.asr.chunks.json"
    try:
        _atomic_json(raw_path, raw_payload)
        _atomic_json(chunks_path, payload)
    except OSError as exc:
        return _failure(updated, "ASR_WRITE_FAILED", str(exc), retryable=True)
    updated.update(
        transcript_downloaded=True,
        transcript_type="ASR",
        transcript_path=str(raw_path),
        transcript_chunks_path=str(chunks_path),
        transcript_status=transcript_status,
        transcript_error=None,
        transcript_retryable=False,
        transcript_unavailable_segments=unavailable_segments,
    )
    if zero_duration_words or unavailable_segments:
        updated["transcript_quality_status"] = "REVIEW_REQUIRED"
    else:
        updated.pop("transcript_quality_status", None)
    return updated


def transcribe_local_asr(
    record: dict[str, Any],
    *,
    video_path: Path,
    transcript_dir: Path,
    ffmpeg: str | Path,
    model_path: Path,
    min_free_bytes: int = 30 * _GIB,
) -> dict[str, Any]:
    """Return timed ASR from a verified canonical local video."""
    return _transcribe_local_source_asr(
        record,
        video_path=video_path,
        transcript_dir=transcript_dir,
        ffmpeg=ffmpeg,
        model_path=model_path,
        min_free_bytes=min_free_bytes,
        require_verified_video=True,
    )


def transcribe_local_audio_asr(
    record: dict[str, Any],
    *,
    audio_path: Path,
    transcript_dir: Path,
    ffmpeg: str | Path,
    model_path: Path,
    min_free_bytes: int = 30 * _GIB,
) -> dict[str, Any]:
    """Return timed ASR from a temporary audio-only source.

    This is a bounded acquisition fallback for records without usable public
    subtitles. It deliberately leaves ``verified`` and ``canonical_video_path``
    untouched: an audio-only source is transcript evidence, not video archival
    or canonical media verification.
    """
    return _transcribe_local_source_asr(
        record,
        video_path=Path(audio_path),
        transcript_dir=transcript_dir,
        ffmpeg=ffmpeg,
        model_path=model_path,
        min_free_bytes=min_free_bytes,
        require_verified_video=False,
    )
