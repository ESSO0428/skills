# Command reference

`$W` is the workspace (`--workspace` > `$YTD_WORKSPACE` > cwd), `$C` is the collection root. Verify flags with `--help` before use; defaults below are read from the argparse definitions. Prefix each command with `uv run --project $C python`.

## `-m channel_distill <command> --workspace $W` (src/channel_distill/cli.py)

| command | key flags |
|---|---|
| `inventory` | `--channel-id` (required), `--skip-playlists` |
| `plan-download` | `--output $W/DOWNLOAD_PLAN.md`, `--min-free-space-gb 30`, `--safety-reserve-percent 0.25`, `--margin 1.5` |
| `download` | `--topic` (required), `--video-id`, `--ffprobe`, `--max-videos`, `--sync-wiki [--candidates]`, plus the plan-download space flags |
| `transcribe` | `--video-id` (required), `--ffmpeg`, `--model-path` or `--model-name` (under `$W/data/models`), `--min-free-space-gb`, `--postprocess` (prepare-sources, build-reading-views, audit-coverage), `--sync-wiki [--candidates]` |
| `prepare-sources` | none beyond `--workspace` |
| `build-reading-views` | `--source-dir $W/data/processing/source_chunks`, `--output-dir $W/data/processing/reading_views` |
| `audit-coverage` | `--output $W/data/manifest/coverage-report.json`, `--priority P0` |
| `wiki-gate` | `--record` (required), `--log` |
| `compile-wiki` | `--candidates $W/knowledge/p0_candidates.json`, `--coverage`, `--wiki-dir $W/knowledge/wiki` |

Topic classification reads `$W/config/topic-rules.json` (none means every video is topic `unknown`); a sample is `$C/examples/topic-rules.ml-course.json`.

## Frozen batch (skills/acquiring-video-sources/scripts)

- `acquire_video_batch.py freeze --ids-file <ids.json> [--run-id]`; the manifest and output default under `$W`.
- `acquire_video_batch.py plan` (read-only preflight), then `run --execute` after user approval; both take `--workspace`, `--batch`, `--report`, space flags.
- `video_batch_report.py --stage {acquisition,agy-plan,final} --manifest <p> --batch <p> [--json] [--output <p>]`
- `agy_batch_jobs.py {budget,prepare,run,record-usage-after}`: the AGY quota flow and its approval rules are in acquiring-video-sources and [`../../../docs/agy-fallback-policy.md`](../../../docs/agy-fallback-policy.md).
- `extract_video_frames.py --video --video-id --source-url --requests --output-dir --output-manifest [--ffmpeg]`

## Other

- `skills/distilling-youtube-channel/scripts/build_semantic_review.py --workspace $W [--manifest] [--source-chunks-dir] [--agy-packets-dir $W/data/processing/agy-evidence-packets] [--output-dir $W/data/processing/semantic_reviews] [--audit]`
- `skills/llm-wiki/scripts/wiki_gate.py --record <p> [--log <p>]`, `compile_wiki.py --candidates --coverage --wiki-dir` (all required), `validate_wiki.py`, `wiki_sync.py --manifest --log [--evidence-dir]`.
