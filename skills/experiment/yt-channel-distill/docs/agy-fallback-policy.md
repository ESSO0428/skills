# AGY 全片 fallback 政策

## 目的與適用範圍

AGY 是來源取得或轉錄失敗時的備援證據來源，不是所有非 ASR 影片的通用提取器。以下情況可進入 AGY 候選統計：

- 本機影片已驗證，但整支 ASR 為 `ASR_FAILED`；報表稱為「ASR 全片失敗／壞軌候選」，不把它當作媒體已物理損壞的證明。
- 本機影片已驗證，但沒有可用字幕／逐字稿，例如 `ASR_NEEDED`、`FETCH_FAILED`。
- 本機媒體明確損壞、只能部分讀取，或有明確 ASR gap；部分缺損仍優先只補 bounded gap。
- 直接影片抓取失敗。這些項目單獨列出；只有遠端能力 canary 實際讀到影音後，才加入可執行 AGY 清單。只讀到標題、描述或頁面 metadata 不算成功。

已取得影片且有完整可用字幕者不因「不是 ASR」而觸發 AGY。`DOWNLOAD_FAILED`、`VERIFY_FAILED`、`UNAVAILABLE` 不能與「AGY 可嘗試」混算。

## 用量閘門

1. 對每種來源模式先用少數代表樣本測量；遠端 URL 模式需確認有實際影音 observation，不能從本機檔測試推定遠端可用。
2. 記錄每片實際 duration、AGY CLI 版本、model、prompt hash、模式、時間、token／usage 前後值與輸出 coverage，分短／中／長片估計單片用量。
3. 批次開始前 agent 以 AGY CLI 的 `/usage` 查詢目前 5 小時與週配額，再依 pilot 前後的配額差計算保守可跑數量並建議使用者。headless 模式使用 `agy -p /usage`；互動 TUI 則在 prompt 輸入 `/usage`。這是 CLI 內建查詢，不是模型 prompt。若因未登入、服務錯誤或 CLI 不支援而無法取得 quota，才請使用者提供剩餘量；不可把估算冒充帳戶實際餘額。
4. 由使用者選定本批影片數／ID 後才執行。每批結束再讀取一次報表，不輪詢同一執行中的程序。

## 能力評估的兩種方案

對任何最終仍無可用文字的影片，報告必須把「AGY 沒完成」與「目前沒有可救來源／已達停止門檻」分開說明；說明後追加：**建議放棄本輪**。這是本輪成本與重試政策的建議，不是永久刪除影片；只有使用者明確批准一次 bounded retry 才能再排程。

若使用者要判斷本週 AGY 值不值得擴大，先用最新 `agy-plan` 報表確認候選數與 ID；候選集合由 `ASR_FAILED` 與無可用字幕兩類組成，數量不可硬編碼，執行前必須重算。必須核對唯一候選 ID 並去重；候選總數以 unique video ID union 計算，重疊 ID 只計一次；分層抽樣前也要確認兩類 ID 清單互斥，並保存清單／報表作為樣本框。向使用者並列兩種方案，不把任一方案當成已批准：

| 方案 | 做法 | 可以回答 | 不能據此宣稱 |
|---|---|---|---|
| **候選集分層試跑** | 從 `ASR_FAILED` 與無可用字幕兩類分層抽樣，測真正的候選影片 | AGY 是否能在各候選類別產生經審查可用的時間碼證據 | 未抽樣影片一定可恢復，或整批可在本週額度內完成 |
| **已下載影片正向控制** | 對一支本機已驗證、已知可讀的影片跑相同 local-file AGY 工作，檢查 CLI、媒體讀取、回應擷取及落檔 | 本機 AGY 呼叫與批次保存路徑是否正常 | `ASR_FAILED`／無字幕候選可恢復，或其成功率與成本相同 |

若沒有相符 pilot，無論使用者選哪個方案，最初都只能提出**單 job pilot**，不能預先提交多支批次。Option A 的首支候選影片同時是其類別的第一個樣本；Option B 的正向控制是 runner canary。首支 pilot 的精確單片用量未知，使用者須明確核准一支未知成本嘗試。保存 post-run quota 後，若仍能支持下一輪且在使用者批准上限內，才可準備下一個固定小輪次；用量無可觀測變化時停在 `INCONCLUSIVE`，不得把它當成零成本繼續。

候選集方案的初始操作樣本建議為：**每類 2 個成功結果**。第一輪每類最多試 2 支；若某類未達標且 quota 允許，第二輪只可為該類再加 1 支，亦即**每類最多 3 次嘗試**、全批最多 6 支。達到每類 2 個成功結果即停止；到上限仍未達標則以 `INCONCLUSIVE` 結束，不因樣本不足而自動擴大。這是小型可行性篩查，不是統計上可靠的成功率估計。若 quota preflight／使用者核准的用量上限低於下一輪預估，提前停止並回報目前證據。已下載正向控制只需 1 支；若該支失敗，先記錄並診斷，不自動連續重試。

本工具的 `agy_batch_jobs.py run` 會逐一完成事先準備的固定 job 清單，並不會依「成功數」動態停止。候選集方案因此按**固定小輪次**執行：第一輪最多 2 支／類別，命令結束後一次審核與核對；只有樣本目標未達且仍在次數／用量上限內，才準備第二輪。禁止把最多 6 次當成預設整批授權，也禁止以 while 腳本不設用量及嘗試上限地遍歷整個候選集。

只有經審核確認 AGY 實際讀取影音、輸出有效時間碼文字，且足以支援該類工作，才計入成功樣本。完整成功沿用 final report 支援的 `READ_SUCCESS`，並設 `review_status=ACCEPTED`、`coverage_complete=true`；部分結果不得冒充完整成功。使用以下互斥結果，並保留原始 ASR／字幕狀態，不覆寫來源狀態：

- `AGY_UNREADABLE`：AGY 命令正常結束，但明確回報 `METADATA_ONLY`／`INACCESSIBLE`／`NONE`，或無法讀到影音；保存原始回應作為判據。
- `AGY_EXECUTION_FAILED`：啟動錯誤、非零結束、timeout 或程序中斷；這不證明 AGY 讀不到媒體。
- `AGY_INVALID_OUTPUT`：回應不是可解析且符合 schema 的預期 JSON；不等同媒體不可讀。
- `AGY_PARTIAL`：實際讀到部分影音／逐字稿但有 coverage gap；記錄時間範圍，不算完整成功樣本。

每次只在已完成的 job 輪次後讀取 `/usage`，不輪詢執行中的程序。若用量介面只顯示整數百分比，讀值不變表示**低於可觀測解析度或未知**，不是零成本；出現 1 個百分點跳動也不能當成精確單片成本。用量無法支持下一輪預算時就停止，向使用者報告 `INCONCLUSIVE`，不得猜測或擴大樣本。

**使用者選定方案、影片數／ID 與用量上限前不得啟動**任何 AGY job。已下載正向控制可作為低成本的第一個端到端 canary；若使用者要評估候選集的修復可行性，必須選候選集分層方案，正向控制不能取代它。

在首支 matching pilot 完成前，**首支 pilot 的精確單片用量未知**；不能根據總剩餘百分比編造單片成本或整批容量。agent 先查 quota 並告知此未知量，僅可提出一支 pilot 的 bounded attempt，請使用者明確核准「一支影片、實際成本未知」後才啟動。Pilot 完成後立刻保存 post-run 用量；若整數百分比沒有變化，記為低於解析度／未知，不視為零成本。除非取得可比較的單片成本量測且下一輪仍在使用者核准的上限內，否則不開始下一輪。

AGY CLI 可用 `agy -p /usage` 回報模型家族的 5 小時與週剩餘百分比及重置時間。agent 應記錄查詢時間、CLI 版本、與本批模型相符的 quota 家族及 reset 時間，並將結果寫入 usage snapshot；不可把 Claude/GPT 配額套用到 Gemini 模型，或將一個模型家族的百分比套用到另一家族。若 CLI 查詢失敗，才請使用者提供查詢輸出。快照格式：

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

報表中的可執行建議數依 pilot 單片消耗按影片時長縮放，再乘 safety multiplier；model 與來源模式必須相同。local file 與 remote URL 不能混在同一估算批次，需各自代表樣本。此估值不是 live quota 查詢或保證；未提供實際 remaining、相同 model/source mode pilot 與 pilot 前後差值時，AGY job preparation 必須拒絕執行。

## 批次 ledger

批次檔至少保留固定目標集合與 AGY 結果，例如：

```json
{
  "run_id": "batch-a",
  "expected_video_ids": ["video-id-1", "video-id-2"],
  "agy_remote_capability": "UNVERIFIED",
  "agy_results": {
    "video-id-1": {
      "status": "READ_MEDIA",
      "review_status": "ACCEPTED",
      "coverage_complete": true,
      "agy_cli_version": "<version>",
      "model": "exact-model-id",
      "prompt_sha256": "sha256-of-exact-prompt"
    }
  }
}
```

`agy_remote_capability` 僅能為 `UNVERIFIED`、`AVAILABLE` 或 `UNAVAILABLE`。每筆嘗試都保存來源模式、時間、原始回應／packet、錯誤和用量；範例中的其餘 provenance 欄位亦需保留。AGY 只有在媒體實際可讀、review 為 `ACCEPTED`、coverage 完整且 CLI/model/prompt provenance 齊全時才計為修復。

## 統計與集合核對

`expected_video_ids` 是同一批 acquisition、AGY 與最終 review 的 frozen scope。報表必須同時給 count 與 ID：

- acquisition：預期、已驗證本機影片、直接下載失敗、仍 pending，以及逐字稿狀態。
- AGY 前：本機可嘗試數、`ASR_FAILED` 候選、沒有可用字幕、其他 transcript 問題、直接抓取失敗及遠端能力狀態。
- final：預期、已驗證本機影片、可用 transcript/AGY source、原先 `ASR_FAILED` 而經審核修復者、AGY 嘗試未修復者及最終 unresolved IDs。

所有子集合必須包含於 frozen scope；media 結果必須把預期集合分割成 verified、terminal failure、pending；final source 結果必須把預期集合分割成 usable 與 final failed。任何重複、遺漏、越界 ID 或非互斥分割都要回報 `FAIL`，不得進入下一階段。

skill 內建三個可重跑入口，各自負責清楚分離的工作：

- `scripts/acquire_video_batch.py freeze/plan/run`：從使用者明選 ID 建立不可覆寫的 frozen ledger，先做整批磁碟預檢，再逐片下載、驗證、取字幕及必要時首次 local ASR。`run` 必須明確 `--execute`；terminal download/ASR failure 不自動重試。
- `scripts/video_batch_report.py`：唯讀產生 acquisition／AGY plan／final 統計，可將 UTF-8 JSON 寫到下一階段使用的檔案。
- `scripts/agy_batch_jobs.py budget/prepare/run/record-usage-after`：`budget` 在選片前依 pilot model/source mode/影片時長提供建議數；`prepare` 再驗證報表、使用者批准 ID、agent 以 `/usage` 擷取的 quota snapshot、pilot 成本與候選資格，產生帶 prompt SHA-256 的 job；`run` 必須明確 `--execute`，逐片執行一次且只記錄為待審查，不自動批准 coverage 或修復；完成後使用 `record-usage-after` 附加 agent 以 `/usage` 擷取的用量快照與可比較的前後差值。

AGY `run` 預設不帶 `--dangerously-skip-permissions`；只有使用者明確要求免權限提示時才帶 `--yolo`。三個入口都不會自行猜測帳戶用量。執行後需 agent 審核原始 packet、修正 ledger 的 review／coverage 欄位，再跑 final report。
