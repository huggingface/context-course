# Experiment: Increase embedding weight decay from 0.0005 to 0.001 to test whether stronger regularization on token embeddings improves validation bpb, following the success of the lm_head weight decay increase.

## Campaign

- Campaign: `regularization-tuning`

## Hypothesis

Increase embedding weight decay from 0.0005 to 0.001 to test whether stronger regularization on token embeddings improves validation bpb, following the success of the lm_head weight decay increase.

## Parent Context

- Parent master hash: `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`
- Master val_bpb at dispatch: `0.962777`
- Worker id: `worker-0`
- Worktree: `/Users/ben/code/open-autolab/.runtime/worktrees/embedding-wd-001`

## Single Variable

- `train.py` line 257: `weight_decay = 0.001` (was 0.0005) for embedding optimizer group

## Expected Upside

Stronger regularization on token embeddings could improve generalization and validation bpb, following the success of the lm_head weight decay increase.

## Duplicate Check

This is not a duplicate - no previous experiments have tested embedding weight decay changes on the current master.

## Runtime

- Log path: `/Users/ben/code/open-autolab/research/live/embedding-wd-001.log`
- Launcher: `uv run scripts/opencode_worker.py run embedding-wd-001`

## Allowed Edit Scope

- `train.py` only

## Run Plan

- Refresh master with `uv run scripts/refresh_master.py --fetch-dag`
- Run `uv run scripts/hf_job.py preflight`
- Run `uv run scripts/hf_job.py launch --mode experiment`
- Stream logs to the reserved path
- Parse `uv run scripts/parse_metric.py /Users/ben/code/open-autolab/research/live/embedding-wd-001.log`

## Result

- Status: CANCELLED (STUCK)
- HF Job: `69cbdff7942f980bf425a3d0`
- Stuck at: step 02348 (97.6%) during final evaluation phase
- Duration: 10+ minutes hanging before cancellation
- Submitted: `no`
- Interpretation: Job cancelled due to infrastructure issue during evaluation. Hypothesis remains untested.
- Failure mode: Infrastructure - job hung during evaluation phase

## Memory-Keeper Handoff

- One short note for `research/notes.md`: CANCELLED due to job hanging at step 02348 during evaluation. Hypothesis remains untested.
- Any do-not-repeat update: Add to Known Regressions under Regularization Tuning section with note about infrastructure issue.
