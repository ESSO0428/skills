# Experiment（實驗）

這裡放實驗性的 skills 集合：不保證穩定，可能改名、搬出這個 repo 或直接刪除。目前只有一個集合 [`yt-channel-distill`](./yt-channel-distill/README.md)（YouTube 頻道蒸餾前處理），只在單一頻道上實測過；需要安裝整個集合，單裝一個 skill 無法執行。

## 明確呼叫（User-invoked）

只能在明確呼叫時使用。

- **[distilling-youtube-channel](./yt-channel-distill/skills/distilling-youtube-channel/SKILL.md)** — 入口：把 YouTube 頻道從 inventory 一路帶到有 provenance 的蒸餾前證據。
- **[acquiring-video-sources](./yt-channel-distill/skills/acquiring-video-sources/SKILL.md)** — 建立頻道 inventory、收集字幕、下載已授權影片，並規劃失敗項目的 AGY fallback。
- **[recovering-asr](./yt-channel-distill/skills/recovering-asr/SKILL.md)** — 對沒有可用字幕的已驗證本機影片執行可續跑的本機 ASR。
- **[supplementing-asr-gaps](./yt-channel-distill/skills/supplementing-asr-gaps/SKILL.md)** — 用 AGY 對 ASR 明確缺口補一個 bounded evidence packet。
- **[llm-wiki](./yt-channel-distill/skills/llm-wiki/SKILL.md)** — 把已驗證來源編譯成可重建、保留 provenance 的 Markdown Wiki。
