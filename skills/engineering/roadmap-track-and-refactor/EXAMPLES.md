# 範例

這裡放正例、反例與壓縮大表格的方法。

## `ROADMAP.md` 正例

```md
## 2026-07-12 某實驗
- [x] 產出 train table
- [x] 跑完 new_mlp
- [ ] 補報告

> 一句話小節：目前最好的條件是 x，仍待確認 y。

| Split | MRR_avg |
|---|---:|
| offspring-level | 0.328 |
| PNIC | 0.326 |
```

重點：
- checklist 在前
- 只留最近需要盯的簡單表格
- 深細節不塞在主看板

## `ROADMAP.md` 反例

```md
## 某實驗
- [x] ...

| 很大很長的表格 | ... |
| ... | ... |

很多段診斷、很多來源路徑、很多歷史比較全文都直接留在這裡。
```

問題：
- 主看板變成報告
- 最近進度被深細節淹沒
- 難以快速回顧最佳方向

## `ROADMAP.md` 的 `## 已完成` 正例

```md
## 已完成

- ✅ `固定 merged train 對照`：offspringlevel 有正向訊號，後續仍值得繼續用固定 test set 重跑。
  - roadmap: [某 roadmap](docs/roadmap/2026-07-12_example.md)
  - report: [某 report](docs/reports/2026-07-12_example_report.md)

- 🗂️ `new_mlp InfoNCE loss function 測試`：沒有穩定優於 mse，先保留供回查，暫不再擴大。
  - roadmap: [某 archive roadmap](docs/roadmap/archive/2026-07-06_example.md)
  - report: [某 archive report](docs/reports/archive/2026-07-06_example_report.md)
```

重點：
- `✅` 給仍有決策價值的已完成條目
- `🗂️` 給已歸檔或暫不主推的已完成條目
- icon 要和對應 roadmap 檔案位置一致

## `docs/roadmap/*.md` 正例

```md
# 2026-07-08 某主題

- status: done
- date: 2026-07-08

## 一句結論
- ...

## 原始進度追蹤
- [x] ...
- [x] ...

## 簡短摘要表格
| setting | MRR_avg |
|---|---:|
| best | 0.225 |

## 相關報告
- [某 report](../reports/2026-07-08_example_report.md)
```

## `docs/roadmap/archive/*.md` 正例

```md
# 2026-07-06 某方向

- status: archived
- date: 2026-07-06

## 一句結論
- ...

## 為什麼歸檔
- ...

## 原始進度追蹤
- [x] ...

## 相關報告
- [某 archive report](../../reports/archive/2026-07-06_example_report.md)
```

## 大表格壓縮建議

當表格太大、使用者只是想回顧方向時，先確認使用者是否接受壓縮，再優先壓成：
- 最好模型是誰
- 最好分數是多少
- 相比基線增減多少
- 哪幾個 split 最差 / 最值得看

範例：

原本：保留 20 列以上大表格。

壓縮後：

```md
- 這條線整體偏弱；最好的是 `new_mlp`。
- 最好分數：`offspring-level (b16384) MRR_avg=0.225`
- 後續更值得改做固定測試集，而不是繼續糾結這批資料。
```

同時保留：
- 壓縮版摘要 → `docs/roadmap/*.md` 或 `docs/roadmap/archive/*.md`
- 完整版數據 → `docs/reports/*.md` 或 `docs/reports/archive/*.md`

