# AGY foreground execution

Use `skills/acquiring-video-sources/scripts/agy_zero_shot_batch.py` for user-approved AGY waves.

- The prompt must require foreground completion: finish media inspection in the same print turn, wait for every foreground command, and return the final schema object instead of progress text.
- Do not treat an outer conversation envelope or background-task progress as a transcript. Preserve it as `AGY_INVALID_OUTPUT` with raw stdout and stderr.
- For each valid object, save the normalized transcript JSON, raw response, stderr, prompt hash, model, CLI version, source path, coverage, and usage snapshots.
- Before each video, query `agy -p /usage`. Stop the wave when either Gemini five-hour or weekly remaining quota is at or below the configured reserve (default 10%).
- A valid `AUDIO_AND_VIDEO` plus `COMPLETE` object is still `OUTPUT_CAPTURED_REVIEW_REQUIRED` until content review; it is not automatically canonical evidence.
- Run waves rather than assuming duration-linear cost. Recompute the recommendation from the latest post-wave usage snapshot.
- `--limit` is a wave boundary, not permission to silently shrink the approved batch. The summary must report both `wave_complete` and `global_remaining_unattempted_count`; if quota or an acquisition error prevents the requested wave from finishing, the command exits non-zero and the partial wave must be reported as incomplete. Full burn uses `--reserve-percent 0`, retaining only the hard zero-quota guard.

## Quota direction report

Every AGY quota assessment must present these three user-selectable directions for the remaining unique videos. The estimates are planning ranges, not guarantees; include the latest `/usage` snapshot and state that retries are excluded unless explicitly added.

| Direction | Per-video estimate | Total for remaining videos | Per five-hour window | Recommended per week | Theoretical weekly cap (minimum/maximum) | Estimated completion (minimum/maximum) |
|---|---:|---:|---:|---:|---:|---:|
| Conservative | 12% five-hour / 2.4% weekly | remaining_count x those rates | about 6 videos | about 30 videos | about 30 / about 32 videos | 1 week / 2–3 weeks |
| Aggressive | 5% five-hour / 1% weekly | remaining_count x those rates | about 15 videos | about 45 videos | about 45 / about 50 videos | 1 week / 1–2 weeks |
| Full burn | 10% five-hour / 2% weekly, no reserve | remaining_count x those rates | about 8 videos | about 44 videos | about 44 / about 50 videos | within 1 week / about 1 week |

The agent must replace the illustrative counts with values calculated from the current candidate count and measured pilot range. The report columns are fixed: `Direction`, `Per-video estimate`, `Total for remaining videos`, `Per five-hour window`, `Recommended per week`, `Theoretical weekly cap (minimum/maximum)`, and `Estimated completion (minimum/maximum)`. The first value in each paired cell is the minimum estimate and the second is the maximum conservative estimate; for Full burn, use the latest completed-batch evidence when it is stronger than the old pilot high-water estimate. Do not present a full-burn command until the user selects that direction; the selected direction controls the batch `--limit` and `--reserve-percent` arguments.

使用者可見報表固定使用以下中文欄位：`方案`、`單片估算`、`<N> 部總量`（N 依實際剩餘數替換）、`每五小時窗口`、`建議每週`、`當週理論上限（最少／最多）`、`預估完成（最少／最多）`。每個配對欄位一律先列最少值、再列最多值；`最多` 是最久的保守估算。若 Full burn 已有完整批次實測，優先使用實測週期，不得沿用較慢的舊高水位推算。

## After direction selection

Once the user selects Conservative, Aggressive, or Full burn, immediately produce the selected schedule. Partition the current remaining unique IDs into weekly groups and five-hour waves; show the reset boundary between waves; and provide copy-paste commands with unique output directories. Each command must set `--limit` to its wave size and `--reserve-percent` to the direction's reserve. Full burn uses zero reserve, while the other directions retain their calculated reserve. State that the commands use the maximum (slowest conservative) estimate; actual completion may be faster. The agent must not repeat the choice question or provide only a table after the selection.
