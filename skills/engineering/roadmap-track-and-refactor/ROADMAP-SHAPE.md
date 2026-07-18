# ROADMAP 版型

`ROADMAP.md` 是主看板，不是完整報告。

## 主體順序

優先維持這個順序：
1. 最新、進行中的實驗條目
2. `## 已完成`
3. `## 未來可能發展方向`
4. 必要時補少量簡短的歷史 / 發展脈絡

## 進行中的條目

格式預設為：

```md
## 日期-實驗名
- [x] ...
- [ ] ...
```

規則：
- 最新條目放最上面
- checklist 是主要介面
- 狀態追蹤以 bullet checkbox 為主，結果用簡單表格呈現
- 可加一句話小節或暫時表格，但只在它真的能幫助最近幾輪實驗時保留
- 若內容太重，優先考慮把細節移到 `docs/`，而不是讓主看板持續膨脹
- 大量數據細節表格應移到 `docs/reports`，並在主看板留下超連結

## 已完成

格式預設為：

```md
- ✅ `實驗名`：一句話說明結果、為什麼仍有決策價值、下一步建議。
  - roadmap: [某 roadmap](docs/roadmap/2026-07-08_example.md)
  - report: [某 report](docs/reports/2026-07-08_example_report.md)

- 🗂️ `實驗名`：一句話說明結果、為什麼先不主推、避免重複踩坑的提醒。
  - roadmap: [某 archive roadmap](docs/roadmap/archive/2026-07-06_example.md)
  - report: [某 archive report](docs/reports/archive/2026-07-06_example_report.md)
```

規則：
- `✅` 表示「已完成，但仍有決策價值」，入口優先指向 `docs/roadmap/*.md`
- `🗂️` 表示「已完成，且已歸檔 / 暫不主推」，入口優先指向 `docs/roadmap/archive/*.md`
- 若某個 archive 主題的完整報告仍常被當成主證據引用，可讓 report 暫留 `docs/reports/*.md`；但 roadmap 入口圖示仍應用 `🗂️`
- 目的是讓使用者一眼看出哪些方向值得續看、哪些方向主要是避免再踩坑
- 這裡只留短結論與入口，不留深細節

## 未來可能發展方向

- 盡量留下系統化資訊，而不是零散提醒
- 表格只在真的有助於方向判斷時保留
- 若內容太多，優先考慮拆到 `docs/roadmap/` 或 `docs/reports/`

## 收斂檢查

每次重構後，`ROADMAP.md` 應比整理前更容易看出最近主線，且主看板承擔的深細節應比整理前更少。
