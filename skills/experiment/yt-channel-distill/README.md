# yt-channel-distill

> [!WARNING]
> 實驗性集合，不保證穩定。目前只在**一個頻道**上實測過；AGY 與本機 ASR 分支綁定作者環境，換環境可能需要自行調整。

把一個 YouTube 頻道處理成「有 provenance 的蒸餾前證據」：inventory、授權下載、字幕與本機 ASR、AGY 補證、source chunks、語意審查、Wiki 與 coverage 報告。蒸餾本身不在這裡；這裡產出的是下游可以消費、可回查的證據與缺口清單。

## 內含 skills

五個 skills 全部是 user-invoked（明確呼叫才使用），因為下載、長時間 ASR、AGY 配額與磁碟寫入的誤觸成本高。

- **[distilling-youtube-channel](./skills/distilling-youtube-channel/SKILL.md)** — 入口：8 個階段，從頻道 inventory 到證據與 coverage。
- **[acquiring-video-sources](./skills/acquiring-video-sources/SKILL.md)** — inventory、授權下載與 `ffprobe` 驗證、字幕、AGY fallback 規劃。
- **[recovering-asr](./skills/recovering-asr/SKILL.md)** — 對沒有字幕的已驗證本機影片跑可續跑的本機 ASR。
- **[supplementing-asr-gaps](./skills/supplementing-asr-gaps/SKILL.md)** — 用 AGY 補 ASR 缺口的 bounded evidence packet。
- **[llm-wiki](./skills/llm-wiki/SKILL.md)** — 把已驗證來源編譯成可重建的 Markdown Wiki。

規則集中在 [`RULES.md`](./RULES.md)（授權、磁碟、AGY、ASR 停止門檻、provenance），細節在 [`docs/`](./docs/)。

## 安裝

安裝**整個集合**；只裝單一 skill 不能執行，因為 skills 的腳本 import 集合根 `src/channel_distill/` 的 Python 套件，並互相引用 `RULES.md`、`docs/` 與 `llm-wiki` 的腳本。

```bash
npx skills@latest add esso0428/skills        # 或 Claude plugin：/plugin install esso0428-skills@esso0428
cd <集合根>                                   # 含 pyproject.toml 的 skills/experiment/yt-channel-distill
uv run --extra dev pytest tests -q            # 可選：確認環境
```

SKILL.md 內的指令都寫成 `uv run --project <collection-root> python ...`，`<collection-root>` 即本目錄。

## 外部工具

| 工具 | 用途 | 狀態 |
|---|---|---|
| `uv`、Python 3.11+ | 執行所有腳本 | 必要 |
| `yt-dlp`（隨 `pyproject.toml` 安裝） | inventory、字幕、影片下載 | 必要 |
| `ffmpeg`、`ffprobe` | 影片驗證、音訊切窗、抽影格 | 必要；放在 PATH 或 `$YTD_FFMPEG_DIR` |
| `faster-whisper`（`--extra asr`） | 本機 ASR | 選配，作者環境專用；模型需預先放在 `<ws>/data/models/`，不會自動下載 |
| `agy` CLI | AGY 全片 fallback 與缺口補證 | 選配，作者環境專用；配額解析依賴 `agy -p /usage` 的輸出格式 |

沒有 `faster-whisper` 與 `agy` 時，inventory、字幕、下載、source chunks、Wiki 與 coverage 仍可使用。

## Workspace 布局

工作資料放在集合之外的 workspace（解析順序：`--workspace` > `$YTD_WORKSPACE` > 目前目錄），每個頻道一個：

```
<ws>/
├─ data/
│  ├─ manifest/        videos.json、coverage-report.json
│  ├─ videos/          已驗證的本機影片
│  ├─ transcripts/     時間碼字幕與 ASR 輸出
│  ├─ processing/      frozen batch、source_chunks、reading_views、AGY jobs 與 packets、semantic_reviews
│  └─ models/          faster-whisper 模型目錄
├─ config/topic-rules.json   選配；沒有則所有影片 topic 為 unknown（範例見 examples/）
├─ knowledge/          p0_candidates.json、wiki/
└─ evaluation/
```

優先層級沿用 `P0` 命名（`audit-coverage --priority`）。搬動 workspace 會讓既有 ASR checkpoint 簽章失效而重跑。

## 目錄

- `skills/` — 五個 skills（各含 `SKILL.md`、`agents/openai.yaml`；腳本在各自的 `scripts/`）
- `src/channel_distill/` — Python 套件與 `python -m channel_distill` CLI
- `schemas/`、`examples/` — AGY 輸出 schema；topic 規則範例
- `tests/` — 離線測試，不連網
