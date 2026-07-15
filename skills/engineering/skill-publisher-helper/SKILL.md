---
name: skill-publisher-helper
description: 把一組 skills 打包成可安裝 repo 的助手。
disable-model-invocation: true
---

先把目標 repo 與工作模式說清楚，再按固定形狀整理 README、bucket、skill 目錄與 `.claude-plugin` manifests。

## 1. 先判斷這次要打包到哪裡

先詢問使用者目前是哪一種情況：
- 要新建一個泛用工具包 repo，名稱就叫 `skills`
- 要新建一個某領域專用的 skills repo，需另外命名
- 已有本地 skills repo，需要整理現有目錄
- 已有 GitHub 上的 skills repo，需要先下載再整理

若使用者提供的是 GitHub URL，先詢問是否允許你下載、整理，並在完成後 push 回遠端。若目前環境或專案規則不允許 git 寫入，明說限制，改成只整理本地副本或輸出 handoff。

讀 `TARGET-MODES.md`。

完成條件：已知道目標 repo 類型、repo 名稱或目錄位置、是否有 GitHub 遠端，以及是否允許處理遠端副本。

## 2. 判斷是新打包還是重整既有架構

若使用者已有自己的 skills repo 或既有打包架構：
- 先讀目前的 `README.md`、`CLAUDE.md`、`skills/`、`.claude-plugin/`
- 問使用者是否要參考 `mattpocock/skills` 的架構重整
- 若不重整整體架構，明確確認這次只補哪些東西，例如 install 入口、manifests、bucket README 或 skill metadata

若是新 repo，直接用固定形狀起步。

讀 `REPO-SHAPE.md` 與 `INSTALL-ENTRY.md`。

完成條件：已知道這次是從零建立、完整重整既有 repo，還是只在既有架構上局部補齊，且已知道哪些既有內容要保留、哪些要改寫。

## 3. 依選定範圍打包 repo

若使用者選擇完整參考 `mattpocock/skills` 或從零建立新 repo，就用固定方法整理：
- 建立或更新頂層 `README.md`
- 建立或更新 `AGENTS.md`
- 建立或更新 `CLAUDE.md`
- 在 `CLAUDE.md` 中用超連結指向 `AGENTS.md`，說明共通慣例請查看 `AGENTS.md`
- 在 `AGENTS.md` 中用超連結指向 `CLAUDE.md`，說明 Claude Code marketplace 安裝與其專屬功能請查看 `CLAUDE.md`
- 建立 `skills/engineering/README.md`、`skills/productivity/README.md`
- 把每個 skill 放進正確 bucket
- 確保每個 skill 目錄至少有 `SKILL.md`、`README.md`、`agents/openai.yaml`
- 補上 `.claude-plugin/plugin.json` 與 `.claude-plugin/marketplace.json`

若使用者明確要求保留既有架構，就不要硬套完整固定形狀；只在雙方已同意的範圍內補齊，例如：
- 補 `README.md` 的 install 入口
- 補 `.claude-plugin` manifests
- 補 bucket README
- 補 `SKILL.md` frontmatter 與 `agents/openai.yaml`
- 若有更新 repo root 指南，則補齊 `AGENTS.md` / `CLAUDE.md` 的分工與互連

若有既有 skill，逐一檢查：
- `SKILL.md` frontmatter
- `agents/openai.yaml`
- README 與 bucket README 是否列到它
- plugin manifest 的 skills 清單是否包含它

讀 `REPO-SHAPE.md` 與 `CLAUDE-AGENTS-SPLIT.md`。

完成條件：repo 已在使用者同意的範圍內完成整理；若是完整重整，則具備清楚的 skills root 結構；若是局部補齊，則已把承諾要補的部分補完；若本次碰到 repo root 指南，也已處理好 `AGENTS.md` 與 `CLAUDE.md` 的分工與互連。

## 4. 補上安裝入口

在 `README.md` 入口補上：
- `skills.sh` 安裝方式
- `Claude plugin marketplace` 安裝方式

若使用者採用 `mattpocock/skills` 風格，README 應直接寫出：
- `npx skills@latest add owner/repo`
- `/plugin marketplace add owner/repo`
- `/plugin install owner-skills@owner`

這兩種安裝方式都只需要 GitHub repo 位址；其中 Claude plugin 另需要 repo root 已具備 `.claude-plugin/marketplace.json` 與 `.claude-plugin/plugin.json`。

讀 `INSTALL-ENTRY.md`。

完成條件：README 已能作為 repo 入口，讓使用者直接照安裝說明使用。

## 5. 完成前核對與可用性驗證說明

逐項確認：
- repo 名稱、marketplace 名稱、plugin 名稱是否一致
- 頂層 README、bucket README、plugin manifest 是否都列到同一批 skills
- 每個 user-invoked skill 是否同時具備 `disable-model-invocation: true` 與 `policy.allow_implicit_invocation: false`
- 相對連結是否正確
- 若是既有 repo 重整，使用者是否已確認哪些內容保留、哪些內容改寫
- 若遠端 repo 因權限或規則無法 push，是否已明確交代剩餘手動步驟

另外，完成後還要明確告知使用者：
- 這次打包後的 repo root 在哪裡
- 這次打包後的 skill 目錄在哪裡
- 若 repo 尚未初始化 git，提醒使用者先 `cd` 到該 repo root，再自行執行 `git init`
- 若 repo 已初始化過 git，提醒使用者先 `cd` 到該 repo root，再在該目錄完成 `git commit` 後再 `git push`
- 若本次建立或更新了 `AGENTS.md` 與 `CLAUDE.md`，也要明確告知兩份文檔是否都已建立、內容分工是否正確、互相連結是否已補上
- 常見 global / local 安裝路徑在哪裡
- 若已 push 到 GitHub，是否建議先刪掉已安裝 skill 再重裝測試
- 若使用者是 Linux，可直接給 `rm -rf` 指令；其他平台則列出需刪除的路徑
- `skills.sh` 與 `Claude plugin marketplace` 的安裝方式
- 建議重開 agent CLI 或執行 `/reload`（如 pi-agent）後再確認 skill 是否可用

讀 `VERIFY-INSTALL.md`。

完成條件：repo 可被視為一個可安裝、可維護、可繼續擴充的 skills package，且使用者已拿到足夠的安裝、重裝與驗證說明。
