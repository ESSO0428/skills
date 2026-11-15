"""Parse timed subtitle cues while retaining their source provenance."""

from __future__ import annotations

import html
import re


_TIMING = re.compile(
    r"(?m)^(?P<start>\d{2}:\d{2}(?::\d{2})?[.,]\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}(?::\d{2})?[.,]\d{3})(?:[^\n]*)$"
)


def _seconds(timestamp: str) -> float:
    parts = timestamp.replace(",", ".").split(":")
    value = 0.0
    for part in parts:
        value = value * 60 + float(part)
    return value


def parse_subtitles(
    content: str,
    *,
    format: str,
    video_id: str,
    title: str,
    source_url: str,
    transcript_type: str,
) -> list[dict]:
    """Return timestamped subtitle chunks with their video provenance."""
    normalized_format = format.lower().lstrip(".")
    if normalized_format not in {"vtt", "srt"}:
        raise ValueError(f"unsupported subtitle format: {format}")
    if transcript_type not in {"official", "auto", "ASR"}:
        raise ValueError(f"unsupported transcript_type: {transcript_type}")
    chunks: list[dict] = []
    previous_words: list[str] = []
    previous_text = ""
    previous_end = -1.0
    blocks = re.split(r"\r?\n\s*\r?\n", content)
    for block in blocks:
        if normalized_format == "vtt" and re.match(r"^(?:NOTE\b|STYLE\b|REGION\b)", block):
            continue
        match = _TIMING.search(block)
        if match is None:
            continue
        lines = block[match.end() :].splitlines()
        cleaned_lines: list[str] = []
        for line in lines:
            cleaned = html.unescape(re.sub(r"<[^>]*>", "", line))
            cleaned = " ".join(cleaned.split())
            if cleaned and (
                normalized_format != "vtt"
                or not cleaned_lines
                or cleaned != cleaned_lines[-1]
            ):
                cleaned_lines.append(cleaned)
        cue_text = " ".join(cleaned_lines)
        if not cue_text:
            continue
        start = _seconds(match.group("start"))
        end = _seconds(match.group("end"))
        if end <= start:
            raise ValueError(f"invalid cue timing: {start} --> {end}")
        words = cue_text.split()
        if normalized_format == "vtt" and start <= previous_end + 0.25:
            if re.search(r"[\u3400-\u9fff]", previous_text + cue_text):
                for overlap in range(min(len(previous_text), len(cue_text)), 0, -1):
                    if previous_text[-overlap:] == cue_text[:overlap]:
                        words = cue_text[overlap:].split()
                        break
            else:
                for overlap in range(min(len(previous_words), len(words)), 0, -1):
                    if previous_words[-overlap:] == words[:overlap]:
                        words = words[overlap:]
                        break
        previous_words = cue_text.split()
        previous_text = cue_text
        previous_end = end
        if not words:
            if chunks:
                chunks[-1]["end_seconds"] = max(chunks[-1]["end_seconds"], end)
            continue
        chunks.append(
            {
                "start_seconds": start,
                "end_seconds": end,
                "text": " ".join(words),
                "video_id": video_id,
                "title": title,
                "source_url": source_url,
                "transcript_type": transcript_type,
            }
        )
    return chunks
