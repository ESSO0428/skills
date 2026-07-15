# Archive 規則

把內容移進 archive，不是刪掉，而是把它從主線視野移開。

## 何時 archive roadmap 主題

符合下列任一類時，優先考慮 `docs/roadmap/archive/*.md`：
- 主問題已回答
- 方向已完成且短期不再主推
- 效果偏弱，不值得繼續投入實驗成本
- 保留它的主要目的已變成避免重複踩坑

## 何時 archive report

若一個方向的 roadmap 主題已 archive，檢查對應 report：
- 若該報告也只剩回查價值，移到 `docs/reports/archive/*.md`
- 若該報告仍常被當成現行主證據引用，可暫留在 `docs/reports/*.md`

## 一致性規則

- `ROADMAP.md` 的 `## 已完成` 入口，應指向正確的 roadmap 檔案位置
- `docs/roadmap/archive/*.md` 應指向正確的 report 位置
- 若 roadmap 與 report 的位置不同步，先修正連結與存放位置，再視為完成

## un-archive（取消歸檔）

若新證據讓一個舊方向重新值得追：
- 把檔案從 `archive/` 移回父目錄
- 把狀態從 `archived` 改成 `active`、`revisited` 或其他明確狀態
- 補一句說明：這次為什麼重新打開
- 檢查 `ROADMAP.md` 與對應 report 的連結是否也要同步更新

## archive 的語氣

用中性、可重用的語氣，例如：
- 已完成且已歸檔
- 主問題已回答
- 暫不主推
- 效果偏弱，先不續追

避免把 archive 當情緒性垃圾桶；它是回查層。
