---
name: yt-channel-distill
description: YouTube 頻道蒸餾前處理集合的入口：依階段分流到 inventory、下載與驗證、ASR、缺口補證、AGY fallback、語意審查與 Wiki 的 skill。
disable-model-invocation: true
---

# yt-channel-distill

這是集合入口，安裝時要裝整個目錄；底下的 skill 依賴本目錄的 `pyproject.toml`、`src/channel_distill/` 與 `RULES.md`，不能單獨安裝。

開始前讀 [`RULES.md`](RULES.md)。依目前階段只讀對應的那一個 skill：

| 階段 | skill |
|---|---|
| 不確定從哪開始，或要跑完整條流程 | [`distilling-youtube-channel`](skills/distilling-youtube-channel/SKILL.md) |
| 頻道 inventory、字幕、授權下載、ffprobe 驗證、AGY fallback 規劃 | [`acquiring-video-sources`](skills/acquiring-video-sources/SKILL.md) |
| 已驗證本機影片沒有可用字幕 | [`recovering-asr`](skills/recovering-asr/SKILL.md) |
| 只補 `ASR_SEGMENT_UNAVAILABLE`／`READY_PARTIAL` 的局部缺口 | [`supplementing-asr-gaps`](skills/supplementing-asr-gaps/SKILL.md) |
| 把已驗證來源編成可重建的 Wiki | [`llm-wiki`](skills/llm-wiki/SKILL.md) |

Python 指令一律用 `uv run --project <本目錄> ...`；工作區用 `--workspace` 或 `$YTD_WORKSPACE` 指定。
