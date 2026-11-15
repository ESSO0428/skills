"""Build a provenance-linked, transcript-first semantic review for every manifest video.

This is the stage-3 pass.  It does not fetch media, run ASR, call AGY, or inspect
slides.  It records an auditable text review for every readable source and a
terminal gap for every video whose source stage is still unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from channel_distill.workspace import resolve_workspace


_SENTENCE_RE = re.compile(r"[^。！？!?；;\n]{8,}[。！？!?；;]?")
_SIGNAL_RE = re.compile(
    r"model|training|train|test|loss|data|label|metric|objective|gradient|"
    r"attention|transformer|sequence|image|text|audio|agent|learning|"
    r"模型|訓練|訓練|測試|損失|資料|數據|標註|指標|目標|梯度|注意力|"
    r"序列|影像|文字|音訊|代理|學習|分類|生成|預測|嵌入|參數|函數",
    re.IGNORECASE,
)
_VISUAL_RE = re.compile(
    r"slide|figure|table|chart|plot|equation|formula|投影片|簡報|圖表|表格|公式|圖片|架構圖",
    re.IGNORECASE,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _excerpt(text: str, limit: int = 360) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def _sentences(text: str) -> list[str]:
    return [" ".join(m.group(0).split()) for m in _SENTENCE_RE.finditer(text)]


def _load_source_chunks(directory: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        video_id = payload.get("video_id")
        chunks = payload.get("chunks")
        if not isinstance(video_id, str) or not isinstance(chunks, list) or not chunks:
            continue
        result[video_id] = [dict(chunk) for chunk in chunks if isinstance(chunk, dict)]
    return result


def _load_agy_transcripts(
    packets_dir: Path,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    transcripts: dict[str, list[dict[str, Any]]] = {}
    packet_meta: dict[str, dict[str, Any]] = {}
    all_packet_meta: dict[str, dict[str, Any]] = {}
    for packet_path in sorted(packets_dir.glob("*.packet.json")):
        packet = _read_json(packet_path)
        video_id = packet.get("video_id")
        if not isinstance(video_id, str):
            continue
        all_packet_meta[video_id] = {
            "packet_path": str(packet_path),
            "packet_type": packet.get("packet_type"),
            "video_url": packet.get("video_url"),
            "agy_status": packet.get("agy", {}).get("status"),
            "unknown": packet.get("evidence", {}).get("unknown", []),
        }
        if packet.get("packet_type") != "AGY_FULL_VIDEO_EVIDENCE":
            continue
        transcript_path = packet.get("evidence", {}).get("asr_observation", {}).get(
            "transcript_path"
        )
        if not isinstance(video_id, str) or not isinstance(transcript_path, str):
            continue
        path = Path(transcript_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file():
            continue
        transcript = _read_json(path)
        segments = transcript.get("transcript_segments")
        if not isinstance(segments, list) or not segments:
            continue
        chunks = []
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
                continue
            start = segment.get("start_seconds")
            end = segment.get("end_seconds")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                continue
            chunks.append(
                {
                    "chunk_id": f"{video_id}:agy:{index}",
                    "video_id": video_id,
                    "source_url": packet.get("video_url"),
                    "transcript_type": "AGY_SUPPLEMENTAL",
                    "start_seconds": start,
                    "end_seconds": end,
                    "text": segment["text"],
                    "agy_uncertain": bool(segment.get("uncertain", False)),
                }
            )
        if chunks:
            transcripts[video_id] = chunks
            packet_meta[video_id] = {
                "packet_path": str(packet_path),
                "transcript_path": str(path),
                "agy_cli_version": packet.get("agy", {}).get("agy_cli_version"),
                "model": packet.get("agy", {}).get("model"),
                "packet_type": packet.get("packet_type"),
            }
    return transcripts, packet_meta, all_packet_meta


def _ordered(chunks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(chunks, key=lambda c: (float(c.get("start_seconds", 0)), c.get("chunk_id", "")))


def _review_record(
    video_id: str,
    manifest_record: dict[str, Any],
    chunks: list[dict[str, Any]],
    *,
    source_kind: str,
    packet_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ordered = _ordered(chunks)
    texts = [str(chunk.get("text", "")).strip() for chunk in ordered if str(chunk.get("text", "")).strip()]
    joined = "\n".join(texts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    sentence_rows: list[dict[str, Any]] = []
    for chunk in ordered:
        text = str(chunk.get("text", "")).strip()
        for sentence in _sentences(text):
            sentence_rows.append({"chunk": chunk, "text": sentence})
    signal_rows = [row for row in sentence_rows if _SIGNAL_RE.search(row["text"])]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(row: dict[str, Any]) -> None:
        chunk_id = str(row["chunk"].get("chunk_id"))
        key = f"{chunk_id}:{row['text']}"
        if key in seen:
            return
        seen.add(key)
        selected.append(row)

    if sentence_rows:
        add(sentence_rows[0])
        add(sentence_rows[len(sentence_rows) // 2])
        add(sentence_rows[-1])
    for row in signal_rows:
        add(row)
        if len(selected) >= 8:
            break
    visual_candidates = [row for row in sentence_rows if _VISUAL_RE.search(row["text"])]
    claims = [
        {
            "claim_id": f"{video_id}:claim:{index:03d}",
            "claim_text": _excerpt(row["text"]),
            "source_chunk_id": row["chunk"].get("chunk_id"),
            "start_seconds": row["chunk"].get("start_seconds"),
            "end_seconds": row["chunk"].get("end_seconds"),
            "evidence_class": "TRANSCRIPT_OBSERVATION",
        }
        for index, row in enumerate(selected, start=1)
    ]
    title = manifest_record.get("title") or ordered[0].get("title") or video_id
    transcript_types = sorted({str(chunk.get("transcript_type")) for chunk in ordered})
    uncertainties = [
        "This is a transcript-first review; slides and frames were not required or reviewed in stage 3.",
        "The extracted claims are observations linked to transcript chunks, not independently verified research principles.",
    ]
    if any(chunk.get("transcript_type") == "ASR" for chunk in ordered):
        uncertainties.append("ASR wording may contain recognition errors; preserve the original transcript and timestamps.")
    if source_kind == "agy_supplemental":
        uncertainties.append("AGY text is supplemental and cannot replace canonical transcript provenance.")
    if visual_candidates:
        uncertainties.append(
            f"{len(visual_candidates)} text segments mention visual material; defer visual follow-up to stage 4 if a selected claim depends on it."
        )
    limits = [
        "No slide/frame inspection in this stage.",
        "No external fact checking or cross-video synthesis in this stage.",
    ]
    status = (
        "SEMANTIC_REVIEW_COMPLETE_SUPPLEMENTAL"
        if source_kind == "agy_supplemental"
        else "SEMANTIC_REVIEW_COMPLETE_TEXT_ONLY"
    )
    return {
        "schema_version": "semantic-review.v1",
        "stage": 3,
        "stage_name": "semantic_review",
        "video_id": video_id,
        "title": title,
        "status": status,
        "source_kind": source_kind,
        "review_method": "deterministic_transcript_first_v1",
        "transcript_types": transcript_types,
        "topic": {"label": title, "basis": "manifest_title_or_source_title"},
        "coverage": {
            "chunk_count": len(ordered),
            "nonempty_chunk_count": len(texts),
            "character_count": len(joined),
            "start_seconds": ordered[0].get("start_seconds") if ordered else None,
            "end_seconds": ordered[-1].get("end_seconds") if ordered else None,
            "text_sha256": digest,
        },
        "claims": claims,
        "representative_excerpts": [
            {
                "source_chunk_id": row["chunk"].get("chunk_id"),
                "start_seconds": row["chunk"].get("start_seconds"),
                "end_seconds": row["chunk"].get("end_seconds"),
                "text": _excerpt(row["text"]),
            }
            for row in selected[:8]
        ],
        "unknowns": uncertainties,
        "limits": limits,
        "visual_follow_up_candidates": [
            {
                "source_chunk_id": row["chunk"].get("chunk_id"),
                "start_seconds": row["chunk"].get("start_seconds"),
                "end_seconds": row["chunk"].get("end_seconds"),
                "reason": "Transcript mentions visual material; inspect only if the claim is selected for stage 4.",
            }
            for row in visual_candidates[:12]
        ],
        "provenance": {
            "source_chunk_ids": [chunk.get("chunk_id") for chunk in ordered],
            "source_urls": sorted({chunk.get("source_url") for chunk in ordered if chunk.get("source_url")}),
            "manifest_status": manifest_record.get("status"),
            "manifest_verified": bool(manifest_record.get("verified")),
            "supplemental_packet": packet_meta,
        },
    }


def _classify_gap_kind(manifest_record: dict[str, Any], *, is_agy_gap: bool) -> str:
    if is_agy_gap:
        return "AGY_FULL_VIDEO_GAP"
    if manifest_record.get("status") == "DOWNLOAD_FAILED":
        return "DOWNLOAD_FAILED"
    if manifest_record.get("verified") and manifest_record.get("transcript_status") in {
        "ASR_FAILED",
        "ASR_INVALID_OUTPUT",
        "FETCH_FAILED",
        "PARSE_FAILED",
    }:
        return "VERIFIED_MEDIA_TEXT_FAILURE"
    return "SOURCE_UNAVAILABLE"


def _recommendation_for_gap_kind(source_gap_kind: str) -> str:
    recommendations = {
        "AGY_FULL_VIDEO_GAP": "AGY 未完成或未產生可用文字；建議放棄本輪。只有使用者明確批准一次 bounded retry 才再試。",
        "DOWNLOAD_FAILED": "直接下載失敗；建議放棄本輪，不再盲目重試。只有確認新的合法來源或使用者明確批准 bounded retry 才再試。",
        "VERIFIED_MEDIA_TEXT_FAILURE": "影片檔已驗證但文字路徑失敗；建議放棄本輪，不再重跑同一路徑。只有使用者明確批准一次 bounded ASR／替代文字來源才再試。",
        "SOURCE_UNAVAILABLE": "目前沒有可用來源或已達停止門檻；建議放棄本輪。",
    }
    return recommendations.get(source_gap_kind, recommendations["SOURCE_UNAVAILABLE"])


def _blocked_record(
    video_id: str,
    manifest_record: dict[str, Any],
    reason: str,
    *,
    source_gap_kind: str,
    packet_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recommendation = (
        "建議放棄本輪；AGY 工作未完成或未產生可用文字。若仍要嘗試，需使用者明確批准一次 bounded retry。"
        if source_gap_kind == "AGY_FULL_VIDEO_GAP"
        else "建議放棄本輪；目前沒有可用來源或已達停止門檻。若仍要嘗試，需使用者明確批准一次 bounded retry。"
    )
    recommendation = _recommendation_for_gap_kind(source_gap_kind)
    return {
        "schema_version": "semantic-review.v1",
        "stage": 3,
        "stage_name": "semantic_review",
        "video_id": video_id,
        "title": manifest_record.get("title") or video_id,
        "status": "SEMANTIC_REVIEW_BLOCKED_SOURCE_GAP",
        "source_kind": "none",
        "source_gap_kind": source_gap_kind,
        "recommendation": recommendation,
        "review_method": "not_run",
        "claims": [],
        "unknowns": [reason],
        "limits": ["No transcript/source chunks were available; no semantic claim may be inferred."],
        "provenance": {
            "source_chunk_ids": [],
            "source_urls": [manifest_record.get("source_url")] if manifest_record.get("source_url") else [],
            "manifest_status": manifest_record.get("status"),
            "manifest_verified": bool(manifest_record.get("verified")),
            "supplemental_packet": packet_meta,
            "recommendation": recommendation,
        },
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _read_json(args.manifest)
    records = manifest.get("videos", manifest)
    if not isinstance(records, dict):
        raise ValueError("manifest must contain a videos mapping")
    source_chunks = _load_source_chunks(args.source_chunks_dir)
    agy_chunks, agy_meta, agy_all_meta = _load_agy_transcripts(args.agy_packets_dir)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    counts = Counter()
    for video_id in sorted(records):
        record = records[video_id] or {}
        if video_id in source_chunks:
            review = _review_record(video_id, record, source_chunks[video_id], source_kind="canonical_source_chunks")
        elif video_id in agy_chunks:
            review = _review_record(
                video_id,
                record,
                agy_chunks[video_id],
                source_kind="agy_supplemental",
                packet_meta=agy_meta.get(video_id),
            )
        else:
            is_agy_gap = video_id in agy_all_meta
            gap_kind = _classify_gap_kind(record, is_agy_gap=is_agy_gap)
            reason = (
                "AGY produced no usable transcript; retain this video as an AGY coverage gap."
                if is_agy_gap
                else "No canonical source chunks or successful AGY transcript is available; retain this video as a source coverage gap."
            )
            review = _blocked_record(
                video_id,
                record,
                reason,
                source_gap_kind=gap_kind,
                packet_meta=agy_all_meta.get(video_id),
            )
        file_path = output_dir / f"{video_id}.json"
        _write_json(file_path, review)
        counts[review["status"]] += 1
        index_rows.append(
            {
                "video_id": video_id,
                "title": review.get("title"),
                "status": review["status"],
                "source_kind": review["source_kind"],
                "source_gap_kind": review.get("source_gap_kind"),
                "recommendation": review.get("recommendation"),
                "path": str(file_path),
                "claim_count": len(review.get("claims", [])),
                "chunk_count": review.get("coverage", {}).get("chunk_count", 0),
            }
        )
    generated_at = datetime.now(timezone.utc).isoformat()
    index = {
        "schema_version": "semantic-review-index.v1",
        "stage": 3,
        "stage_name": "semantic_review",
        "generated_at": generated_at,
        "method": "deterministic_transcript_first_v1",
        "manifest_count": len(records),
        "source_chunk_video_count": len(source_chunks),
        "agy_text_video_count": len(agy_chunks),
        "agy_packet_count": len(agy_all_meta),
        "counts": dict(sorted(counts.items())),
        "records": index_rows,
        "visual_review_policy": "deferred_to_stage_4_distilly_on_selected_claims_only",
    }
    _write_json(output_dir / "index.json", index)
    gap_rows = [
        row
        for row in index_rows
        if row.get("status") == "SEMANTIC_REVIEW_BLOCKED_SOURCE_GAP"
    ]
    gap_type_recommendations = {
        kind: {
            "count": sum(row.get("source_gap_kind") == kind for row in gap_rows),
            "video_ids": sorted(
                row["video_id"] for row in gap_rows if row.get("source_gap_kind") == kind
            ),
            "recommendation": _recommendation_for_gap_kind(kind),
        }
        for kind in sorted({row.get("source_gap_kind") for row in gap_rows})
    }
    row_by_id = {row["video_id"]: row for row in gap_rows}
    gap_items_by_kind = {}
    for kind, grouped in gap_type_recommendations.items():
        items = []
        for video_id in grouped["video_ids"]:
            record = records.get(video_id) or {}
            row = row_by_id[video_id]
            items.append(
                {
                    "video_id": video_id,
                    "title": row.get("title") or record.get("title") or video_id,
                    "url": record.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                    "manifest_status": record.get("status"),
                    "transcript_status": record.get("transcript_status"),
                    "verified": bool(record.get("verified")),
                    "recommendation": grouped["recommendation"],
                }
            )
        grouped["items"] = items
        gap_items_by_kind[kind] = items
    grouped_ids = [item["video_id"] for items in gap_items_by_kind.values() for item in items]
    gap_ids = [row["video_id"] for row in gap_rows]
    grouped_set = set(grouped_ids)
    gap_set = set(gap_ids)
    consistency = {
        "status": "PASS"
        if len(grouped_ids) == len(grouped_set) == len(gap_set)
        and grouped_set == gap_set
        and sum(grouped["count"] for grouped in gap_type_recommendations.values()) == len(gap_rows)
        else "FAIL",
        "gap_record_count": len(gap_rows),
        "grouped_record_count": len(grouped_ids),
        "unique_grouped_id_count": len(grouped_set),
        "unclassified_gap_ids": sorted(gap_set - grouped_set),
        "orphan_grouped_ids": sorted(grouped_set - gap_set),
        "duplicate_grouped_ids": sorted({video_id for video_id in grouped_ids if grouped_ids.count(video_id) > 1}),
    }
    audit = {
        "schema_version": "semantic-review-audit.v1",
        "generated_at": generated_at,
        "stage": 3,
        "manifest_count": len(records),
        "review_artifact_count": len(index_rows),
        "counts": dict(sorted(counts.items())),
        "blocked_by_gap_kind": dict(
            sorted(
                Counter(
                    row.get("source_gap_kind")
                    for row in index_rows
                    if row.get("status") == "SEMANTIC_REVIEW_BLOCKED_SOURCE_GAP"
                ).items()
            )
        ),
        "gap_type_recommendations": gap_type_recommendations,
        "gap_items_by_kind": gap_items_by_kind,
        "gap_set_consistency": consistency,
        "text_review_complete": counts["SEMANTIC_REVIEW_COMPLETE_TEXT_ONLY"]
        + counts["SEMANTIC_REVIEW_COMPLETE_SUPPLEMENTAL"],
        "source_gaps": counts["SEMANTIC_REVIEW_BLOCKED_SOURCE_GAP"],
        "all_manifest_ids_accounted_for": len(index_rows) == len(records)
        and {row["video_id"] for row in index_rows} == set(records),
        "stage_4_visual_policy": "not_required_for_stage_3_completion",
    }
    _write_json(args.audit, audit)
    stage123 = {
        "schema_version": "stage123-review-audit.v1",
        "generated_at": generated_at,
        "manifest_count": len(records),
        "stage_1_source_acquisition": {
            "SOURCE_READY": audit["text_review_complete"],
            "SOURCE_GAP_RECORDED": audit["source_gaps"],
        },
        "stage_2_evidence_organization": {
            "EVIDENCE_READY": audit["text_review_complete"],
            "GAP_PACKET_OR_SOURCE_GAP_RECORDED": audit["source_gaps"],
        },
        "stage_3_semantic_review": {
            "TEXT_REVIEW_COMPLETE": audit["text_review_complete"],
            "SEMANTIC_REVIEW_BLOCKED_SOURCE_GAP": audit["source_gaps"],
        },
        "stage_4_visual_policy": "deferred; not a prerequisite for stages 1-3",
        "every_manifest_id_has_terminal_stage123_record": audit["all_manifest_ids_accounted_for"],
        "all_stages_1_to_3_have_readable_text": audit["text_review_complete"] == len(records),
        "blocked_by_gap_kind": audit["blocked_by_gap_kind"],
        "gap_type_recommendations": audit["gap_type_recommendations"],
        "gap_items_by_kind": audit["gap_items_by_kind"],
        "gap_set_consistency": audit["gap_set_consistency"],
    }
    _write_json(args.stage123_audit, stage123)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace", type=Path,
        help="workspace root (default: $YTD_WORKSPACE, else cwd); unset paths below default under it",
    )
    parser.add_argument("--manifest", type=Path, help="default: <ws>/data/manifest/videos.json")
    parser.add_argument("--source-chunks-dir", type=Path, help="default: <ws>/data/processing/source_chunks")
    parser.add_argument(
        "--agy-packets-dir", type=Path,
        help="default: <ws>/data/processing/agy-evidence-packets",
    )
    parser.add_argument("--output-dir", type=Path, help="default: <ws>/data/processing/semantic_reviews")
    parser.add_argument("--audit", type=Path, help="default: <ws>/evaluation/semantic-review-audit-latest.json")
    parser.add_argument(
        "--stage123-audit", type=Path,
        help="default: <ws>/evaluation/stage123-review-audit-latest.json",
    )
    args = parser.parse_args()
    ws = resolve_workspace(args.workspace)
    args.manifest = args.manifest or ws.manifest / "videos.json"
    args.source_chunks_dir = args.source_chunks_dir or ws.processing / "source_chunks"
    args.agy_packets_dir = args.agy_packets_dir or ws.processing / "agy-evidence-packets"
    args.output_dir = args.output_dir or ws.processing / "semantic_reviews"
    args.audit = args.audit or ws.evaluation / "semantic-review-audit-latest.json"
    args.stage123_audit = args.stage123_audit or ws.evaluation / "stage123-review-audit-latest.json"
    audit = build(args)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
