---
name: distilling-youtube-channel
description: 把一個 YouTube 頻道從 inventory 一路帶到有 provenance 的蒸餾前證據（字幕、ASR、AGY 補證、source chunks、語意審查、Wiki 與 coverage）。
disable-model-invocation: true
---

# Distilling a YouTube channel

Entry skill: takes a YouTube channel from inventory to provenance-backed evidence that a downstream distillation step can consume. Each stage names its command, a Completion check, and the sub-skill that owns the detail.

**必讀規則：**開始前讀 [`../../RULES.md`](../../RULES.md)，它是授權、磁碟、AGY、ASR 停止門檻與 provenance 的單一真實來源。逐階段旗標與路徑見 [`references/commands.md`](references/commands.md)。

**路徑慣例：**`<collection-root>` 是含 `pyproject.toml` 的集合根（從本檔往上兩層），`$W` 代表 workspace（`--workspace` > `$YTD_WORKSPACE` > cwd；布局見集合 [`README.md`](../../README.md)）。命令寫成 `uv run --project <collection-root> python -m channel_distill <sub> --workspace $W ...`，或 `uv run --project <collection-root> python <collection-root>/skills/<skill>/scripts/<script>.py ...`。需要 `yt-dlp`、`ffmpeg`、`ffprobe` 在 PATH（或 `$YTD_FFMPEG_DIR`）。

Stages run in order; finish one (its Completion check) before the next. A terminal gap stays a gap; RULES.md decides retries.

## Stages

1. **Inventory** — `inventory --channel-id <UC...>` (add `--skip-playlists` when playlists are not needed). Owner: [`acquiring-video-sources`](../acquiring-video-sources/SKILL.md).
   Completion: `$W/data/manifest/videos.json` lists every channel video once, with ID, URL, title, playlist links, visibility.

2. **Captions and metadata** — collected inside the acquisition run (stage 3); official or automatic timed captions come first.
   Completion: each video records its transcript type (official, automatic, none) and keeps the raw timed cues.

3. **Authorised download and verification** — pick explicit video IDs with the user, then `plan-download` (storage preflight) and `download --topic <topic> [--video-id <id>]`, or the frozen-batch route `acquire_video_batch.py freeze` → `plan` → `run --execute`. Show the user the size estimate and get approval before any download.
   Completion: each selected video has a local file that passed `ffprobe` and a manifest status; failed downloads are listed by ID.

4. **ASR fallback** — only for verified local videos with no usable caption: `transcribe --video-id <id> [--postprocess]`. Owner: [`recovering-asr`](../recovering-asr/SKILL.md).
   Completion: each video is `READY`, `READY_PARTIAL` (offsets listed) or `ASR_FAILED` (reason recorded).

5. **Bounded gap supplement** — only `ASR_SEGMENT_UNAVAILABLE` / `READY_PARTIAL` intervals. Owner: [`supplementing-asr-gaps`](../supplementing-asr-gaps/SKILL.md).
   Completion: every gap has one evidence packet or an explicit unavailable result.

6. **AGY fallback planning** — `video_batch_report.py --stage acquisition`, then `--stage agy-plan` for whole-video failures. Planning and reports are the agent's; bulk `agy_batch_jobs.py run --execute` is only handed to the user as a pasteable command after the user picks scope and usage cap. Skip this stage when `agy` is not installed. Owner: [`acquiring-video-sources`](../acquiring-video-sources/SKILL.md).
   Completion: expected, verified, transcribed, repaired and failed ID sets partition the frozen batch (`--stage final`); otherwise stop and fix before stage 7.

7. **Pre-distillation prep** — `prepare-sources` (source chunks), `build-reading-views`, then transcript-first semantic review with [`scripts/build_semantic_review.py`](scripts/build_semantic_review.py). Frame extraction (`extract_video_frames.py`, see [`../../docs/selective-review-workflow.md`](../../docs/selective-review-workflow.md)) is selective follow-up, not a gate.
   Completion: each readable video has source chunks, a reading view and a semantic-review record; unreadable ones carry `SEMANTIC_REVIEW_BLOCKED_SOURCE_GAP`.

8. **Wiki and coverage** — `wiki-gate --record <record.json>` (CLI wrapper of [`../llm-wiki/scripts/wiki_gate.py`](../llm-wiki/scripts/wiki_gate.py)) per terminal record, then `audit-coverage` and `compile-wiki`. Owner: [`llm-wiki`](../llm-wiki/SKILL.md).
   Completion: gate outcome is `COMPILE`, `COMPILE_WITH_GAPS` or `RECORD_BLOCKED` for every record, and `$W/data/manifest/coverage-report.json` lists the remaining gaps.

## Completion

The user holds a coverage report plus source chunks, reading views and semantic-review records with video ID, URL, time range, transcript type and status for each video, and every gap is named. Distillation itself happens downstream, outside this collection.

## Boundaries

- Whole-channel batch download, skipping the disk pre-check, unapproved downloads or AGY bulk runs, and deleting sources are all ruled out by RULES.md; follow it.
- Selector, concept grouping, evidence packets, normalization and any mentor or domain skill content are downstream and out of scope.
- `build_semantic_review.py` and the CLI take their paths from the workspace; for a second channel use a separate workspace.
