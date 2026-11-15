---
name: acquiring-video-sources
description: 建立官方 YouTube 頻道／playlist inventory、收集 metadata 與字幕、下載已授權影片，並規劃失敗項目的 AGY fallback；不做內容解讀。
disable-model-invocation: true
---

# Acquiring video sources

這個 skill 負責把官方來源變成可驗證、可重建的本機 evidence inputs；後續的 selector、語意正規化與蒸餾屬於下游管線，不是本 skill 或入口 skill `distilling-youtube-channel` 的責任。

**必讀規則：**開始前讀 [`../../RULES.md`](../../RULES.md)，它是來源、授權與 provenance 的單一真實來源。

**路徑慣例：**`<collection-root>` 是含 `pyproject.toml` 的集合根（從本檔往上兩層），`$S` 代表 `<collection-root>/skills/acquiring-video-sources/scripts`，`$W` 代表 `$YTD_WORKSPACE`（workspace 根；也可在每個命令加 `--workspace`）。所有腳本以 `uv run --project <collection-root> python $S/<script>.py ...` 執行；要求 `yt-dlp`、`ffmpeg`、`ffprobe` 在 PATH（或 `$YTD_FFMPEG_DIR`）。

**AGY 分支：**若候選統計含 ASR／字幕失敗或下載失敗，再讀 [`../../docs/agy-fallback-policy.md`](../../docs/agy-fallback-policy.md)。

## Steps

1. 從官方頻道、真實 playlist（與若有的官方清單）建立去重 inventory：`uv run --project <collection-root> python -m channel_distill inventory --workspace $W --channel-id <UC...>`；記錄 video ID、URL、title、playlist 關聯、可見性與時間。
2. 在 `$W/data/processing/` 保存此批固定 `expected_video_ids` 與 run ID；呼叫 `$S/acquire_video_batch.py plan`，先查 manifest、磁碟餘量與整批安全預估，再向使用者報告預估下載量、保留空間與風險。
3. 使用者確認後才呼叫同一腳本的 `run --execute`。它依 frozen ID 逐片下載並以 `ffprobe` 驗證；成功後收集官方／自動時間碼字幕，無可用字幕時對已驗證本機影片跑一次 local ASR。每片立即 checkpoint；直接下載失敗及 ASR_FAILED 不自動重試，留下 AGY／ASR recovery 狀態。`ASR_FAILED` 是文字路徑失敗，不是媒體已證實壞軌；字幕原始時間碼、純文字稿及來源型別分別保存。
4. 每批 acquisition 完成後呼叫 `$S/video_batch_report.py --stage acquisition`。核對預期數、已驗證本機影片、直接失敗、pending 與逐字稿狀態及 ID 清單；若不自洽先停下排錯。
5. 對全片 `ASR_FAILED`、沒有可用字幕、明確的媒體完整性錯誤及直接影片抓取失敗，agent 主動執行 `--stage agy-plan` 並回報分類與 count／ID；`ASR_FAILED`／`AGY_FULL_VIDEO_GAP` 不得直接改稱壞軌，候選判定與排除條件依 [`../../RULES.md`](../../RULES.md)。
6. AGY 用量評估、報表與 job preparation 由 agent 完成：先執行 CLI 處理的 `agy -p /usage` 讀取目前 quota，再以相符 pilot 估算單片／批次用量。能力評估時必須並列兩種評估方案，由使用者選擇：候選集分層試跑、或已下載影片正向控制；各自能回答的問題不同，停損／樣本規則依 [`../../docs/agy-fallback-policy.md`](../../docs/agy-fallback-policy.md)。只有取得方案、影片數／ID 與用量上限核准後才準備 job；之後交付使用者可直接貼上的命令，使用者執行批次，agent 不代跑。
7. 使用者回報大量 AGY 命令結束後，agent 記錄 post-run 用量、產生 final report 並核對 ID／修復狀態；若尚未執行，只交付命令後停止，不輪巡。之後 agent 對 manifest 執行 [`../llm-wiki/scripts/wiki_gate.py`](../llm-wiki/scripts/wiki_gate.py)（參數見 [llm-wiki](../llm-wiki/SKILL.md)）；只有回報 `COMPILE`、`COMPILE_WITH_GAPS` 或 `RECORD_BLOCKED` 時才交給 llm-wiki 的 compiler／log。

## Optional visual evidence

當語意審查明確指出某個主張需要簡報、公式、表格或圖表才能安全判斷時，使用 [`scripts/extract_video_frames.py`](scripts/extract_video_frames.py) 依明確 timestamp request 抽取少量影格。每個 request 必須包含 purpose 與可回查的 source chunk／claim；輸出的 `visual-evidence.v1` manifest 保存 video hash、source URL、時間戳、影格 hash 與 command hash。這是選擇性補證，不是全片抽樣；流程見 [`../../docs/selective-review-workflow.md`](../../docs/selective-review-workflow.md)。

工具會拒絕缺少非空 `source_url`、`purpose`，或同時缺少 `source_chunk_id`／`claim_id` 的 request，不會以 `unspecified`、無 URL 或無 locator 的影格繼續產生 evidence。

```bash
uv run --project <collection-root> python $S/extract_video_frames.py   --video $W/data/videos/<video-id>.mp4   --video-id <video-id>   --source-url https://www.youtube.com/watch?v=<video-id>   --requests $W/data/processing/visual-frame-requests/<video-id>.json   --output-dir $W/data/processing/visual-evidence/<video-id>   --output-manifest $W/data/processing/visual-evidence/<video-id>.json
```

## Batch report commands

對同一 frozen batch 使用同一份 `expected_video_ids` 與 ledger。依 `RULES.md` 的分工，agent 主動完成 preflight、報表、budget、job preparation 與收尾統計；使用者只在 terminal 執行大量 `run --execute` 命令。報表唯讀，不會啟動下載或 AGY：

```bash
R="uv run --project <collection-root> python"
$R $S/acquire_video_batch.py freeze --workspace $W --ids-file $W/data/processing/selected-video-ids.json --run-id batch-a
$R $S/acquire_video_batch.py plan --workspace $W
$R $S/acquire_video_batch.py run --execute --workspace $W
# User-authorized, one-pass retry for frozen DOWNLOAD_FAILED IDs only; review plan first.
$R $S/acquire_video_batch.py plan --retry-download-failures --workspace $W --batch $W/data/processing/retry-download-failures.json
$R $S/acquire_video_batch.py run --execute --retry-download-failures --workspace $W --batch $W/data/processing/retry-download-failures.json --report $W/data/processing/retry-download-failures-report.json
$R $S/video_batch_report.py --stage acquisition --manifest $W/data/manifest/videos.json --batch $W/data/processing/current-batch.json
$R $S/video_batch_report.py --stage agy-plan --manifest $W/data/manifest/videos.json --batch $W/data/processing/current-batch.json --json --output $W/data/processing/agy-plan.json
# Agent-only, read-only quota query; handled by the AGY CLI, not sent as a model prompt.
agy -p /usage
$R $S/agy_batch_jobs.py budget --workspace $W --report-json $W/data/processing/agy-plan.json --manifest $W/data/manifest/videos.json --batch $W/data/processing/current-batch.json --usage-snapshot $W/data/processing/agy-usage-snapshot.json --model <agy-model>
$R $S/agy_batch_jobs.py prepare --workspace $W --report-json $W/data/processing/agy-plan.json --manifest $W/data/manifest/videos.json --batch $W/data/processing/current-batch.json --approved-ids-file $W/data/processing/approved-agy-ids.json --usage-snapshot $W/data/processing/agy-usage-snapshot.json --output-dir $W/data/processing/agy-jobs/batch-a --model <agy-model>
# User executes this bulk command only after choosing/approving the IDs and limit:
$R $S/agy_batch_jobs.py run --jobs $W/data/processing/agy-jobs/batch-a/jobs.json --batch $W/data/processing/current-batch.json --manifest $W/data/manifest/videos.json --execute
# Add --yolo only when the user explicitly requests bypassing AGY permission prompts.
# After the user reports completion, the agent records usage and reconciles the final report:
$R $S/agy_batch_jobs.py record-usage-after --jobs $W/data/processing/agy-jobs/batch-a/jobs.json --batch $W/data/processing/current-batch.json --usage-snapshot $W/data/processing/agy-usage-after.json
$R $S/video_batch_report.py --stage final --manifest $W/data/manifest/videos.json --batch $W/data/processing/current-batch.json
```

`freeze` 只接受 `{"video_ids": ["id1", "id2"]}` 或 JSON ID list，並拒絕覆寫既有 ledger；`plan` 為唯讀。空間不足時 acquisition `run` 在任何下載前停止，且只有明確帶 `--execute` 才會啟動。AGY budget／quota gate 與用量快照規格依 `RULES.md` 及 [`docs/agy-fallback-policy.md`](../../docs/agy-fallback-policy.md)：報表、估算及所需 JSON 由 agent 準備，不列為使用者的 terminal 工作。

```json
{
  "checked_at": "<ISO-8601 time>",
  "agy_cli_version": "<version>",
  "quota_model_family": "Gemini Models",
  "five_hour_remaining_percent": 72,
  "weekly_remaining_percent": 41,
  "five_hour_reset_at": "<ISO-8601 time>",
  "weekly_reset_at": "<ISO-8601 time>",
  "pilot_video_id": "example12345",
  "pilot_model": "<agy-model>",
  "pilot_source_mode": "local_file",
  "pilot_duration_seconds": 2520,
  "pilot_five_hour_used_percent": 8,
  "pilot_weekly_used_percent": 1.2,
  "safety_multiplier": 1.5
}
```

這是根據 pilot 單片實測、影片時長縮放、安全係數及當下 `/usage` 配額快照所得的保守建議，不是用量保證；pilot model 與來源模式必須吻合，單一 job batch 不混用 local file／remote URL 模式。使用者選定 ID 並核准預算後，agent 準備 job 並提供 `run --execute` 命令，由使用者在 terminal 啟動大量批次；只有使用者明確要求跳過 AGY 權限提示時才帶 `--yolo`。腳本等待整批命令結束，不輪巡；中斷後只處理仍為 `PREPARED` 的 job。完成後 agent 依可觀測用量刷新並以 `record-usage-after` 記錄前後差值（若視窗重置或無法讀取，保留為未知，不推算）。AGY 結果先是 `OUTPUT_CAPTURED_REVIEW_REQUIRED`，需 agent 審核並更新 ledger 後才能由 final report 計入修復。

## AGY quota directions

For every AGY quota assessment, read `RULES.md` and `docs/agy-foreground-execution.md`, then present three user-selectable directions: Conservative, Aggressive, and Full burn. The user-facing table must contain these columns: `方案`, `單片估算`, `<N> 部總量` (N = the actual remaining count), `每五小時窗口`, `建議每週`, `當週理論上限（最少／最多）`, and `預估完成（最少／最多）`. Put the minimum value first and the maximum conservative value second in each paired cell. Calculate the values from the latest `/usage` snapshot and measured pilot range; for Full burn, prefer a completed-batch measurement over an older pilot high-water estimate. The selected direction controls `agy_zero_shot_batch.py --limit` and `--reserve-percent`.

Use `$S/agy_zero_shot_batch.py` (default `--schema` is the collection's `schemas/agy-zero-shot-schema.json`; it parses the output of `agy -p /usage` and stops with an explicit error if that format changes) for user-approved foreground zero-shot waves. It records raw AGY output, normalized transcript JSON, stderr, provenance, and usage. It skips attempted IDs and stops only at the configured reserve or a hard acquisition failure. Each `summary.json` distinguishes `wave_complete` from `global_remaining_unattempted_count`; if a requested wave is not fully processed, the script exits non-zero so a partial wave cannot be mistaken for completion. Full burn uses `--reserve-percent 0`, retaining only the hard zero-quota guard.

After the user selects a direction, respond with an execution schedule for that selected direction: split the remaining unique IDs into weekly groups and five-hour waves, state when a quota reset is required, and provide copy-paste commands for each wave. Set `--limit` to the wave size and `--reserve-percent` to the selected direction's reserve (zero for Full burn). State that the commands use the maximum (slowest conservative) estimate; actual completion may be faster. Do not ask the user to choose again or return only the estimate table.

## Completion

每批有固定 run scope；影片、完整時間碼字幕、無時間碼稿與 AGY observation 的狀態及 provenance 可區分。acquisition／AGY 統計由內建報表輸出 count 和 ID，集合核對通過；失敗及用量限制清楚列出。

## Boundaries

- 本機 `agy` CLI 與 faster-whisper 是作者環境專用的選配工具；沒有它們時，AGY 與本機 ASR 分支不可用，其餘流程照常。
- 不批次下載整個頻道，不繞過 YouTube 限制，不把 unlisted 課綱連結冒充 playlist 成員。
- acquisition、報表、用量估算、job preparation 與收尾統計依 `RULES.md` 分工；使用者只在 terminal 啟動大量 AGY 批次。agent 不猜測 quota，也不代替使用者啟動大量批次。
- 不修改 canonical transcript、candidate、knowledge 或 Skill 內容；只產生來源與證據輸入。
- bounded ASR checkpoint 恢復／局部缺損修復交給 `recovering-asr`；本 acquisition runner 只對尚無可用字幕的已驗證影片啟動首次 ASR。
- Wiki gate 只讀 record；不在來源取得階段改寫 Wiki 卡片或候選原則。
