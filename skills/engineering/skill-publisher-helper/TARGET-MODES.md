# 目標模式

先分清楚這次是在哪一種打包情境：

## 1. 新建泛用工具包 repo

適用於：
- 使用者想把多個可重用 skills 整成自己的通用工具箱
- repo 名稱就直接叫 `skills`

先確認：
- GitHub owner 是誰
- 是否直接採用 `skills` 作為 repo 名
- 哪些 skill 要先納入第一版

## 2. 新建某領域專用的 skills repo

適用於：
- 使用者只想打包某個特定領域，例如 research、design、ops、workflow
- repo 名稱不一定叫 `skills`

先確認：
- repo 名稱
- 這組 skills 的領域邊界
- 是否仍採用 `mattpocock/skills` 的 README 與 plugin 入口風格

## 3. 已有本地 skills repo

適用於：
- 使用者已有資料夾或 repo root
- 希望直接在現有目錄中重整

先確認：
- repo root 的本地路徑
- 是否可以改動既有 README / CLAUDE / manifests
- 哪些既有內容要保留

## 4. 已有 GitHub 上的 skills repo

適用於：
- 使用者直接提供 GitHub repo URL
- 希望整理遠端 repo 的現有內容

先確認：
- GitHub URL
- 是否允許先下載到本地整理
- 是否允許整理完成後 push 回遠端
- 若目前環境禁止 git 寫入，是否改成只輸出本地整理結果或 handoff

## 既有架構時要額外問的問題

若目標 repo 已有自己的打包架構，先問：
- 是否要維持現有架構
- 是否要參考 `mattpocock/skills` 的形狀重整
- 是否至少要補上 `skills.sh` 與 `Claude plugin marketplace` 的安裝入口
