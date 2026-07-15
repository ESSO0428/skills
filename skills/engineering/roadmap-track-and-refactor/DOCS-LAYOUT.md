# 文件分層

`docs/` 是主看板外的深層結構。

具體的可追溯表格樣式，見 `TRACEABILITY-TEMPLATES.md`。

`docs/roadmap/**/*.md` 檔名可使用日期前綴以保留追溯性，但檔名不可有空格。

## `docs/roadmap/*.md`

放：
- 仍有決策價值的主題
- 從 `ROADMAP.md` 重構出來、但之後仍可能影響方向判斷的內容
- 表格或數據被壓縮後的摘要版

格式建議：
- 最上方先寫狀態、日期、一句結論
- 保留先前從 `ROADMAP.md` 轉出的 checklist，方便快速回憶做過什麼
- 可加簡單摘要表格，但不要塞滿不必要診斷
- 連到對應 `docs/reports/*.md`

## `docs/roadmap/archive/*.md`

放：
- 已完成、已回答、暫不主推的主題
- 主要用途是保留「做過且知道為什麼先不要再追」
- 已歸檔方向對應的壓縮版摘要

格式建議：
- 最上方先寫 `status: archived`、日期、一句結論、為什麼歸檔
- 保留原 checklist，方便回憶舊流程
- 可留簡短摘要表格，但不要塞深細節
- 連到對應 `docs/reports/archive/*.md` 或 `docs/reports/*.md`

## `docs/reports/*.md`

放：
- 完整實驗數據
- 表格
- 診斷
- 討論
- 來源路徑
- 壓縮前的完整版內容

規則：
- 表格若引用數據，應盡量有一欄寫清楚數據來源檔案路徑
- 若不是放在表格欄位，至少要在相鄰文字中明確寫出來源位置

它是證據層，不是主看板。

## `docs/reports/archive/*.md`

放：
- 已歸檔方向對應的完整報告
- 內容格式與 `docs/reports/*.md` 相同
- 已歸檔方向對應的完整版內容

關於 archive 的時機與一致性規則，請見 `ARCHIVE-RULES.md`。

## `docs/lab_report.md`

這是最終統整層，像工程研究版小論文。

用途：
- 用少量文字整理主要論據
- 提供 Intro / Method / Result / Discussion / Conclusion 式結構
- 用超連結指向真正的 `docs/reports/*.md`
- `docs/reports/archive/*.md` 只有限引用，作為反例或已排除方向

更新時機：
- 當一輪主要實驗結束，且至少有一份 `docs/reports/*.md` 新增或更新後，再評估是否同步更新 `docs/lab_report.md`
