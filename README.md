# 研究與工程工作流 Skills

<!--toc:start-->
- [研究與工程工作流 Skills](#研究與工程工作流-skills)
  - [快速開始（Quickstart）](#快速開始quickstart)
    - [用 skills.sh 安裝](#用-skillssh-安裝)
    - [用 Claude plugin marketplace 安裝](#用-claude-plugin-marketplace-安裝)
  - [結構](#結構)
  - [內含 skills](#內含-skills)
    - [明確呼叫（User-invoked）](#明確呼叫user-invoked)
    - [自動觸發（Model-invoked）](#自動觸發model-invoked)
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
- [`skills/collection`](./skills/collection/) — 收錄其他作者 / 其他專案的第三方 skills，每個來源放在一個子目錄，原則上保持 upstream；若 curated subset 需要極小的 compatibility adjustment，會在對應 skill 與 README 中明確標示（目前有 [`superpowers/`](./skills/collection/superpowers/)）

## 內含 skills

### 明確呼叫（User-invoked）

- **[roadmap-track-and-refactor](./skills/engineering/roadmap-track-and-refactor/SKILL.md)** — 把 `ROADMAP.md` 維持成主看板，將深細節移到 `docs/roadmap*` / `docs/reports*`，保留 traceability，並乾淨地歸檔已完成方向。
- **[executing-roadmap-plan](./skills/engineering/executing-roadmap-plan/SKILL.md)** — 按既有 `ROADMAP.md` 計畫執行，並如實更新 checkbox、report 與 evidence。
- **[skill-publisher-helper](./skills/engineering/skill-publisher-helper/SKILL.md)** — 把一組 skills 打包成可安裝 repo，或重整既有 skills repo 的入口與結構。
- **[talk-human](./skills/productivity/talk-human/SKILL.md)** — 把技術內容改寫成更精簡、結構更清楚、也更適合人閱讀的說明。

### 自動觸發（Model-invoked）

agent 遇到符合的情境時會自動使用，也可以明確呼叫。

- **[data-repo-gitignore](./skills/engineering/data-repo-gitignore/SKILL.md)** — 為資料型 / ML repo 規劃 `.gitignore`：資料類目錄各自宣告保留清單、root 用副檔名全域攔截大檔，並以 `git check-ignore` 實測驗證。

## Third-party skill collections

這裡收錄其他作者 / 其他專案發佈的第三方 skills，放在 [`skills/collection/`](./skills/collection/) 下，依來源放各子目錄，原則上保持 upstream 原樣；若 curated subset 需要極小的 compatibility adjustment，會在對應 skill 與 README 中明確標示。目前唯一有 local compatibility adjustments 的第三方 skill 是 Superpowers `writing-plans`。

### Superpowers

來源：[`obra/superpowers`](https://github.com/obra/superpowers)

完整 Superpowers 提供一套較完整的 agentic software-development workflow，涵蓋 brainstorming、implementation planning、TDD、debugging、verification、code review、subagent orchestration、branch / worktree workflow 等。

這裡只收錄目前較常使用、且適合獨立組合的三個 skills：

- **[brainstorming](./skills/collection/superpowers/brainstorming/SKILL.md)** — 在開始實作前釐清需求、限制與設計方向，透過問題與方案比較逐步收斂成 design / spec。
- **[writing-plans](./skills/collection/superpowers/writing-plans/SKILL.md)** — 根據既有 spec / requirements，產出具體且可執行的 implementation plan：指定需要建立或修改的檔案、定義 interfaces、拆分 implementation tasks、提供實作步驟，並包含 RED → GREEN 的 targeted testing / implementation 步驟。
- **[using-git-worktrees](./skills/collection/superpowers/using-git-worktrees/SKILL.md)** — 在需要隔離開發環境時建立或使用 Git worktree，偵測既有 worktree / isolation、選擇適當位置、必要時建立隔離的 worktree，讓 feature、experiment 或其他工作與目前 working tree 分離。

> [!NOTE]
> `brainstorming` 與 `using-git-worktrees` 保持 upstream 原樣。
>
> `writing-plans` 僅包含少量、明確標示的 local compatibility overrides，目的有兩項：
>
> 1. **Optional execution handoff** — upstream 會將 `subagent-driven-development` / `executing-plans` 作為 required execution sub-skills；本 curated subset 未收錄它們，因此改為 optional execution helpers。它們若存在，只是可用的 execution options 之一，不具有高於目前 agent 或 host framework 原生 execution / delegation capabilities 的預設優先權。
> 2. **Skill-name compatibility** — referenced skills 依可用性解析，優先嘗試 `superpowers:<name>`，再嘗試純 `<name>`，兩者皆不可用時才視為 unavailable。這個順序只用於解析 matching skill identity，不代表 execution priority。
>
> 實際 execution approach 由 implementation plan、使用者指示、目前可用能力，以及 host framework 自己的 routing / delegation policy 決定；可以使用 matching execution skill、目前 agent 的原生能力、host framework 的 subagent / delegation 機制，或 direct execution。缺少某個 referenced skill 時不會因此自動搜尋或安裝，也不會阻塞 workflow。
>
> `writing-plans/SKILL.md` 中的 local differences 以 `<!-- LOCAL OVERRIDE -->` 系列 marker 明確標示，方便未來與 upstream 同步。除這些 compatibility adjustments 外，其餘內容維持 upstream behavior；因此三個 skills 仍可能提及完整 Superpowers 中未包含於本 curated subset 的其他能力，本 repository 不因此自動提供完整 Superpowers workflow。

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

若想直接使用上游最新版，也可以改以 upstream 套件安裝（裝的是 `obra/superpowers` 當下最新版，而非本 repo 記錄的快照 commit）：

```bash
npx skills@latest add obra/superpowers \
  --skill brainstorming \
  --skill writing-plans \
  --skill using-git-worktrees
```

Upstream：[obra/superpowers](https://github.com/obra/superpowers)

Synced from commit: `44c9b2d6e889982ac18c27d05a19fefe335194e1`（含 `LICENSE`、`skills/brainstorming`、`skills/writing-plans`、`skills/using-git-worktrees`）

## 備註

- `roadmap-track-and-refactor` 與 `skill-publisher-helper` 都是較完整的 workflow skills，內含 reference 檔與固定整理方法。
- `executing-roadmap-plan` 則是刻意保持精簡的 execution skill，用來補強 ROADMAP 執行時的 checkbox / report 紀律。
- `talk-human` 也刻意保持很小，方便和其他 skills 組合使用。
- 若這個套件之後繼續擴充，頂層 `README.md` 應維持簡短，把細節往 bucket README、skill 自己的文件，或正式發佈設定下放。
