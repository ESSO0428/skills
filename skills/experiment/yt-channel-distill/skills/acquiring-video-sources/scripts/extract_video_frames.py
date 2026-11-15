"""Extract explicitly requested video frames with provenance.

This is a bounded evidence helper, not a sampler: every output frame must be
requested with an explicit timestamp and purpose.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from channel_distill.workspace import find_binary


TOOL_VERSION = "1.2.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return cleaned or "frame"


def build_ffmpeg_command(
    *, video_path: Path, timestamp_seconds: float, output_path: Path, ffmpeg: str = "ffmpeg"
) -> list[str]:
    """Build a single-frame command bounded to one explicit timestamp."""

    return [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{timestamp_seconds:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-y",
        str(output_path),
    ]


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ffmpeg failed").strip()
        raise RuntimeError(f"frame extraction failed ({result.returncode}): {detail}")


def _validated_requests(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not requests:
        raise ValueError("at least one explicit frame request is required")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, request in enumerate(requests, start=1):
        if not isinstance(request, dict):
            raise ValueError(f"frame request {index} must be an object")
        request_id = str(request.get("request_id") or f"frame-{index:04d}")
        if request_id in seen:
            raise ValueError(f"duplicate request_id: {request_id}")
        seen.add(request_id)
        try:
            timestamp = float(request["timestamp_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"request {request_id} needs numeric timestamp_seconds") from exc
        if not isfinite(timestamp) or timestamp < 0:
            raise ValueError(f"request {request_id} has invalid timestamp_seconds")
        purpose = request.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValueError(f"request {request_id} needs a non-empty purpose")
        source_chunk_id = request.get("source_chunk_id")
        claim_id = request.get("claim_id")
        if not (
            isinstance(source_chunk_id, str)
            and source_chunk_id.strip()
            or isinstance(claim_id, str)
            and claim_id.strip()
        ):
            raise ValueError(f"request {request_id} needs source_chunk_id or claim_id")
        validated.append(
            {
                "request_id": request_id,
                "timestamp_seconds": timestamp,
                "purpose": purpose.strip(),
                "source_chunk_id": source_chunk_id.strip() if isinstance(source_chunk_id, str) else None,
                "claim_id": claim_id.strip() if isinstance(claim_id, str) else None,
            }
        )
    return validated


def extract_frames(
    *,
    video_path: Path,
    video_id: str,
    source_url: str | None,
    requests: list[dict[str, Any]],
    output_dir: Path,
    ffmpeg: str = "ffmpeg",
    runner: Callable[[list[str]], None] = _run,
) -> dict[str, Any]:
    """Extract requested frames and return a provenance-bearing manifest."""

    video_path = Path(video_path)
    if not isinstance(video_id, str) or not video_id.strip():
        raise ValueError("video_id must be non-empty")
    if not isinstance(source_url, str) or not source_url.strip():
        raise ValueError("source_url must be non-empty")
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise FileNotFoundError(f"video file is missing or empty: {video_path}")
    validated = _validated_requests(requests)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for index, request in enumerate(validated, start=1):
        filename = f"{index:04d}-{_safe_name(request['request_id'])}.jpg"
        output_path = output_dir / filename
        command = build_ffmpeg_command(
            video_path=video_path,
            timestamp_seconds=request["timestamp_seconds"],
            output_path=output_path,
            ffmpeg=ffmpeg,
        )
        runner(command)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced no frame for {request['request_id']}")
        frame = {
            **request,
            "frame_path": str(output_path),
            "frame_sha256": _sha256(output_path),
            "command_sha256": hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest(),
        }
        frames.append(frame)

    return {
        "schema_version": "visual-evidence.v1",
        "tool": "extract_video_frames",
        "tool_version": TOOL_VERSION,
        "video_id": video_id,
        "video_path": str(video_path),
        "frames": frames,
        "provenance": {
            "source_url": source_url,
            "video_sha256": _sha256(video_path),
            "extraction_scope": "explicit_timestamps_only",
            "frame_count": len(frames),
        },
    }


def _load_requests(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("frames"), list):
        return payload["frames"]
    raise ValueError("requests JSON must be a list or an object with a frames list")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--requests", type=Path, required=True, help="JSON list of explicit timestamp requests")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--ffmpeg", help="ffmpeg binary (default: $YTD_FFMPEG_DIR, then PATH)")
    parser.add_argument("--json", action="store_true", help="print the manifest as JSON")
    args = parser.parse_args()
    try:
        ffmpeg = str(find_binary("ffmpeg", args.ffmpeg))
    except FileNotFoundError as exc:
        parser.error(str(exc))
    manifest = extract_frames(
        video_path=args.video,
        video_id=args.video_id,
        source_url=args.source_url,
        requests=_load_requests(args.requests),
        output_dir=args.output_dir,
        ffmpeg=ffmpeg,
    )
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False))
    else:
        print(args.output_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
