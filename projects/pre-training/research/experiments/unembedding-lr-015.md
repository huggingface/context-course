# Experiment: Increase UNEMBEDDING_LR from 0.01 to 0.015 to test whether a higher learning rate for the output layer improves validation bpb.

## Campaign

- Campaign: `optimizer-tuning`

## Hypothesis

Increase UNEMBEDDING_LR from 0.01 to 0.015 to test whether a higher learning rate for the output layer improves validation bpb.

## Parent Context

- Parent master hash: `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`
- Master val_bpb at dispatch: `0.962777`
- Worker id: `worker-0`
- Worktree: `/Users/ben/code/open-autolab/.runtime/worktrees/unembedding-lr-015`

## Single Variable

`UNEMBEDDING_LR = 0.015` (was 0.01)

## Expected Upside

Higher learning rate for the output layer may allow faster adaptation of the final projection, potentially improving validation bpb.

## Duplicate Check

No prior experiments have tested UNEMBEDDING_LR changes against this master.

## Runtime

- Log path: `/Users/ben/code/open-autolab/research/live/unembedding-lr-015.log`
- Launcher: `uv run scripts/opencode_worker.py run unembedding-lr-015`

## Allowed Edit Scope

- `train.py` only

## Run Plan

- Refresh master with `uv run scripts/refresh_master.py --fetch-dag`
- Run `uv run scripts/hf_job.py preflight`
- Run `uv run scripts/hf_job.py launch --mode experiment`
- Stream logs to the reserved path
- Parse `uv run scripts/parse_metric.py /Users/ben/code/open-autolab/research/live/unembedding-lr-015.log`

## Result

- HF Job: `69cc18d8942f980bf425a641`
- val_bpb: `0.970805`
- Master val_bpb: `0.962777`
- Delta: `+0.008028` (degraded)
- training_seconds: `300.1`
- total_seconds: `431.5`
- peak_vram_mb: `33609.6`
- mfu_percent: `44.14`
- total_tokens_M: `306.6`
- num_steps: `2339`
- Submitted: `no`
- Interpretation: Increasing UNEMBEDDING_LR from 0.01 to 0.015 significantly degraded validation bpb. The output layer is sensitive to learning rate increases.
- Failure mode: Significant regression (+0.008028 bpb).

## Memory-Keeper Handoff

- One short note for `research/notes.md`: Added experiment entry with FAILED status.
- Any do-not-repeat update: Added to Optimizer Tuning section.
