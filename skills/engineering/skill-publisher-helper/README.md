# skill-publisher-helper

把一組 skills 整理成可安裝 repo，並在新 repo、既有本地 repo、既有 GitHub repo 之間做正確分支判斷。

## 這個 skill 做什麼

這個 skill 協助把 skills 打包成類似 `mattpocock/skills` 那樣可維護、可安裝的 repo。

重點包含：

- 判斷是新建 repo 還是重整既有 repo
- 區分泛用 `skills` 工具包與領域專用 skills repo
- 若已有 GitHub repo，先問是否允許下載、整理並 push 回去
- 建立或整理 `README.md`、`AGENTS.md`、`CLAUDE.md`、bucket README、skill 目錄與 `.claude-plugin` manifests
- 將共通規則寫進 `AGENTS.md`，將 Claude Code 專屬內容寫進 `CLAUDE.md`，並讓兩份文檔互相超連結
- 若使用者不想整包重構，則只在既有架構上局部補齊 install 入口、manifests 或 skill metadata
- 在 README 入口補上 `skills.sh` 與 `Claude plugin marketplace` 的安裝說明
- 在打包完成後補上安裝、重裝與可用性驗證指引

## 什麼時候適合使用

當你需要：

- 把零散 skills 整成一個 repo
- 把現有 skills 目錄重整成較穩定的 package 架構
- 將既有技能庫補齊安裝入口與 plugin manifests
- 讓 skills repo 更接近 `mattpocock/skills` 的維護方式

這是一個 user-invoked skill。它適合在你已經決定要整理或發佈一組 skills 時使用，而不是單純修改某個單一 skill 的一句文案。

## 檔案地圖

- [`SKILL.md`](./SKILL.md) — 主流程
- [`TARGET-MODES.md`](./TARGET-MODES.md) — 新 repo / 舊 repo / GitHub URL 的分支與提問重點
- [`REPO-SHAPE.md`](./REPO-SHAPE.md) — skills repo 的固定形狀
- [`INSTALL-ENTRY.md`](./INSTALL-ENTRY.md) — README 安裝入口與命名規則
- [`CLAUDE-AGENTS-SPLIT.md`](./CLAUDE-AGENTS-SPLIT.md) — `AGENTS.md` 與 `CLAUDE.md` 的固定分工
- [`VERIFY-INSTALL.md`](./VERIFY-INSTALL.md) — 打包完成後如何驗證安裝與可用性，內含可直接貼給使用者的模板

## 備註

- 若使用者已有既有架構，先問是否要參考 `mattpocock/skills` 重整。
- 若提供的是 GitHub URL，先確認是否允許下載整理與 push 回遠端。
- 若目前環境不允許 git 寫入，應改成整理本地副本並交代剩餘步驟。
