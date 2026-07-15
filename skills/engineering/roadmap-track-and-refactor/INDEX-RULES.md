# INDEX 規則

當 `docs/` 內文件開始變多、難找、主題分散時，建立 `INDEX.md`。

## 適用位置

- `docs/roadmap/INDEX.md`
- `docs/reports/INDEX.md`
- 若 archive 目錄長大，也可建立 `docs/roadmap/archive/INDEX.md` 與 `docs/reports/archive/INDEX.md`

## 目標

索引的目標不是複製所有內容，而是用最少層級指出：
- 幾個主要方向
- 每個方向對應哪些文件
- 每份文件最短的用途說明

## 形狀

- 最上方先寫最基本說明
- 下方用少量 H2 表示主要方向
- H2 數量盡量少，能維持在 5 個內就不要擴張
- 每個 H2 下用少量 bullet 指向文件

格式範例：

```md
## 某方向
- [文件名](path.md): 一句超短用途說明
- [文件名](path.md): 一句超短用途說明
```

## 約束

- 主 bullet 盡可能少
- 每條描述都要短，像易懂書名，而不是摘要全文
- 若某個方向底下文件太多，代表該方向本身還需要再模組化
