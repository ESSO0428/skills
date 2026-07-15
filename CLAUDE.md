# CLAUDE

這個 repo 的共通規則與跨平台慣例，請查看 [AGENTS.md](./AGENTS.md)。

## Claude Code 專屬內容

### Claude plugin marketplace 安裝

在 Claude Code 內可使用：

```text
/plugin marketplace add esso0428/skills
/plugin install esso0428-skills@esso0428
```

### `.claude-plugin` manifests

這個 repo 使用：
- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

來提供 Claude Code plugin marketplace 的安裝入口。

若新增、移除、重新命名，或大幅調整某個已發佈 skill，除了遵守 [AGENTS.md](./AGENTS.md) 內的共通維護規則，也要同步確認：
- `plugin.json` 的 skills 清單是否正確
- `marketplace.json` 的 plugin 名稱、顯示名稱與說明是否正確

### Claude Code 專屬提醒

- `CLAUDE.md` 只放對 Claude Code 有意義的內容。
- 共通規則不要重複寫在這裡，改放到 [AGENTS.md](./AGENTS.md)。
