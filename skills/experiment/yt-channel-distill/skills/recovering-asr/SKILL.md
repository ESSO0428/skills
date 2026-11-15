---
name: recovering-asr
description: 對沒有可用字幕、已驗證的本機影片執行可續跑、可追溯的本機 ASR，並記錄 READY／READY_PARTIAL／ASR_FAILED 狀態。
disable-model-invocation: true
---

# Recovering ASR

## Status semantics and retry boundary

`ASR_FAILED`, `FETCH_FAILED`, and `AGY_FULL_VIDEO_GAP` describe a failed or unavailable text path; they do not prove that the media track is physically damaged. Use `ffprobe`/decoder errors or explicit damaged or inaccessible ranges for a media-integrity claim. After the configured checkpoint/window attempts are exhausted, leave the gap terminal for this run and do not launch another full-video rescue merely to make stage 3 look complete. The semantic review step must record `SEMANTIC_REVIEW_BLOCKED_SOURCE_GAP` when no readable text exists.

這個 skill 將已驗證的本機媒體轉成可續跑、可追溯的 ASR 證據；它不負責內容結論。

**必讀規則：**開始前讀 [`../../RULES.md`](../../RULES.md) 與 [`../../docs/asr-recovery-policy.md`](../../docs/asr-recovery-policy.md)。

**路徑慣例：**`<collection-root>` 是含 `pyproject.toml` 的集合根（從本檔往上兩層），`$W` 是 workspace（`$YTD_WORKSPACE`）。本機 ASR 需要選配套件 `faster-whisper`（`uv run --project <collection-root> --extra asr ...`）、PATH 上的 `ffmpeg`／`ffprobe`，以及預先放在 `$W/data/models/<model-name>` 的本機模型（`local_files_only`，不會自動下載）。這些是作者環境的選配項目；缺少時本 skill 不可用。

## Steps

1. 讀 manifest，確認官方／自動字幕不可用、媒體已通過 `ffprobe`，並鎖定影片 ID、duration 與輸出路徑。
2. 啟動可續跑的 checkpoint 子程序：`uv run --project <collection-root> --extra asr python -m channel_distill transcribe --workspace $W --video-id <id> [--model-name <dir>] [--postprocess]`（`--model-path` 可直接指定模型目錄）；讓程式切窗、記錄 offset、原子寫入 `READY` 批次與保留 stderr／stdout。
3. 只在 allocator 記憶體錯誤時對單窗口退避；每個窗口自動嘗試兩次，超過次數寫入 `ASR_SEGMENT_UNAVAILABLE`，其餘窗口繼續。
4. 命令結束後一次讀取最終 transcript、checkpoint、不可用片段與 manifest，將整支影片標為 `READY`、`READY_PARTIAL` 或 `ASR_FAILED`。
5. 對最終 record 執行 `uv run --project <collection-root> python <collection-root>/skills/llm-wiki/scripts/wiki_gate.py --record <record.json> [--log <gate.jsonl>]`（或 `transcribe --postprocess --sync-wiki`）；依 `COMPILE`／`COMPILE_WITH_GAPS`／`RECORD_BLOCKED` 只觸發一次對應的 Wiki 更新或 blocked event。

## Completion

輸出包含可重建的時間碼 transcript、checkpoint／錯誤紀錄、片段級狀態與 manifest 更新；`READY_PARTIAL` 必須列出所有缺損 offset，`ASR_FAILED` 必須說明整批停止原因。

## Boundaries

- 字幕可用時不跑 ASR；不由主代理逐片段重試、輪詢或手動判斷是否跳過。
- 換 workspace 路徑會使既有 checkpoint 簽章失效而重跑，續跑請留在同一 workspace。
- 不把 ASR observation 直接寫入 canonical candidate、knowledge 或 Skill；只保留可回查的 evidence handoff，供下游 selector／蒸餾管線在來源封存後消費。
- `ASR_SEGMENT_UNAVAILABLE` 才能觸發 `supplementing-asr-gaps`；整支 `ASR_FAILED` 不得被 AGY 靜默取代。
- gate 判定後不由主代理逐片段重複編譯；Wiki 只保留 canonical gap 狀態。
