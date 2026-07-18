# executing-roadmap-plan

照既有 `ROADMAP.md` 計畫執行，並在執行過程中維持 checkbox、report 與 evidence 紀律。

## 這個 skill 做什麼

這個 skill 用來處理「計畫已經寫在 `ROADMAP.md`，現在要照它執行」的情境。

它特別關心：
- checkbox 要如實更新
- 正式結果要落到 `docs/reports/*.md`
- 重要表格要能追回資料來源
- 計畫真的完成時，report 要有完整論述

## 什麼時候適合使用

當你需要：
- 按既有 `ROADMAP.md` checklist 推進工作
- 在執行過程中同步更新進度
- 把正式結果整理進 report
- 避免只勾 checkbox 卻沒留下可追溯證據

這是一個 user-invoked skill。它偏向 execution discipline，而不是 `ROADMAP.md` 的結構重整或 archive 判斷。

## 檔案地圖

- [`SKILL.md`](./SKILL.md) — 主流程
- [`CHECKBOX-DISCIPLINE.md`](./CHECKBOX-DISCIPLINE.md) — 何時能勾、何時不能勾
- [`REPORT-REQUIREMENTS.md`](./REPORT-REQUIREMENTS.md) — report 與資料來源規則
- [`COMPLETION-RULES.md`](./COMPLETION-RULES.md) — 何時可視為整個計畫已完成
- [`agents/openai.yaml`](./agents/openai.yaml) — 顯示名稱與 user-invoked 設定

## 備註

- 這個 skill 刻意保持精簡。
- `ROADMAP.md` 的 refactor、archive、索引與分層規則，仍交給 `roadmap-track-and-refactor`。
