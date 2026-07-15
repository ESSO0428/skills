# 安裝與可用性驗證

打包完成後，不要只停在「檔案已整理完」。應再交代使用者如何確認 skill 真的可安裝、可載入、可觸發。

## 完成後至少要告知使用者的三個位置

每次完成打包後，至少明確列出：
- 原始 skill 或 skills source 目前在哪裡
- 打包後的 repo root 在哪裡
- 打包後的 skill 目錄在哪裡

若這次是整理既有 repo，也要明確說明：
- 哪些檔案是沿用既有內容
- 哪些檔案是這次新增或重寫的
- 若本次有處理 `AGENTS.md` 與 `CLAUDE.md`，也要說明兩份文檔是否都已建立或更新

## 常見安裝路徑

### Claude Code

- global：`~/.claude/skills/`
- local：`<project-root>/.claude/skills/`

### Pi / Codex / 其他 Agent Skills-compatible harnesses

- global：`~/.agents/skills/`
- local：`<project-root>/.agents/skills/`

若使用者要測單一 skill，通常是看對應的 `<skill-name>/` 子目錄是否出現在上述位置。

## repo root 與 git 初始化提醒

完成打包後，除了交代 repo root 路徑，也要提醒使用者後續在哪個目錄做 git 操作。

### 若 repo 尚未初始化 git

提醒使用者：
- 先 `cd` 到這次打包後的 repo root
- 在那個目錄自行執行 `git init`
- 後續在同一個 repo root 完成 `git commit` 後，再 `git push` 這個專案

### 若 repo 已初始化過 git

提醒使用者：
- 先 `cd` 到這次打包後的 repo root
- 在同一個 repo root 完成 `git commit`
- 然後再 `git push` 這個專案

## 若已 push 到 GitHub，建議做一次乾淨重裝測試

若使用者已把 repo push 到 GitHub，且 repo 結構已確認無誤，建議做一次乾淨重裝測試：
- 先刪掉 global / local 已安裝的 skill
- 再依正式安裝方式重新安裝
- 最後重開 agent CLI 或執行 `/reload`

這樣比較能確認 README 入口、repo 結構與 manifests 是真的可用，而不是只靠目前工作目錄中的殘留檔案剛好能用。

## Linux 用戶可直接給的刪除指令

若已知使用者是 Linux，可直接提供：

```bash
rm -rf ~/.claude/skills/<skill-name>
rm -rf ~/.agents/skills/<skill-name>
rm -rf .claude/skills/<skill-name>
rm -rf .agents/skills/<skill-name>
```

注意：
- 只刪除這次要重測的 skill 目錄，不要無差別刪整個 `skills/`
- 若使用者只測 global 或只測 local，就只給對應那幾條
- 若這次測的是整個 collection，也可改成刪除這次安裝出的那批 skill 子目錄

## 非 Linux 用戶

若不是 Linux，則不要硬給 `rm -rf`。改成直接列出應刪除的路徑，例如：
- `~/.claude/skills/<skill-name>`
- `~/.agents/skills/<skill-name>`
- `<project-root>/.claude/skills/<skill-name>`
- `<project-root>/.agents/skills/<skill-name>`

讓使用者自行用對應平台的方式刪除。

## 安裝方式

### 用 skills.sh 安裝整個 repo

```bash
npx skills@latest add owner/repo
```

若使用者只想測單一 skill，可另外視情況補：

```bash
npx skills@latest add owner/repo --skill=<skill-name>
```

### 用 Claude plugin marketplace 安裝

```text
/plugin marketplace add owner/repo
/plugin install owner-skills@owner
```

## 安裝後的 reload / 重啟提醒

安裝完成後，建議提醒使用者至少做其中一件：
- 重開 agent CLI
- 若支援，執行 `/reload`（例如 pi-agent）

最後再確認：
- skill 是否出現在 slash command / skills 清單中
- 能否真的被呼叫一次
- user-invoked skill 是否只在明確輸入名稱時出現

## 可直接貼給使用者的驗證模板

以下模板可在打包完成後，依實際 repo 名稱、owner、skill 名稱與路徑替換後直接貼給使用者：

```md
已完成打包。

### 目前檔案位置
- 原始 skills source：`<source-path>`
- 打包後 repo root：`<repo-root>`
- 這次新增 / 整理的 skill 目錄：`<skill-path-1>`、`<skill-path-2>`

### git 提醒
如果這個 repo 還沒初始化，請先：

```bash
cd <repo-root>
git init
```

之後在同一個 repo root 完成 `git commit`，再 `git push` 這個專案。

如果這個 repo 已經初始化過，則請先：

```bash
cd <repo-root>
```

再在該目錄完成 `git commit` 後 `git push` 即可。

### AGENTS / CLAUDE 文檔
如果這次有處理 `AGENTS.md` 與 `CLAUDE.md`，也請一併交代：
- `AGENTS.md` 是否已建立或更新
- `CLAUDE.md` 是否已建立或更新
- `CLAUDE.md` 是否已指向 `AGENTS.md`
- `AGENTS.md` 是否已指向 `CLAUDE.md`

### 常見安裝路徑
- Claude Code global：`~/.claude/skills/`
- Claude Code local：`<project-root>/.claude/skills/`
- Pi / Codex global：`~/.agents/skills/`
- Pi / Codex local：`<project-root>/.agents/skills/`

### 重新安裝測試
若你已經把 repo push 到 GitHub，建議做一次乾淨重裝測試。

如果你是 Linux，可先刪掉先前安裝的 skill：

```bash
rm -rf ~/.claude/skills/<skill-name>
rm -rf ~/.agents/skills/<skill-name>
rm -rf .claude/skills/<skill-name>
rm -rf .agents/skills/<skill-name>
```

如果不是 Linux，請改為手動刪除這些路徑中對應的 `<skill-name>` 目錄：
- `~/.claude/skills/<skill-name>`
- `~/.agents/skills/<skill-name>`
- `<project-root>/.claude/skills/<skill-name>`
- `<project-root>/.agents/skills/<skill-name>`

### 安裝方式
#### skills.sh
```bash
npx skills@latest add <owner>/<repo>
```

若只想測單一 skill，也可視情況改成：

```bash
npx skills@latest add <owner>/<repo> --skill=<skill-name>
```

#### Claude plugin marketplace
```text
/plugin marketplace add <owner>/<repo>
/plugin install <owner>-skills@<owner>
```

### 安裝後
安裝完成後，建議：
- 重開 agent CLI
- 或執行 `/reload`（若你的 agent 支援，例如 pi-agent）

最後請確認：
- skill 已出現在 slash command / skills 清單中
- skill 可以被實際呼叫一次
- 若它是 user-invoked，只有在你明確輸入名稱時才會出現
```
