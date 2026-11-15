# llm-wiki skill

把 canonical candidates 與 coverage facts 編譯成可重建、可驗證的 Markdown Wiki。它純標準庫、不依賴外部服務，不下載影片、不做 ASR，也不覆寫來源。屬於 `yt-channel-distill` 集合；腳本以集合根的 `pyproject.toml` 執行。

## 使用

`<ws>` 為 workspace（見集合 [`README.md`](../../README.md)）。POSIX shell 直接貼上；PowerShell 將 `\` 換成反引號。

```bash
uv run --project <collection-root> python <collection-root>/skills/llm-wiki/scripts/bootstrap.py --json
uv run --project <collection-root> python <collection-root>/skills/llm-wiki/scripts/compile_wiki.py \
  --candidates <ws>/knowledge/p0_candidates.json \
  --coverage <ws>/data/manifest/coverage-report.json \
  --wiki-dir <ws>/knowledge/wiki
uv run --project <collection-root> python <collection-root>/skills/llm-wiki/scripts/validate_wiki.py \
  --candidates <ws>/knowledge/p0_candidates.json \
  --coverage <ws>/data/manifest/coverage-report.json \
  --wiki-dir <ws>/knowledge/wiki
uv run --project <collection-root> python <collection-root>/skills/llm-wiki/scripts/smoke_test.py --json
uv run --project <collection-root> python <collection-root>/skills/llm-wiki/scripts/wiki_sync.py \
  --manifest <ws>/data/manifest/videos.json \
  --log <ws>/data/processing/wiki-gate.jsonl \
  --candidates <ws>/knowledge/p0_candidates.json \
  --coverage <ws>/data/manifest/coverage-report.json \
  --wiki-dir <ws>/knowledge/wiki
```

若 evidence packet 已封存，`wiki_sync.py` 追加 `--evidence-dir <ws>/data/processing/evidence_packets`；Wiki gate 以 packet hash 記錄 supplemental／blocked 終態，成功補證不會升格為 canonical transcript。

`bootstrap.py` 只檢查檔案與 Python 版本，不會建立或修改來源。`compile_wiki.py` 失敗時保持既有輸出；成功後以 input hash 避免相同輸入重複追加 log。集合 CLI 在 `--sync-wiki` 時把 READY／READY_PARTIAL／FAILED／AGY_BLOCKED 的 derived `wiki_gate` 狀態寫入 manifest 並同步 append-only log；canonical transcript、source chunks 與原始媒體保持不變。

`smoke_test.py` 在自動清理的暫存目錄建立 fixture，執行 bootstrap、compile、第二次冪等 compile 與 validate，並確認 candidates／coverage 未被改寫；它不讀取或修改 workspace 資料。
