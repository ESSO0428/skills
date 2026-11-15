# 影片蒸餾規則

本檔是這個集合中所有影片任務的單一規則入口：授權、磁碟、AGY、ASR 停止門檻與 provenance 都以它為準。它固定安全邊界與流程骨架，細節以連結的政策文件、程式與 manifest 為準。

`<ws>` 指 workspace（`--workspace` > `$YTD_WORKSPACE` > cwd），布局見 [`README.md`](README.md)。

## 穩定的流程骨架

1. **來源 inventory**：從官方頻道、真實 playlist 與（若有）官方課綱／清單建立去重清單；課綱連結但 unlisted 的影片單獨記錄可見性，不冒充 playlist 成員。
2. **來源取得**：先取官方／自動字幕與 metadata；依使用者授權用 `yt-dlp` 只在本機保存指定影片，下載後以 `ffprobe` 驗證。不得直接批次下載整個頻道，下載前重查空間並保留安全餘量，下載前向使用者報告預估量並取得同意。若 topic 內有已記錄的失敗項，使用 `download --topic <topic> --video-id <id>` 精確處理下一支，不為了清單順序盲目重試失敗項。
3. **文字證據**：保留原始時間碼字幕、無時間碼稿、source chunks、anchors、候選段落與失敗狀態；每份文字進入可搜尋的主題／時間索引。
4. **ASR fallback**：只有沒有可用字幕時，才對已驗證本機影片跑可續跑的 local ASR。程式自行切窗、checkpoint、重試、放棄與原子合併；主代理不逐片段輪詢或重複判斷。
5. **AGY fallback**：整支影片 `ASR_FAILED`、沒有可用字幕、或直接影片取得失敗時，先以批次統計確認候選集合，再評估 AGY zero-shot。影片已抓到但只缺局部 ASR 時仍只補 bounded gap；直接抓取失敗者須先確認目前 AGY 路徑真的能讀到影音。AGY 產物是補充證據，不覆寫 canonical transcript。
6. **內容審查**：AGY／來源處理結束後，先核對預期集合、已驗證影片檔、可用文字來源、AGY 修復與最終缺口的 ID 集合能自洽；再做一次必要的語意審查。下游蒸餾只接受可回溯 provenance。
7. **索引與覆蓋**：`<ws>/knowledge/wiki/` 是從候選與 coverage 報告編譯的導航層，不是事實來源；優先層級（預設 `P0`）先完成，其餘與未完成 ASR 保留在 manifest／coverage gap。

## 階段邊界：語意審查先於蒸餾補證

- `ASR_FAILED`、`FETCH_FAILED` 與 `AGY_FULL_VIDEO_GAP` 是文字取得／補證終態，不是「整支影片已證實壞軌」；只有 ffprobe／解碼錯誤或明確的 damaged/inaccessible range 證據，才能標記媒體完整性問題。已驗證本機影片的文字 gap 應保留為 gap，不因語意階段而盲目重試。
- 最終回報每個 unresolved gap 時，必須先說明分類：`AGY_FULL_VIDEO_GAP` 是 AGY 工作未完成／未產生可用文字，`SOURCE_UNAVAILABLE` 是目前沒有可用來源或已達停止門檻；分類後一律追加「建議放棄本輪」，只有使用者明確批准一次 bounded retry 才可重新排程。
- 語意審查是 **transcript-first**：在 canonical transcript、source chunks 與 provenance packet 就緒後，先為每個可讀 packet 記錄主題、主要主張、疑點、unknown、限制與可回溯時間範圍。這一步不要求逐部影片完整回看投影片。
- 投影片／影格回看是下游的條件式補證：只針對重要候選主張、公式／表格／圖表，或文字不足以安全判斷的片段按需使用；全片影像回看不是前置門檻。
- 需要補證時，先建立含 `purpose`、`source_chunk_id`／`claim_id` 與明確 `timestamp_seconds` 的 request，再交給 `skills/acquiring-video-sources/scripts/extract_video_frames.py` 產生帶 video hash、frame hash 與 command hash 的 `visual-evidence.v1` manifest；流程見 [`docs/selective-review-workflow.md`](docs/selective-review-workflow.md)。
- 若仍無法安全判斷關鍵主張，保留 `unknown` 並建立最小的 `NEEDS_COLLECTION_REVIEW`／visual follow-up；不得用猜測補全，也不得把 selective review 宣稱為完整影片理解。
- 人工二審（`MANUAL_SECOND_REVIEW_PENDING`）是非阻塞旁支：有可讀文字的影片照常完成語意審查與下游蒸餾，不得把二審設成全批次 gate；缺口影片保留原失敗分類並排除於本批次，二審後只對保留項目增量補證。

## 證據與 provenance 契約

- canonical transcript、source chunks、manifest 與原始媒體是事實來源；摘要、wiki、AGY observation 都不能覆寫它們。
- 每個候選或 principle 至少記錄影片 ID、來源 URL、時間範圍、逐字稿型別、chunk／投影片頁碼（若有）與處理狀態。
- evidence packet 必須分開 `direct_evidence`、`asr_observation`、`visual_observation`、`project_inference`、`unknown`；推論不得偽裝成來源原話。
- 公式、圖表或術語未核對時標成 `REVIEW_REQUIRED`；來源矛盾時保留矛盾，不用猜測消除。

## ASR 續跑與停止門檻

- 官方／自動字幕優先；長片只重用通過來源與時間戳驗證的 `READY` checkpoint 批次。
- 只有 allocator 記憶體錯誤啟用單窗口退避；每個子窗口自動嘗試兩次。超過次數直接寫入 `ASR_SEGMENT_UNAVAILABLE` 並跳過，其他片段繼續。
- 尚有其他文字時影片為 `READY_PARTIAL`，保留 `transcript_unavailable_segments` 與 coverage gap；整批／媒體／模型／安全磁碟失敗才是 `ASR_FAILED`。
- 每支影片的擷取命令以「預估終點」為等待窗口，不採固定短間隔輪巡；命令結束後才讀最終 transcript、不可用片段與 manifest。以媒體長度與本機已觀察吞吐估算等待時間；若估計更久就一次等待更久，窗口到期仍未結束才按新速率重新估算，不重啟命令。
- 可繼續條件只有：新增驗證批次、模型／依賴／空間有實質改變，或錯誤屬一次性 I/O／暫時性失敗；每次先保留 checkpoint、錯誤與 manifest。

詳細停損與欄位見 [`docs/asr-recovery-policy.md`](docs/asr-recovery-policy.md)。

## AGY ASR gap supplement

- 觸發條件是 manifest 的 `ASR_SEGMENT_UNAVAILABLE`／`READY_PARTIAL` offset，或主代理明確確認的 bounded gap；完整 ASR、官方／自動字幕與一般非 ASR 影片不觸發。
- 輸入含影片 ID／URL、gap start/end、前後 ASR context 與既有 provenance；輸出只是一個補充 packet，不能直接改 canonical transcript、candidate 或 knowledge。
- packet 記錄 model、prompt hash、時間、原始回應與來源時間範圍；不得把推測填成逐字稿或宣稱全片理解。
- 主代理在同一部影片的既有內容與補片段都收齊後只審一次；無矛盾且 provenance 足夠才合併，否則保留 gap／`REVIEW_REQUIRED`。

詳細欄位見 [`docs/agy-asr-gap-supplement-policy.md`](docs/agy-asr-gap-supplement-policy.md)。

## AGY 全片 fallback 與批次統計

- `ASR_FAILED` 是整支影片沒有可用 ASR 的候選狀態，不等同於已證實媒體實體壞軌；保留原錯誤與媒體驗證結果。沒有可用字幕但本機影片已驗證者也列為候選，報表分開列出兩類。
- `DOWNLOAD_FAILED`／`VERIFY_FAILED` 等直接抓取失敗要明確列數與 ID；除非 AGY 遠端能力 canary 確實讀到影音，否則不得把它們算成可實際執行的 AGY 候選或重複批次嘗試。
- AGY 前置報表、候選 ID 核對、單片／批次用量估算與建議數由 agent 主動完成；agent 先以 CLI 處理的 `agy -p /usage` 讀取目前模型配額，再依同 model、source mode 與提取範圍相符的 pilot 估算用量。若 `/usage` 因未登入、服務錯誤或 CLI 不支援而無法取得配額，才向使用者索取觀測值；若缺代表 pilot，明確說首支 pilot 的精確單片用量未知，只提出一支 bounded attempt 並取得「一支影片、實際成本未知」的明確核准，不虛構單片成本。不得要求使用者跑報表／budget 腳本、手算或自行建立 snapshot／job JSON。不可將 `/usage` 當作一般模型 prompt 執行。
- 做 AGY 能力評估時，對目前候選集要提出兩個可選方案：`候選集分層試跑`（測實際修復能力）與 `已下載影片正向控制`（只驗證本機讀取及批次落檔）。每次重跑報表核對唯一候選 ID 並去重；使用者選定方案與上限前不得啟動。正向控制不得冒充候選群修復率；配額顆粒度不足或 pilot 不匹配時，不得宣稱可跑完全部候選。
- 使用者選定 ID／上限並核准預算後，agent 建立 frozen batch、snapshot、報表與 prepared jobs，交付可直接貼上的大量執行命令；大量 `agy_batch_jobs.py run --execute` 由使用者在 terminal 啟動，agent 不代跑。`--limit` 只界定單一 wave，不得靜默縮小已核准的 Full burn；Full burn 使用零 reserve，只保留硬性零配額停止。每個 wave 必須同時輸出 `wave_complete` 與 frozen batch 的 `global_remaining_unattempted_count`，未跑滿時以非零結束碼回報，不能把 wave 完成誤報成整批完成。使用者回報命令結束後，agent 主動記錄可觀測的 post-run 用量並產生 final report；不可觀測的 quota 保留未知、不推算。
- AGY quota 報表的 `當週理論上限` 與 `預估完成` 都必須呈現「最少／最多」兩值，先最少、後最多；下達批次命令時明確聲明採用最多（最久的保守估算）安排，實際可能更快。若 Full burn 已有完整批次實測，優先採用實測週期，不沿用較慢的 pilot high-water 推算。
- 每次 AGY 結果記錄 CLI 版本、model、prompt SHA-256、來源模式、時間、coverage、原始結果與使用量量測；未經審核且未證明 coverage 完整的輸出不算修復成功。
- 來源批次固定 `expected_video_ids`。使用 acquisition skill 內的 `acquire_video_batch.py` 凍結明確選取 ID、做磁碟預檢並執行 resumable acquisition；agent 主動執行 `video_batch_report.py` 產生 acquisition／AGY／final 統計，並用 `agy_batch_jobs.py` 依 agent 從 `/usage` 讀取（或查詢失敗時由使用者提供）的 quota snapshot 與核准 ID 準備 job。預期數、已驗證本機媒體、逐字稿來源成功、AGY 修復及最終失敗都輸出 ID 清單並檢查集合分割；不自洽或有超出批次 ID 時停止後續階段。

詳細狀態與 ledger 欄位見 [`docs/agy-fallback-policy.md`](docs/agy-fallback-policy.md)；前景執行與配額方案表見 [`docs/agy-foreground-execution.md`](docs/agy-foreground-execution.md)。

## 高風險敘述

來源矛盾、公式／圖表會改變結論、跨影片衝突，或要把影片內容提升為正式原則時，視為高風險：保留 `REVIEW_REQUIRED`，交人工或下游審查，不由本集合自行定論。清楚、低風險、純機械整理不需額外審查。

## 完成與不可用標記

- 一支影片只有在媒體、文字型別、時間範圍、provenance 與 manifest 狀態一致時才可標 `READY`；部分可用標 `READY_PARTIAL`，缺損必須可搜尋。
- `ASR_SEGMENT_UNAVAILABLE`、`ASR_FAILED`、`REVIEW_REQUIRED` 與 `NEEDS_COLLECTION_REVIEW` 都是可交付的狀態，不得以空白摘要假裝完成。
- 未經使用者明確要求，不發布到 GitHub 或其他平台、不刪除來源、不放寬授權或磁碟安全限制。
