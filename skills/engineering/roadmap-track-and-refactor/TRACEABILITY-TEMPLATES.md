# Traceability 模板

目標：讓保留在主看板、摘要層、證據層的資訊都能一路往下追回更完整的版本。

## 1. `ROADMAP.md` 入口模板

`ROADMAP.md` 只放入口，不放深細節。

```md
- ✅ `某實驗`：一句話結論。
  - roadmap: [某 roadmap](docs/roadmap/2026-07-12_example.md)
  - report: [某 report](docs/reports/2026-07-12_example_report.md)

- 🗂️ `某實驗`：一句話結論。
  - roadmap: [某 archive roadmap](docs/roadmap/archive/2026-07-06_example.md)
  - report: [某 archive report](docs/reports/archive/2026-07-06_example_report.md)
```

規則：
- 至少要能追到一份 `docs/roadmap*.md` 或 `docs/reports*.md`
- `✅` 用於「已完成，但仍有決策價值」的條目
- `🗂️` 用於「已完成，且已歸檔 / 暫不主推」的條目
- `✅` 的 roadmap 入口優先追到 `docs/roadmap/*.md`
- `🗂️` 的 roadmap 入口優先追到 `docs/roadmap/archive/*.md`
- 若主看板保留了暫時表格，表下方仍應留往 `docs/reports` 的超連結

## 2. `docs/roadmap/*.md` 摘要模板

摘要層可以放壓縮版，但要能追回完整報告。

```md
## 簡短摘要表格

| setting | MRR_avg | 詳細報告 |
|---|---:|---|
| best new_mlp | 0.225 | [report](../reports/2026-07-08_example_report.md) |
```

若整張表共用同一份報告，也可在表下方統一寫：

```md
- 詳細報告：[某 report](../reports/2026-07-08_example_report.md)
```

## 3. `docs/roadmap/archive/*.md` 摘要模板

archive 摘要也可以放壓縮版，但相對路徑要從 `docs/roadmap/archive/` 出發。

```md
## 簡短摘要表格

| setting | MRR_avg | 詳細報告 |
|---|---:|---|
| best new_mlp | 0.225 | [report](../../reports/archive/2026-07-08_example_report.md) |
```

若整張表共用同一份報告，也可在表下方統一寫：

```md
- 詳細報告：[某 report](../../reports/archive/2026-07-08_example_report.md)
```

規則：
- 壓縮版要保留主要結論、代表點與下一步判斷
- 壓縮版不能成為唯一保留處；完整版仍要在 `docs/reports*`

## 4. `docs/reports/*.md` / `docs/reports/archive/*.md` 證據模板

重要數據表應盡量直接帶 `資料來源` 欄。

```md
| Split | Batch | MRR_avg | 資料來源 |
|---|---:|---:|---|
| offspring-level | 16384 | 0.328 | `runs/.../best.json` |
| PNIC | 16384 | 0.326 | `runs/.../best.json` |
```

若一整張表真的共用同一來源，才允許改成表下方統一註記：

```md
- 資料來源：`runs/.../summary.csv`
```

規則：
- 只要表格在支撐主要結論，就要能一路追回 raw file path
- 若是比較表，必要時可在 `資料來源` 欄中放多個路徑，或在相鄰文字逐列補充

## 5. 壓縮版與完整版共存

壓縮後至少保留兩層：
- 壓縮版：`docs/roadmap/*.md` 或 `docs/roadmap/archive/*.md`
- 完整版：`docs/reports/*.md` 或 `docs/reports/archive/*.md`

不要讓 `ROADMAP.md` 或壓縮摘要成為唯一保存處。
