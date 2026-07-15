# AGENTS

Claude Code marketplace 安裝與 Claude Code 專屬功能，請查看 [CLAUDE.md](./CLAUDE.md)。

這個套件中的 skills 依 bucket 放在 `skills/` 下：

- `engineering/` — 研究與工程工作流 skills
- `productivity/` — 溝通與輕量工作流輔助 skills

維護規則：

- 每個 skill 都要出現在對應 bucket 的 `README.md` 中，且 skill 名稱要連到它的 `SKILL.md`。
- 頂層 `README.md` 應列出所有已包含的 skills；若同時存在兩種類型，則依 **User-invoked** 與 **Model-invoked** 分組。
- 若新增、移除、重新命名，或大幅調整某個 skill，至少同步更新：
  - 頂層 `README.md`
  - 對應 bucket 的 `README.md`
  - `.claude-plugin/plugin.json`
  - `.claude-plugin/marketplace.json`
- bucket 的責任要清楚，不要把 engineering workflow skills 混進 `productivity/`，反之亦然。
- 若 skill 內含相對路徑範例，必須確認那些連結從範例預期落點出發時仍然有效。
- 每個 skill 的 `SKILL.md` 都應有 frontmatter。至少包含 `name` 與 `description`；若是 user-invoked，還要加 `disable-model-invocation: true`。
- `SKILL.md` 的 frontmatter 比照 `mattpocock/skills`：user-invoked 的 `description` 寫成給人讀的一句話摘要；model-invoked 的 `description` 則寫成較偏 trigger / symptom 的使用時機。
- 目前這個套件中已收錄的 skills 一律先維持為 user-invoked；未來若新增 skill 是否允許自動觸發，再逐一判斷。
- 每個 skill 都應在自己的目錄下提供 `agents/openai.yaml`，用來放 Codex / OpenAI 端的 `display_name`、`short_description`，以及 user-invoked skill 需要的 `policy.allow_implicit_invocation: false`。
- 若 `SKILL.md` 是 user-invoked（如 `disable-model-invocation: true`），則 `agents/openai.yaml` 也要同步設 `policy.allow_implicit_invocation: false`；兩邊不可失配。
- `README.md`、bucket README 與其他 support `.md` 不需要為了模仿結構而額外加 frontmatter；比照 `mattpocock/skills`，主要由 `SKILL.md` 承擔這層 metadata。
- 命名慣例：repo 用 `skills`，marketplace 用 GitHub owner，plugin 用 `<owner>-skills`。
- 請保持 repo root 結構乾淨，讓這個 skills 套件能直接作為可發佈、可安裝的 GitHub repo 使用。
