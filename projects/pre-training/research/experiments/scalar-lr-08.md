# Experiment: Increase SCALAR_LR from 0.7 to 0.8 to test whether faster learning of per-layer residual and initial scaling parameters improves validation bpb.

## Campaign

- Campaign: `optimizer-tuning`

## Hypothesis

Increase SCALAR_LR from 0.7 to 0.8 to test whether faster learning of per-layer residual and initial scaling parameters improves validation bpb.

## Parent Context

- Parent master hash: `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`
- Master val_bpb at dispatch: `0.962777`
- Worker id: `worker-1`
- Worktree: `/Users/ben/code/open-autolab/.runtime/worktrees/scalar-lr-08`

## Single Variable

- `train.py` line 455: `SCALAR_LR = 0.8` (was 0.7)

## Expected Upside

Faster learning of per-layer residual and initial scaling parameters could improve optimization dynamics and lead to better validation bpb.

## Duplicate Check

This is not a duplicate - no previous experiments have tested SCALAR_LR changes on the current master.

## Runtime

- Log path: `/Users/ben/code/open-autolab/research/live/scalar-lr-08.log`
- Launcher: `uv run scripts/opencode_worker.py run scalar-lr-08`

## Allowed Edit Scope

- `train.py` only

## Run Plan

- Refresh master with `uv run scripts/refresh_master.py --fetch-dag`
- Run `uv run scripts/hf_job.py preflight`
- Run `uv run scripts/hf_job.py launch --mode experiment`
- Stream logs to the reserved path
- Parse `uv run scripts/parse_metric.py /Users/ben/code/open-autolab/research/live/scalar-lr-08.log`

## Result

- Status: FAILED
- HF Job: `69cbe00334fa24114ddf47a6`
- val_bpb: `0.963049` (WORSE than master 0.962777)
- training_seconds: `300.1`
- total_seconds: `433.0`
- peak_vram_mb: `33609.6`
- mfu_percent: `44.82`
- total_tokens_M: `311.3`
- num_steps: `2375`
- Submitted: `no`
- Interpretation: Increasing SCALAR_LR degraded validation bpb by +0.000272. The faster learning rate for scalar parameters hurt generalization.
- Failure mode: Regression - higher val_bpb than master

## Memory-Keeper Handoff

- One short note for `research/notes.md`: FAILED. Increasing SCALAR_LR degraded validation bpb by +0.000272.
- Any do-not-repeat update: Add to Known Regressions under Optimizer Tuning section.
