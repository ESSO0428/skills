# Report 要求

正式結果不能只停在 `ROADMAP.md` checkbox；應有對應的 `docs/reports/*.md` 落點。

## 何時要更新 report

一旦已有正式結果，就應：
- 更新既有 report
- 或新增新的 `docs/reports/*.md`

不要等到所有事情都做完才一次回填；至少要把正式結果先落下來。

## 表格與資料來源

重要表格應盡量直接帶 `資料來源` 欄，或在表下方明確註記來源路徑。

可接受：
- `best.json`
- `summary.csv`
- `metadata.json`
- 對應 `.sh` 腳本
- 其他能讓人追回原始數據的位置

規則：
- 只要某張表在支撐結論，就要能追回來源
- 若一整張表共用同一來源，可在表下方統一寫
- 不要只寫「見實驗結果」而沒有實際路徑

## ROADMAP 與 report 連結

若 `ROADMAP.md` 條目已有 report 入口：
- 保持連結正確
- 若 report 檔名或位置改了，記得同步更新

若目前還沒有 report 入口，且這次已產生正式結果，應補上對應入口。
