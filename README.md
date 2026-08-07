# 研究與工程工作流 Skills

<!--toc:start-->
- [研究與工程工作流 Skills](#研究與工程工作流-skills)
  - [快速開始（Quickstart）](#快速開始quickstart)
    - [用 skills.sh 安裝](#用-skillssh-安裝)
    - [用 Claude plugin marketplace 安裝](#用-claude-plugin-marketplace-安裝)
  - [結構](#結構)
  - [內含 skills](#內含-skills)
    - [明確呼叫（User-invoked）](#明確呼叫user-invoked)
  - [Third-party skill collections](#third-party-skill-collections)
    - [Superpowers](#superpowers)
  - [備註](#備註)
<!--toc:end-->

這是一個可安裝的 Skills 套件，用來承載可重複使用的 agent skills，重點放在研究迭代、實驗追蹤、ROADMAP 計畫執行，以及讓輸出更適合人閱讀的工作流。

## 快速開始（Quickstart）

### 用 skills.sh 安裝

```bash
npx skills@latest add esso0428/skills
```

### 用 Claude plugin marketplace 安裝

```
/plugin marketplace add esso0428/skills
/plugin install esso0428-skills@esso0428
```

## 結構

- [`skills/engineering`](./skills/engineering/README.md) — 放實驗工作流、ROADMAP 維護，以及研究 / 工程整理類 skills
- [`skills/productivity`](./skills/productivity/README.md) — 放輸出可讀性與較輕量的工作流輔助 skills
- [`skills/collection`](./skills/collection/) — 收錄其他作者 / 其他專案的第三方 skills，每個來源放在一個子目錄，並保持 upstream 原樣（目前有 [`superpowers/`](./skills/collection/superpowers/)）

## 內含 skills

### 明確呼叫（User-invoked）

- **[roadmap-track-and-refactor](./skills/engineering/roadmap-track-and-refactor/SKILL.md)** — 把 `ROADMAP.md` 維持成主看板，將深細節移到 `docs/roadmap*` / `docs/reports*`，保留 traceability，並乾淨地歸檔已完成方向。
- **[executing-roadmap-plan](./skills/engineering/executing-roadmap-plan/SKILL.md)** — 按既有 `ROADMAP.md` 計畫執行，並如實更新 checkbox、report 與 evidence。
- **[skill-publisher-helper](./skills/engineering/skill-publisher-helper/SKILL.md)** — 把一組 skills 打包成可安裝 repo，或重整既有 skills repo 的入口與結構。
- **[talk-human](./skills/productivity/talk-human/SKILL.md)** — 把技術內容改寫成更精簡、結構更清楚、也更適合人閱讀的說明。

## Third-party skill collections

這裡收錄其他作者 / 其他專案發佈的第三方 skills，放在 [`skills/collection/`](./skills/collection/) 下，依來源放各子目錄，並保持 upstream 原樣不改寫。

### Superpowers

精選自 [obra/superpowers](https://github.com/obra/superpowers) 的三個 skills。完整 Superpowers 是一套較完整的 agentic software-development methodology，涵蓋 brainstorming、implementation planning、TDD、debugging、verification、code review、subagent-driven development 與 branch / workflow management 等面向；不過完整 workflow 對我的日常使用情境來說較為龐大，因此這個 repository 並不重新收錄完整 Superpowers，只精選我實際最需要的幾個 composable skills，作為較輕量的 curated subset。

收錄的 skills：

- **[brainstorming](./skills/collection/superpowers/brainstorming/SKILL.md)** — 在實作前釐清需求、提出必要問題、比較不同方案，並把討論收斂成 design / spec。
- **[writing-plans](./skills/collection/superpowers/writing-plans/SKILL.md)** — 根據既有 spec / requirements，產出具體且可執行的 implementation plan：指定需要建立或修改的檔案、定義 interfaces、拆分 implementation tasks、提供實作步驟，並包含 RED → GREEN 的 targeted testing / implementation 步驟。
- **[using-git-worktrees](./skills/collection/superpowers/using-git-worktrees/SKILL.md)** — 在需要隔離開發環境時建立或使用 Git worktree，偵測既有 worktree / isolation、選擇適當位置、必要時建立隔離的 worktree，讓 feature、experiment 或其他工作與目前 working tree 分離。

這三個 skills 是 upstream 原始副本，因此內容仍可能提及完整 Superpowers 中其他未包含於本 curated subset 的 skills；本 repository 不因此自動提供那些額外的 skills 或完整 Superpowers workflow。

建議一次一起安裝這三個 skills：

```bash
npx skills@latest add esso0428/skills \
  --skill brainstorming \
  --skill writing-plans \
  --skill using-git-worktrees
```

也可以只安裝其中一個，例如: `brainstorming` 或是 `writing-plans` (使用 `--skill writing-plans`)
```bash
npx skills@latest add esso0428/skills --skill brainstorming
```

Upstream：[obra/superpowers](https://github.com/obra/superpowers)

Synced from commit: `44c9b2d6e889982ac18c27d05a19fefe335194e1`（含 `LICENSE`、`skills/brainstorming`、`skills/writing-plans`、`skills/using-git-worktrees`）

## 備註

- `roadmap-track-and-refactor` 與 `skill-publisher-helper` 都是較完整的 workflow skills，內含 reference 檔與固定整理方法。
- `executing-roadmap-plan` 則是刻意保持精簡的 execution skill，用來補強 ROADMAP 執行時的 checkbox / report 紀律。
- `talk-human` 也刻意保持很小，方便和其他 skills 組合使用。
- 若這個套件之後繼續擴充，頂層 `README.md` 應維持簡短，把細節往 bucket README、skill 自己的文件，或正式發佈設定下放。
