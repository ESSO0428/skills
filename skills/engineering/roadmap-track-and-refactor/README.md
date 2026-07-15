# roadmap-track-and-refactor

讓 `ROADMAP.md` 維持成真正的主看板，同時把已完成主題、已歸檔方向，以及完整證據移到正確的 `docs/` 分層。

## 這個 skill 做什麼

這個 skill 用來維護以下分層工作流：

- `ROADMAP.md`
- `docs/roadmap/*.md`
- `docs/roadmap/archive/*.md`
- `docs/reports/*.md`
- `docs/reports/archive/*.md`
- `docs/lab_report.md`

它追求的不是把文件寫得更漂亮，而是讓主看板保持輕量、讓仍有決策價值的摘要被保留下來，並且讓深層證據可以一路追回來源。

## 什麼時候適合使用

當你需要：

- 讓最新實驗維持在 `ROADMAP.md` 最上方
- 把已完成內容移出主看板
- 判斷某個主題該放在 `docs/roadmap/` 還是 `docs/roadmap/archive/`
- 同時保留摘要層與完整報告層
- 隨著文件變多時新增或整理 `INDEX.md`
- 在徵得使用者同意後壓縮過大的表格

這是一個 user-invoked 的 workflow skill。當問題核心是文件結構與實驗 traceability，而不是單純一行小修時，就適合使用它。

## 它位於哪一層

這個 skill 介於日常實驗追蹤與長篇報告之間：

- `ROADMAP.md` 是 live board
- `docs/roadmap*` 保存壓縮後的主題摘要
- `docs/reports*` 保存完整證據與來源路徑
- `docs/lab_report.md` 是最終統整層

## 檔案地圖

- [`SKILL.md`](./SKILL.md) — 主工作流
- [`ROADMAP-SHAPE.md`](./ROADMAP-SHAPE.md) — 哪些內容應該留在主看板
- [`DOCS-LAYOUT.md`](./DOCS-LAYOUT.md) — roadmap / report 各層如何拆分
- [`ARCHIVE-RULES.md`](./ARCHIVE-RULES.md) — 何時 archive 與 un-archive
- [`INDEX-RULES.md`](./INDEX-RULES.md) — 何時該建立 index 頁
- [`TRACEABILITY-TEMPLATES.md`](./TRACEABILITY-TEMPLATES.md) — 連結與證據模板
- [`EXAMPLES.md`](./EXAMPLES.md) — 正反例與表格壓縮範例
- [`REFACTORING-HEURISTICS.md`](./REFACTORING-HEURISTICS.md) — 當內容擺放或清理判斷卡住時的補充啟發

## 備註

- `ROADMAP.md` 應優先偏向目前仍在進行的工作。
- 大表格壓縮前要先詢問使用者。
- 不要讓摘要頁成為唯一剩下的證據層。
- 若這個 skill 之後繼續演化，這份 `README.md` 應保持簡短，把操作細節放回上面的 reference 檔。
