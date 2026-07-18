---
name: executing-roadmap-plan
description: 按照既有 `ROADMAP.md` 計畫執行，並維持 checkbox、report 與 evidence 紀律。
disable-model-invocation: true
---

先照既有 `ROADMAP.md` 條目執行，再如實更新 checkbox、`docs/reports/*.md` 與對應證據。

## 1. 先鎖定本次要執行的計畫條目

先確認本次要執行的是哪個 `ROADMAP.md` H2 條目，以及它目前是否已連到既有 report。

若同時有多個條目，先明確決定這次主軸，不要一邊執行一邊漂移範圍。

完成條件：已知道本次要執行哪個 `ROADMAP.md` 條目、目前有哪些 checkbox、對應 report 在哪裡，或目前尚未建立。

## 2. 按 checklist 執行，不要預先勾選

- 只在工作真的完成、且已有可追溯證據後，才把 checkbox 從 `[ ]` 改成 `[x]`
- 不要因為「快做完了」或「應該沒問題」就先勾
- 若執行過程發現缺少必要步驟，可在原條目下補新的 checkbox 或子 bullet，但不要默默把缺口吞掉
- 若專案本身另有實驗執行規則（例如 worktree、script-first、命名慣例），先遵守那些規則

讀 `CHECKBOX-DISCIPLINE.md`。

完成條件：checkbox 狀態如實反映目前進度，而不是樂觀預估。

## 3. 有正式結果就寫進 report

一旦已有正式實驗結果，就更新既有 `docs/reports/*.md`，或新增對應 report。

- 重要表格要附明確資料來源
- 若整張表共用同一來源，可在表下方統一註記來源路徑
- 不要只留設定或命令；要讓結果能支撐後續判讀
- `ROADMAP.md` 條目若已有 report 入口，記得同步維護連結

讀 `REPORT-REQUIREMENTS.md`。

完成條件：正式結果已有 report 落點，且關鍵表格可追回來源。

## 4. 全部跑完後補齊結論段落

當這個計畫條目的主要實驗都已跑完、結果也已整理進 report 後，report 至少要有：
- `結果`
- `結論`
- `討論`
- `最終結論`

不要只留表格或設定。若目前還在進行中，可先保留部分內容；但在宣告整個計畫完成前，這四段必須補齊。

讀 `COMPLETION-RULES.md`。

完成條件：若本次計畫已完成，report 也已具備完整論述，而不是只有 raw numbers。

## 5. 完成前核對

逐項確認：
- `ROADMAP.md` 的 checkbox 是否如實更新
- 新增或更新的 report 路徑是否正確
- 重要表格是否有資料來源
- 若整個計畫已完成，report 是否已有 `結果`、`結論`、`討論`、`最終結論`
- 是否仍能從 `ROADMAP.md` 回到對應 report

完成條件：計畫執行狀態、結果文件與證據路徑彼此一致。
