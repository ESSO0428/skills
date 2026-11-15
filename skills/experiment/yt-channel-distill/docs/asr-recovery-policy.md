# ASR 續跑與停止門檻

這份政策把本機 ASR 的重跑限制成可觀察、可回溯的動作，避免同一錯誤無限試錯。

## 可重用流程

1. 先採用官方或自動字幕；只有沒有可用字幕、且本機影片已通過驗證時才跑 local ASR。
2. 長片切成固定時間窗，由獨立 worker 處理。每批完成後寫入 signature-specific checkpoint；只接受通過影片 ID、來源 URL、offset、chunk 與 word timing 驗證的 `READY` 檔。
3. 已完成的批次永不重做。明確出現 `mkl_malloc`／allocator 記憶體錯誤時，才把當前失敗批次退避為單窗口 worker；每個子窗口最多自動嘗試兩次，成功的立即保留，失敗的寫入不可用片段紀錄後跳過，其他子窗口繼續，最後原子合併回原批次。
4. transcript `READY` 或 `READY_PARTIAL` 後才執行 source chunks、無時間碼 reading view、anchors 與候選片段。

## 可以繼續

- 這次重跑產生新的、可驗證 `READY` checkpoint。
- 外部條件已改變，例如修正依賴、換用已存在的本機模型、釋放安全磁碟空間，或暫時性 I/O／worker timeout 已消失。
- 字幕抓取遭 429 時，停止重複抓字幕；若影片已驗證，改走本機 ASR，兩條來源分開記錄。

## 片段級放棄與影片級停止

- 單一子窗口達到兩次自動嘗試仍失敗時，直接標記 `ASR_SEGMENT_UNAVAILABLE`，保留 offset、結束時間、錯誤與嘗試次數，跳過該片段並繼續同批其餘片段。只要仍有文字，整支影片輸出 `READY_PARTIAL`，manifest 與 ASR JSON 都列出 `transcript_unavailable_segments`；這不是完整語料。
- 後續 `transcribe --postprocess` 對 `READY_PARTIAL` 一樣只跑一次文字 source／reading 管線；不可用片段留在 coverage gap，不送進語意模型假裝已讀。

影片級才直接暫停並記錄目前不可用：

- 整批音訊／worker 不是可分割的片段級錯誤，或所有片段都失敗而沒有任何可用文字。
- 媒體損壞／遺失、模型不在本機、或安全磁碟餘量無法滿足；不得刪除不相關資料來換空間。
- 影片級停止時保留成功 checkpoint、最後錯誤、manifest 的 `ASR_FAILED`／`transcript_error` 與 coverage gap，並在進度文件標記「目前不可用」；這不是完整語料，也不是永久判定。只有外部條件改變才重新排程。

`ASR_READY` 但含有零時長字詞、公式／圖表或術語未核對時，維持 `REVIEW_REQUIRED`，不把警告消掉。
