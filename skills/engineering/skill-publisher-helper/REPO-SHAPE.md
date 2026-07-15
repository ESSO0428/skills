# Repo 形狀

這個 skill 預設重現的打包形狀如下：

```text
repo-root/
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
└── skills/
    ├── engineering/
    │   ├── README.md
    │   └── <skill-name>/
    │       ├── SKILL.md
    │       ├── README.md
    │       ├── agents/
    │       │   └── openai.yaml
    │       └── 其他 support .md
    └── productivity/
        ├── README.md
        └── <skill-name>/
            ├── SKILL.md
            ├── README.md
            ├── agents/
            │   └── openai.yaml
            └── 其他 support .md
```

## 頂層檔案

- `README.md`：repo 入口、Quickstart、安裝方式、skills 總覽
- `AGENTS.md`：跨平台、跨 agent 工具共通的規則與維護慣例
- `CLAUDE.md`：Claude Code 專屬內容，例如 plugin marketplace 安裝與 `.claude-plugin` manifests 說明
- `.claude-plugin/plugin.json`：plugin 自身資訊與 skills 清單
- `.claude-plugin/marketplace.json`：marketplace 名稱、plugin 名稱與顯示資訊

`AGENTS.md` 與 `CLAUDE.md` 應互相超連結：
- `CLAUDE.md` 指向 `AGENTS.md`，說明共通慣例請查看 `AGENTS.md`
- `AGENTS.md` 指向 `CLAUDE.md`，說明 Claude Code marketplace 安裝與專屬功能請查看 `CLAUDE.md`

## bucket

- `skills/engineering/`：研究、工程、workflow、規劃、重構、review 類 skills
- `skills/productivity/`：表達、溝通、整理、輕量工作輔助類 skills

每個 bucket 至少要有自己的 `README.md`，把包含的 skills 列出來。

## 每個 skill 目錄

至少應有：
- `SKILL.md`
- `README.md`
- `agents/openai.yaml`

視需要再加 support `.md`。

## 一致性規則

逐一檢查：
- `SKILL.md` frontmatter 是否完整
- user-invoked skill 是否有 `disable-model-invocation: true`
- `agents/openai.yaml` 是否有對應的 `display_name`、`short_description`
- user-invoked skill 的 `agents/openai.yaml` 是否有 `policy.allow_implicit_invocation: false`
- README、bucket README、plugin manifest 是否都列到同一批 skills
- `AGENTS.md` 與 `CLAUDE.md` 的內容分工是否正確、互相連結是否存在
