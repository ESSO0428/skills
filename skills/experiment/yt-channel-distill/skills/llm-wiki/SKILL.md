---
name: llm-wiki
disable-model-invocation: true
description: 把已驗證的逐字稿、候選原則與 coverage 紀錄編譯成可搜尋、可重建且保留 provenance 的 Markdown Wiki。
---

# LLM Wiki

把已驗證來源編譯成低成本、可重建的 Markdown 導航層；Wiki 不是逐字稿、影片、manifest 或正式 Skill 的替代品。

## 何時啟用

- 一支影片的 canonical source chunks、candidate 或 coverage 狀態新增／修正後。
- 需要查詢主題、原則卡、缺口或 provenance，而不想先載入全部逐字稿時。
- 需要驗證 Wiki 是否仍與 canonical JSON 一致時。

不要把標題猜測、AGY 摘要或未封存的模型推論直接編入 Wiki。

## 固定契約

1. 輸入真相是 candidates、coverage、manifest、transcript 與 source chunks；只讀取它們。
2. 每張 principle card 保留 video ID、URL、時間戳、transcript type、source chunk、evidence level、適用範圍、限制與缺口。
3. 編譯結果包含 `index.md`、topic pages、principle pages、`log.md` 與 input-hash `state.json`。
4. 相同輸入 hash 不重複寫入 log；輸入有新增或修正才建立新的 log entry。編譯失敗時保留既有 Wiki 與所有來源。
5. 回答問題時由卡片導航回原始 chunk；不得從摘要自行補出未被證據支持的結論。

## 操作

指令一律寫成 `uv run --project <collection-root> python <collection-root>/skills/llm-wiki/scripts/<script>.py ...`，`<collection-root>` 是含 `pyproject.toml` 的集合根（從本檔往上兩層）。先執行 `compile_wiki.py --help` 與 `validate_wiki.py --help`；安裝後先跑 `smoke_test.py --json` 做暫存 fixture 的 bootstrap／compile／validate／冪等性檢查。完整參數、範例與路徑見 [README.md](README.md)；schema 與政策見：

- [schema.md](references/schema.md)
- [provenance-policy.md](references/provenance-policy.md)
- [karpathy-method.md](references/karpathy-method.md)

## Completion

先以 `wiki_gate.py --help` 判斷影片終態：`READY` 編譯、`READY_PARTIAL` 帶 gap 編譯、明確失敗或 AGY blocked 留下 blocked event。多支影片一次同步時使用 `wiki_sync.py`，它只做一個 manifest-level gate pass，最多觸發一次 derived Wiki compile。完成條件是 compiler exit code 為 0、validator 回報 `PASS`，且 coverage gaps 仍可在 topic page 找到。集合 CLI 的 `download`／`transcribe`（加 `--sync-wiki`） 會另外把同一決策寫入 manifest 的衍生 `wiki_gate` 欄位與 append-only gate log；此欄位不屬於 canonical source，且不會改變 record fingerprint，重跑仍然冪等。
當補證 packet 已封存時，以 `wiki_sync.py --manifest <p> --log <p> --evidence-dir <dir>` 一次掃描 `*.packet.json`；成功 AGY packet 只記 `event_type=evidence_packet`／`action=RECORD_SUPPLEMENT`，blocked packet 記 `AGY_BLOCKED`／`RECORD_BLOCKED`，兩者都保留 packet hash、merge decision 與 manifest provenance，不覆寫 canonical transcript。
若 packet 的 `coverage_status` 為 `PARTIAL_DURATION_MISMATCH`，或 AGY 回報 duration 超出 canonical duration 容許差異，gate 仍只記錄 supplemental event，但附加 `supplement_review_required=true` 與原因；不得把該 packet 當作整片軌道完整性的證明。

## Boundaries

- 不下載影片、跑 ASR、呼叫 AGY 或改寫 canonical inputs。
- 不把 Wiki 卡片當作完整影片理解；來源不足就保留 gap／blocked event。
