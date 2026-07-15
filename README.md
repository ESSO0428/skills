# 研究與工程工作流 Skills

<!--toc:start-->
- [研究與工程工作流 Skills](#研究與工程工作流-skills)
  - [快速開始（Quickstart）](#快速開始quickstart)
    - [用 skills.sh 安裝](#用-skillssh-安裝)
    - [用 Claude plugin marketplace 安裝](#用-claude-plugin-marketplace-安裝)
  - [結構](#結構)
  - [內含 skills](#內含-skills)
    - [明確呼叫（User-invoked）](#明確呼叫user-invoked)
  - [備註](#備註)
<!--toc:end-->

這是一個可安裝的 Skills 套件，用來承載可重複使用的 agent skills，重點放在研究迭代、實驗追蹤，以及讓輸出更適合人閱讀的工作流。

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

## 內含 skills

### 明確呼叫（User-invoked）

- **[roadmap-track-and-refactor](./skills/engineering/roadmap-track-and-refactor/SKILL.md)** — 把 `ROADMAP.md` 維持成主看板，將深細節移到 `docs/roadmap*` / `docs/reports*`，保留 traceability，並乾淨地歸檔已完成方向。
- **[skill-publisher-helper](./skills/engineering/skill-publisher-helper/SKILL.md)** — 把一組 skills 打包成可安裝 repo，或重整既有 skills repo 的入口與結構。
- **[talk-human](./skills/productivity/talk-human/SKILL.md)** — 把技術內容改寫成更精簡、結構更清楚、也更適合人閱讀的說明。

## 備註

- `roadmap-track-and-refactor` 與 `skill-publisher-helper` 都是較完整的 workflow skills，內含 reference 檔與固定整理方法。
- `talk-human` 則刻意保持很小，方便和其他 skills 組合使用。
- 若這個套件之後繼續擴充，頂層 `README.md` 應維持簡短，把細節往 bucket README、skill 自己的文件，或正式發佈設定下放。
