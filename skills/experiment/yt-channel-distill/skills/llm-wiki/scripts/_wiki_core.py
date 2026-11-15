"""Standalone, provenance-preserving compiler and validator for the LLM Wiki skill."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any


class WikiError(ValueError):
    """Raised when canonical Wiki inputs or derived output are invalid."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WikiError(f"cannot read JSON input {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise WikiError(f"expected JSON object: {path}")
    return payload


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
        suffix=".tmp", delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    temporary.replace(path)


def _input_digest(candidates_path: Path, coverage_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (candidates_path, coverage_path):
        data = path.read_bytes()
        digest.update(str(path.name).encode("utf-8"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _timestamp_link(source: dict[str, Any]) -> str:
    try:
        start = float(source["timestamp_start"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WikiError("source is missing numeric timestamp_start") from exc
    if start < 0:
        raise WikiError("timestamp_start must be non-negative")
    return f"{source['url']}&t={int(start)}"


def _validate_source(source: Any, *, principle_id: str) -> None:
    if not isinstance(source, dict):
        raise WikiError(f"{principle_id}: every source must be an object")
    required = ("video_id", "url", "timestamp_start", "timestamp_end", "transcript_type", "source_chunk")
    missing = [field for field in required if not source.get(field) and source.get(field) != 0]
    if missing:
        raise WikiError(f"{principle_id}: source missing {', '.join(missing)}")
    try:
        start = float(source["timestamp_start"])
        end = float(source["timestamp_end"])
    except (TypeError, ValueError) as exc:
        raise WikiError(f"{principle_id}: source timestamps must be numeric") from exc
    if start < 0 or end < start:
        raise WikiError(f"{principle_id}: invalid source timestamp range")
    if not str(source["url"]).startswith(("http://", "https://")):
        raise WikiError(f"{principle_id}: source URL must be absolute")


def _validate_inputs(candidates: dict[str, Any], coverage: dict[str, Any]) -> list[dict[str, Any]]:
    principles = candidates.get("principles")
    topics = coverage.get("topics", {})
    if not isinstance(principles, list) or not isinstance(topics, dict):
        raise WikiError("candidates.principles and coverage.topics must be arrays/objects")
    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    for principle in principles:
        if not isinstance(principle, dict):
            raise WikiError("each principle must be an object")
        principle_id = str(principle.get("id") or "")
        domain = str(principle.get("domain") or "")
        if not principle_id or not domain or principle_id in seen:
            raise WikiError("each principle needs a unique id and non-empty domain")
        if not principle.get("principle") or not principle.get("decision_rule"):
            raise WikiError(f"{principle_id}: principle and decision_rule are required")
        sources = principle.get("sources")
        if not isinstance(sources, list) or not sources:
            raise WikiError(f"{principle_id}: at least one provenance source is required")
        for source in sources:
            _validate_source(source, principle_id=principle_id)
        seen.add(principle_id)
        valid.append(principle)
    return valid


def _render_principle(principle: dict[str, Any]) -> str:
    applicable = principle.get("applicable_when") or "未明確記錄；回到來源 chunk 確認適用條件。"
    limitations = principle.get("limitations") or principle.get("uncertainty") or "未明確記錄。"
    gaps = principle.get("coverage_gap") or principle.get("gaps") or "未在此 card 單獨記錄；請查看 topic coverage。"
    lines = [
        f"# {principle['id']}",
        "",
        f"- 主題：[[../topics/{principle['domain']}]]",
        f"- 證據等級：`{principle.get('evidence_level', 'UNKNOWN')}`",
        "- 狀態：候選導航卡；不得取代 canonical transcript、source chunks 或影片。",
        "",
        "## 原則",
        "",
        str(principle["principle"]),
        "",
        "## 適用條件",
        "",
        str(applicable),
        "",
        "## 決策規則",
        "",
        str(principle["decision_rule"]),
        "",
        "## 限制與缺口",
        "",
        str(limitations),
        "",
        "### Coverage gap",
        "",
        str(gaps),
        "",
        "## 可回溯證據",
        "",
    ]
    for source in principle.get("sources", []):
        lines.append(
            f"- [{source.get('video_id')}｜{source.get('title') or '未命名影片'}]({_timestamp_link(source)}) "
            f"`{float(source['timestamp_start']):.2f}s–{float(source['timestamp_end']):.2f}s`; "
            f"`{source['transcript_type']}`; chunk `{source['source_chunk']}`"
        )
    return "\n".join(lines) + "\n"


def _render_topic(topic: str, principles: list[dict[str, Any]], coverage: dict[str, Any] | None) -> str:
    lines = [f"# {topic}", "", "## 候選原則", ""]
    if principles:
        lines.extend(
            f"- [[../principles/{p['id']}]] — {p['principle']} (`{p.get('evidence_level', 'UNKNOWN')}`)"
            for p in principles
        )
    else:
        lines.append("- 尚無候選原則；不代表原始語料沒有相關內容。")
    lines.extend(["", "## Coverage", ""])
    if not coverage:
        lines.append("- 尚無 coverage record；需保留為缺口。")
    else:
        years = ", ".join(str(year) for year in coverage.get("course_years", [])) or "未記錄"
        ready = len(coverage.get("ready_transcript_ids", []))
        chunks = coverage.get("source_chunk_count", 0)
        lines.extend([
            f"- 課程年份：{years}",
            f"- 可用逐字稿影片：{ready}",
            f"- source chunks：{chunks}",
        ])
        gaps = coverage.get("coverage_gaps", [])
        lines.append("- coverage gaps：" + ("、".join(f"`{gap}`" for gap in gaps) if gaps else "無已記錄缺口（不表示語意完整）。"))
    lines.extend([
        "",
        "## 使用邊界",
        "",
        "本頁只是低成本導航；採納任何結論前，必須回到原始 source chunk、時間戳與 manifest。",
        "",
    ])
    return "\n".join(lines)


def _render_index(topics: list[str], by_topic: dict[str, list[dict[str, Any]]], principles: list[dict[str, Any]]) -> str:
    lines = [
        "# ML Research Advisor — LLM Wiki 索引",
        "",
        "> 此目錄是可重建的 Markdown 導航層；canonical 資料在 manifest、逐字稿、source chunks 與已驗證影片。",
        "",
        "## 主題",
        "",
    ]
    lines.extend(f"- [[topics/{topic}]] — {len(by_topic.get(topic, []))} 個候選原則" for topic in topics)
    lines.extend(["", "## 原則", ""])
    lines.extend(f"- [[principles/{p['id']}]] — {p['principle']}" for p in sorted(principles, key=lambda item: str(item["id"])))
    return "\n".join(lines) + "\n"


def _render_readme() -> str:
    return (
        "# Wiki 使用邊界\n\n"
        "本 Wiki 由 canonical candidates 與 coverage facts 編譯，僅供導航與檢索。"
        "每張卡保留 video ID、URL、時間戳、逐字稿型別與 source chunk；候選卡不是完整課程內容，也不是最終 Skill。\n"
    )


def compile_wiki(candidates_path: Path, coverage_path: Path, wiki_dir: Path) -> dict[str, Any]:
    """Compile derived pages; source JSON is read-only and never rewritten."""
    candidates_path = Path(candidates_path)
    coverage_path = Path(coverage_path)
    candidates = _load_json(candidates_path)
    coverage = _load_json(coverage_path)
    principles = _validate_inputs(candidates, coverage)
    coverage_topics = coverage.get("topics", {})
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for principle in principles:
        by_topic[str(principle["domain"])].append(principle)
    topics = sorted(set(by_topic) | set(coverage_topics))
    wiki_dir = Path(wiki_dir)
    for principle in principles:
        _write_atomic(wiki_dir / "principles" / f"{principle['id']}.md", _render_principle(principle))
    for topic in topics:
        _write_atomic(wiki_dir / "topics" / f"{topic}.md", _render_topic(topic, by_topic.get(topic, []), coverage_topics.get(topic)))
    _write_atomic(wiki_dir / "index.md", _render_index(topics, by_topic, principles))
    _write_atomic(wiki_dir / "README.md", _render_readme())

    digest = _input_digest(candidates_path, coverage_path)
    state_path = wiki_dir / "state.json"
    old_state = _load_json(state_path) if state_path.exists() else {}
    changed = old_state.get("input_sha256") != digest
    state = {
        "schema_version": 1,
        "input_sha256": digest,
        "principle_count": len(principles),
        "topic_count": len(topics),
    }
    _write_atomic(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        _write_atomic(log_path, "# 編譯紀錄\n\n")
    if changed:
        with log_path.open("a", encoding="utf-8") as log:
            now = datetime.now(timezone.utc).date().isoformat()
            log.write(
                f"## [{now}] compile | input {digest[:12]}\n"
                f"- 原則：{len(principles)}；主題：{len(topics)}；canonical 輸入未修改。\n\n"
            )
    return {"principle_count": len(principles), "topic_count": len(topics), "changed": changed, "input_sha256": digest}


def validate_wiki(candidates_path: Path, coverage_path: Path, wiki_dir: Path) -> dict[str, Any]:
    """Validate source chains and compare deterministic derived pages without writing output."""
    candidates = _load_json(Path(candidates_path))
    coverage = _load_json(Path(coverage_path))
    principles = _validate_inputs(candidates, coverage)
    wiki_dir = Path(wiki_dir)
    required = [wiki_dir / "index.md", wiki_dir / "README.md", wiki_dir / "log.md", wiki_dir / "state.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise WikiError("missing Wiki outputs: " + ", ".join(missing))
    with tempfile.TemporaryDirectory() as temporary:
        expected = compile_wiki(Path(candidates_path), Path(coverage_path), Path(temporary) / "wiki")
        generated = Path(temporary) / "wiki"
        files = [generated / "index.md", generated / "README.md"]
        files.extend(generated / "principles" / f"{p['id']}.md" for p in principles)
        topics = sorted(set(str(p["domain"]) for p in principles) | set(coverage.get("topics", {})))
        files.extend(generated / "topics" / f"{topic}.md" for topic in topics)
        mismatches = []
        for expected_path in files:
            actual_path = wiki_dir / expected_path.relative_to(generated)
            if not actual_path.is_file() or actual_path.read_text(encoding="utf-8") != expected_path.read_text(encoding="utf-8"):
                mismatches.append(str(actual_path))
    if mismatches:
        raise WikiError("derived pages differ from canonical inputs: " + ", ".join(mismatches))
    state = _load_json(wiki_dir / "state.json")
    digest = _input_digest(Path(candidates_path), Path(coverage_path))
    if state.get("input_sha256") != digest:
        raise WikiError("state.json input hash does not match canonical inputs")
    return {"status": "PASS", "principle_count": len(principles), "topic_count": len(set(str(p["domain"]) for p in principles) | set(coverage.get("topics", {}))), "input_sha256": digest, "mismatches": []}
