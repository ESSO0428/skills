# 選擇式影片審閱流程

此流程的目標是減少語意判讀與影格檢視量，同時保留可逆 provenance；它不會把抽取到的段落宣稱為整支影片已完整閱讀。

## 階段邊界

先完成文字語意審查；時間戳／畫面核對是條件式 follow-up，在下游蒸餾遇到文字不足的主張時才執行，不是每部影片的前置必做項。

- **語意審查**：只要文字來源可讀，就先整理主題、主要主張、疑點、unknown、限制與 provenance；完成條件是每個可讀 packet 都有可回溯的文字審查結果。
- **視覺補證**：只對候選主張或文字不足的片段補看投影片／影格；完成條件是被選中的主張有足夠證據，未補證的內容仍保留 unknown／coverage gap。

## 1. 無時間碼文字篩選

- 從 canonical source chunks 建立不含秒數的 reading view（`build-reading-views`）。
- 篩選只讀文字與 segment ID，找出重要段落，以及文字不足或疑似含公式、表格、圖表的段落。

## 2. 對回時間戳並核對畫面資料（條件式）

- 對入選 segment ID 查 anchors，取得影片 URL、秒數與字幕類型。
- 只有 ASR 對公式、表格、圖表、投影片文字或講解內容不可靠時，才提取該段附近的影格：建立含 `purpose`、`source_chunk_id`／`claim_id`、`timestamp_seconds` 的 request，交給 `skills/acquiring-video-sources/scripts/extract_video_frames.py`，產生 `visual-evidence.v1` manifest（video hash、frame hash、command hash）。
- 每個補充觀察都保留 segment ID、anchor、影格路徑與來源型別；畫面只補足該段資訊，不取代原始影片或逐字稿。

## 3. 形成可供下游使用的證據子集

- 已核對、可回溯的 observation 才可進入下游的 note、candidate 與 normalization。
- 直接來源證據、ASR observation、visual observation、project inference 和 unknown 必須維持分開。
- `SELECTIVELY_REVIEWED` 表示已針對目標問題完成上述篩選、回查與必要的畫面核對；它可以作為下游的有界參考資料。

## 4. 高風險敘述

來源矛盾、公式／圖表可能改變結論、跨影片衝突，或要把內容提升為正式原則時，保留 `REVIEW_REQUIRED` 並交人工或下游審查；發現缺口時建立 `NEEDS_COLLECTION_REVIEW`，不自行補證據。審查結果記錄審查者、影片 ID、packet 版本／hash 與時間；沒有新增證據不重複審查同一 packet。

## 不可省略的邊界

- `SELECTIVELY_REVIEWED` 不等於 `VIDEO_CONTENT_COMPLETE`。
- 抽樣校準只衡量對已知 citation 的召回，不能證明未發現的新概念不存在。
- 若要聲稱影片完整內容已審閱，必須另有逐段完整審閱、完整視覺材料確認，或明確且可驗證的等價來源；本流程不作此宣稱。
