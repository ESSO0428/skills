# CLAUDE.md 與 AGENTS.md 分工

若本次會建立或更新 repo root 指南文檔，預設同時處理兩份文件：

- `AGENTS.md`：跨平台、跨 agent 工具共通的規則與慣例
- `CLAUDE.md`：Claude Code 專屬內容，例如 marketplace 安裝、`.claude-plugin` manifests、或其他只對 Claude Code 有意義的說明

## 固定做法

- 建立或更新 `AGENTS.md`
- 建立或更新 `CLAUDE.md`
- 在 `CLAUDE.md` 中用超連結指向 `AGENTS.md`，說明共通慣例請查看 `AGENTS.md`
- 在 `AGENTS.md` 中用超連結指向 `CLAUDE.md`，說明 Claude Code marketplace 安裝與其專屬功能請查看 `CLAUDE.md`

## 內容分工

### `AGENTS.md`

放：
- bucket 規則
- skill frontmatter / `agents/openai.yaml` 規則
- README / bucket README / manifest 的同步要求
- user-invoked / model-invoked 的整體慣例
- 其他不依賴 Claude Code 的共通維護規則

### `CLAUDE.md`

放：
- Claude Code plugin marketplace 安裝方式
- `.claude-plugin/plugin.json` 與 `.claude-plugin/marketplace.json` 的維護提醒
- 只對 Claude Code 有意義的專屬功能或操作

## 既有文件時的處理

若 repo root 已存在 `AGENTS.md` 或 `CLAUDE.md`：
- 先讀目前內容
- 保留仍有價值的內容
- 依內容性質重新分配到共通層或 Claude 專屬層
- 不要把兩邊都寫成重複的總則

## 完成後要交代

完成後應明確告知：
- `AGENTS.md` 是否已建立或更新
- `CLAUDE.md` 是否已建立或更新
- 兩份文檔是否都已互相連結
