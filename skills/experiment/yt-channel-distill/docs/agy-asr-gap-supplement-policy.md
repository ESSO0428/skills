# AGY ASR 缺損補充政策

## 目的

以 AGY／Gemini 的多模態 YouTube 讀取能力補足 local ASR 明確失敗的時間片段，降低為了少數不可用片段而重跑整支影片的成本；這不是另一條一般影片提取管線。

本政策只處理單片段 bounded gap。整支 `ASR_FAILED`、無可用字幕或影片下載失敗的全片 fallback，改依 [`agy-fallback-policy.md`](agy-fallback-policy.md) 與 frozen-batch 報表處理；不得因本文件的 gap 範圍而把全片候選漏掉。

## 觸發範圍

允許觸發：

- manifest 的 `transcript_unavailable_segments` 已列出 start/end；或
- 主代理在 ASR 終點審查時確認的局部 gap。

不允許觸發：

- official／auto 字幕已可用的影片；
- 完整 ASR `READY` 且沒有 gap 的影片；
- 以 AGY 重新摘要一般非 ASR 影片；
- 把整支 `ASR_FAILED` 靜默改成 AGY transcript。

## 證據包

每個補片段 packet 至少保留：

- `video_id`、公開 URL、缺損 `start_seconds`／`end_seconds`；
- 缺損前後的 ASR context 與其 chunk／timestamp provenance；
- AGY 的 audio／visual observation、可能的補充文字、unknown；
- model、prompt hash、執行時間、原始回應、錯誤或限制。

補充文字是 `AGY_SUPPLEMENTAL_OBSERVATION`，不是未經審核的 canonical transcript。若 AGY 回報 duration 與 canonical manifest／本機媒體不一致，packet 必須保留該差異並標為 partial coverage／review required，不得宣稱整部影片軌道完整。

## 合併門檻

主代理只在既有 ASR 與補充 packet 都收齊後審一次：

1. 時間範圍確實落在缺損區段；
2. 與前後 ASR context、投影片／影像沒有矛盾；
3. 補充內容能說明來源與不確定性；
4. 公式、圖表、研究數字若會改變結論，先保留 `REVIEW_REQUIRED`，交人工或下游審查。

不通過時保留原 gap，不重跑同一 packet。通過時也要保留原始 ASR gap、AGY packet 與合併決策，讓 provenance 可重建。
