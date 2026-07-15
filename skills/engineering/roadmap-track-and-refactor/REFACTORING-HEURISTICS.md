# Refactoring 啟發

這些不是主流程，而是在 `track / refactor / archive / index` 的判斷卡住時，用來幫助決策的簡短啟發。

## Split Phase（分階段）

先分清楚這次是在：
- 維護進行中條目
- 收斂已完成條目
- 歸檔舊方向
- 建立索引

不要一開始就同時改所有層。

## Move Function（移動函式）

規則放在最該擁有它的檔案：
- archive 規則 → `ARCHIVE-RULES.md`
- 可追溯模板 → `TRACEABILITY-TEMPLATES.md`
- 看板形狀 → `ROADMAP-SHAPE.md`

不要把同一規則重複寫在很多地方。

## Extract Function（抽出函式）

若某種整理方式會一再重複，就把它抽成：
- reference 檔
- 表格模板
- 範例片段

不要每次都在 `SKILL.md` 重講一次。

## Decompose Conditional（拆解條件）

把分類條件寫明：
- 仍有決策價值 → `docs/roadmap/*.md`
- 已完成、已回答、暫不主推 → `docs/roadmap/archive/*.md`
- 深細節與完整證據 → `docs/reports*.md`

不要只靠模糊直覺決定內容該放哪。

## Encapsulate Collection（封裝集合）

把 `ROADMAP.md` 當成主看板介面，不要讓它直接裸露所有原始表格與細節。
主看板優先暴露：
- 最近實驗
- 短結論
- 入口連結

## Inline Function（內聯函式）

若某個 reference 檔只剩一句顯而易見、沒有獨立價值的規則，考慮刪掉或併回其他檔案。

## Replace Loop with Pipeline（以 Pipeline 取代迴圈）

大表格若只是為了回顧方向，可先用工具（如 python）做聚合、篩選、差值或代表點摘要，再決定留什麼進主看板。

## Remove Dead Code（移除死碼）

若某段內容：
- 不再影響最近實驗
- 不再影響未來決策
- 深資料也已在其他 docs 留存
- 且使用者同意

可直接刪，不一定要 archive。
