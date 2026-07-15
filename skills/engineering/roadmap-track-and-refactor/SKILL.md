---
name: roadmap-track-and-refactor
description: 維護 `ROADMAP.md` 與 `docs/` 的分層整理工作流。
disable-model-invocation: true
---

把 `ROADMAP.md` 當成主看板：最新實驗放最上面，進行中的條目保留 checklist，已完成條目收斂成短入口，深細節移到 `docs/`。

## 1. 判斷這次工作屬於哪一種

先判斷這次是：
- 維護進行中的實驗條目
- 收斂已完成條目
- 歸檔暫不主推的方向
- 建立或整理索引

這個 skill 裡的 `ROADMAP` 一律就是 `ROADMAP.md`。
若這次工作同時跨到多種類型，先用主要類型起步，再照後續步驟把 `archive` / `index` 一起補完。

完成條件：已知道這次是 `track`、`refactor`、`archive` 或 `index` 哪一種，且若屬於複合任務，已知道後續要一起補哪些步驟。

## 2. 先守住主看板

- 保持最新實驗在 `ROADMAP.md` 最上方。
- 進行中的實驗保留 `## 日期-實驗名` + checkbox checklist。
- `ROADMAP.md` 用 checkbox 追蹤狀態，用簡單表格呈現結果；若簡短摘要已足夠，可建議壓縮表格，但壓縮前先和使用者確認。若仍太重，再把大量數據細節表格移到 `docs/reports`，並在主看板留下超連結。
- 若使用者暫時留下表格、片段數據或想法來減少認知負擔，先寬容保留；但應主動思考是否能用更好的模組化方式減少主看板負擔。
- 若使用者提出的想法、結論或後續方向仍對未來決策有幫助，可主動建議整理到 `ROADMAP.md`。

讀 `ROADMAP-SHAPE.md` 與 `EXAMPLES.md`。

完成條件：`ROADMAP.md` 仍能一眼看出最近主線與目前進度。

## 3. 把內容移到正確層

- 仍有決策價值的已完成主題 → `docs/roadmap/*.md`
- 已完成、已回答、暫不主推的主題 → `docs/roadmap/archive/*.md`
- 深細節、完整數據、完整診斷 → `docs/reports/*.md`
- 已歸檔方向若對應報告也不再主推，檢查是否應同步移到 `docs/reports/archive/*.md`
- 最終統整層是 `docs/lab_report.md`；索引層是 `docs/roadmap/INDEX.md` 與 `docs/reports/INDEX.md`

讀 `DOCS-LAYOUT.md`、`ARCHIVE-RULES.md` 與 `TRACEABILITY-TEMPLATES.md`。
若這次工作的 refactor 判斷卡住，讀 `REFACTORING-HEURISTICS.md`。

完成條件：主看板不再承擔不必要的細節，且 roadmap / report 的位置彼此一致。

## 4. 必要時建立索引或壓縮表格

當 `docs/roadmap` 或 `docs/reports` 的文件開始變多、難找、主題分散時，建立或整理 `INDEX.md`。

若主看板上的表格太大、太重、太難回顧，先詢問使用者是否接受壓縮；若接受，再把還留在主看板上的資訊壓成：
- 最佳值 / 最差值
- 差值或增減量
- 少量代表點
- 分布摘要或統計摘要

需要時可用工具（如 python）幫使用者做這種資訊壓縮。

壓縮後要保留兩層：
- 壓縮版：放 `docs/roadmap/*.md` 或 `docs/roadmap/archive/*.md`
- 完整版：放 `docs/reports/*.md` 或 `docs/reports/archive/*.md`

讀 `INDEX-RULES.md` 與 `EXAMPLES.md`。

完成條件：使用者可以用少量 H2 與少量 bullet 找到主要方向與對應文件，且大表格已被壓成更容易回顧的摘要。

## 5. 完成前核對

逐項確認：
- `ROADMAP.md` 是否比整理前更清楚
- 最近實驗是否仍最容易看到
- 已完成條目是否已收斂成短入口
- `docs/roadmap` / `docs/roadmap/archive` / `docs/reports` / `docs/reports/archive` 的超連結是否一致、可追溯
- 摘要版與完整版是否都在 `docs/` 有落點
- 若某段內容只是暫時降低認知負擔，是否已評估「先保留」或「改放其他地方」哪個更合適

完成條件：主看板更清楚、深資料仍可追溯、使用者能快速回顧最近實驗與最佳方向、且需要保留的數據都有清楚來源路徑。
