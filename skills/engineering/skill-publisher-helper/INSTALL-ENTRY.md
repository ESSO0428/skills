# 安裝入口

若使用者接受參考 `mattpocock/skills` 的入口寫法，README 應至少補這兩段：

## 1. 用 skills.sh 安裝

```bash
npx skills@latest add owner/repo
```

這裡的 `owner/repo` 只需要 GitHub repo 位址。

## 2. 用 Claude plugin marketplace 安裝

```text
/plugin marketplace add owner/repo
/plugin install owner-skills@owner
```

這裡同樣只需要 GitHub repo 位址；但要能照這段直接使用，repo root 還必須已有：
- `.claude-plugin/marketplace.json`
- `.claude-plugin/plugin.json`

## 命名慣例

若沿用 `mattpocock/skills` 的風格：
- repo 名：`skills`
- marketplace 名：GitHub owner
- plugin 名：`<owner>-skills`

## 既有架構時的處理

若使用者已有自己的打包架構，不要直接覆蓋。先問：
- 是否要補上這種 README 安裝入口
- 是否要把 `.claude-plugin` manifests 一起補齊
- 是否要同步收斂 plugin / marketplace / repo 的命名
