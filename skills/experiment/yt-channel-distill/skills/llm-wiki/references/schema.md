# LLM Wiki 輸入與輸出 schema

## Canonical candidates

```json
{
  "schema_version": 1,
  "principles": [{
    "id": "P0-001",
    "domain": "example-topic",
    "principle": "...",
    "decision_rule": "...",
    "evidence_level": "EXPLICIT",
    "applicable_when": "...",
    "limitations": "...",
    "coverage_gap": "...",
    "sources": [{
      "video_id": "...",
      "url": "https://www.youtube.com/watch?v=...",
      "timestamp_start": 12.0,
      "timestamp_end": 30.0,
      "transcript_type": "official|auto|ASR",
      "source_chunk": "video:cue-range"
    }]
  }]
}
```

`uncertainty` 可作為 `limitations` 的既有資料欄位；`coverage_gap` 也可用 `gaps` 表示。每個 principle 至少要有一個完整 source；時間戳必須是非負數且 start 不大於 end。

## Coverage

`coverage.topics.<topic>` 可包含 `course_years`、`ready_transcript_ids`、`source_chunk_count` 與 `coverage_gaps`。缺少 coverage 仍要在 Wiki 顯示缺口，不得省略主題。

## Derived output

- `index.md`：主題與原則入口。
- `topics/<topic>.md`：候選卡、可用逐字稿數、chunks 與 coverage gaps。
- `principles/<id>.md`：原則、適用條件、限制與 provenance links。
- `state.json`：canonical input hash、計數與 schema version。
- `log.md`：只在 input hash 變更時追加編譯紀錄。
