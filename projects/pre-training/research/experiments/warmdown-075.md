# Experiment: Decrease WARMDOWN_RATIO from 0.825 to 0.75 to allow more time at higher learning rates before the final LR floor.

## Campaign

- Campaign: `schedule-tuning`

## Hypothesis

Decrease WARMDOWN_RATIO from 0.825 to 0.75 to allow more time at higher learning rates before the final LR floor.

## Parent Context

- Parent master hash: `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`
- Master val_bpb at dispatch: `0.962777`
- Worker id: `worker-1`
- Worktree: `/Users/ben/code/open-autolab/.runtime/worktrees/warmdown-075`

## Single Variable

`WARMDOWN_RATIO = 0.75` (was 0.825)

## Expected Upside

More time at higher learning rates before the final LR floor may improve convergence quality.

## Duplicate Check

No prior experiments have tested WARMDOWN_RATIO changes against this master.

## Runtime

- Log path: `/Users/ben/code/open-autolab/research/live/warmdown-075.log`
- Launcher: `uv run scripts/opencode_worker.py run warmdown-075`

## Allowed Edit Scope

- `train.py` only

## Run Plan

- Refresh master with `uv run scripts/refresh_master.py --fetch-dag`
- Run `uv run scripts/hf_job.py preflight`
- Run `uv run scripts/hf_job.py launch --mode experiment`
- Stream logs to the reserved path
- Parse `uv run scripts/parse_metric.py /Users/ben/code/open-autolab/research/live/warmdown-075.log`

## Result

- HF Job: `69cc194534fa24114ddf48bd`
- val_bpb: `0.962980`
- Master val_bpb: `0.962777`
- Delta: `+0.000203` (degraded)
- training_seconds: `300.1`
- total_seconds: `431.5`
- peak_vram_mb: `33609.6`
- mfu_percent: `43.88`
- total_tokens_M: `304.7`
- num_steps: `2325`
- Submitted: `no`
- Interpretation: Decreasing WARMDOWN_RATIO from 0.825 to 0.75 slightly degraded validation bpb. The longer warmdown phase in master appears beneficial for final convergence.
- Failure mode: Slight regression (+0.000203 bpb).

## Memory-Keeper Handoff

- One short note for `research/notes.md`: Added experiment entry with FAILED status.
- Any do-not-repeat update: Added to Schedule Tuning section.
