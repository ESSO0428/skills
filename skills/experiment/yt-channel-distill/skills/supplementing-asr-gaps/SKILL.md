---
name: supplementing-asr-gaps
description: 針對 manifest 中 ASR_SEGMENT_UNAVAILABLE／READY_PARTIAL 的明確缺口，用 AGY 補一個 bounded evidence packet。
disable-model-invocation: true
---

# Supplementing ASR gaps

這個 skill 只用 AGY 對既有 ASR 的明確缺口補證，輸出 evidence packet，不產生第二份完整 transcript。

**必讀規則：**開始前讀 [`../../RULES.md`](../../RULES.md) 與 [`../../docs/agy-asr-gap-supplement-policy.md`](../../docs/agy-asr-gap-supplement-policy.md)。

**路徑慣例：**`<collection-root>` 是含 `pyproject.toml` 的集合根（從本檔往上兩層），`$W` 是 workspace（`$YTD_WORKSPACE`）。AGY（`agy` CLI）是作者環境專用的選配工具；沒有它時本 skill 不可用。

## Steps

1. 從 manifest 選出一個 bounded `ASR_SEGMENT_UNAVAILABLE`／`READY_PARTIAL` offset，確認不是官方／自動字幕或完整 ASR 可用的影片。
2. 準備影片 ID／URL、缺損 start/end、前後 ASR context、既有 provenance 與 prompt；只要求 AGY 回傳該片段的 audio／visual observation。
3. 封存 raw response、model、prompt hash、時間、來源時間範圍與 packet hash；將 `direct_evidence`、`asr_observation`、`visual_observation`、`project_inference`、`unknown` 分開。
4. 將 packet 交給主代理，與同片既有內容一次整合；不在本 skill 內改 canonical transcript、candidate、knowledge 或 Skill。
5. packet 封存到 `$W/data/processing/evidence_packets/*.packet.json`（含 AGY blocked）後執行 `uv run --project <collection-root> python <collection-root>/skills/llm-wiki/scripts/wiki_sync.py --manifest $W/data/manifest/videos.json --log $W/data/processing/wiki-gate.jsonl --evidence-dir $W/data/processing/evidence_packets`：成功 packet 記為 `RECORD_SUPPLEMENT`，blocked packet 記為 `RECORD_BLOCKED`，交給 Wiki log；`wiki_gate.py --record` 不處理 packet。同一 packet 沒有新證據不重編譯。

## Completion

每個 gap 都有一個可追溯 packet 或明確的不可用結果，且 packet 的時間範圍、原始回應、模型／prompt provenance 與既有 ASR context 完整對齊。

## Boundaries

- 不對非 ASR 影片做一般提取，不把 AGY 當主要提取器，也不以 AGY 靜默取代整支 `ASR_FAILED`。
- 不把 AGY 推測寫成逐字稿；公式、圖表、來源矛盾或升格為正式原則時依 `RULES.md`「高風險敘述」保留 `REVIEW_REQUIRED`。
- 同一 packet 沒有新增證據不得重叫；主代理審查後若仍有疑義，保留 gap／`REVIEW_REQUIRED`。
- gate 只記錄終態，不把 AGY observation 自動升格成 Wiki principle。
