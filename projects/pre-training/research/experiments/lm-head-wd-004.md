# Experiment: Increase lm_head weight_decay from 0.003 to 0.004 to continue the winning direction of stronger output layer regularization.

## Campaign

- Campaign: `regularization-tuning`

## Hypothesis

Increase lm_head weight_decay from 0.003 to 0.004 to continue the winning direction of stronger output layer regularization.

## Parent Context

- Parent master hash: `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`
- Master val_bpb at dispatch: `0.962777`
- Worker id: `worker-2`
- Worktree: `/Users/ben/code/open-autolab/.runtime/worktrees/lm-head-wd-004`

## Single Variable

<What exact variable, knob, or logic change is being tested?>

## Expected Upside

<Why this might improve val_bpb or effective throughput inside the 5-minute budget>

## Duplicate Check

<Why this is not a duplicate of an open or recent experiment>

## Runtime

- Log path: `/Users/ben/code/open-autolab/research/live/lm-head-wd-004.log`
- Launcher: `uv run scripts/opencode_worker.py run lm-head-wd-004`

## Allowed Edit Scope

- `train.py` only

## Run Plan

- Refresh master with `uv run scripts/refresh_master.py --fetch-dag`
- Run `uv run scripts/hf_job.py preflight`
- Run `uv run scripts/hf_job.py launch --mode experiment`
- Stream logs to the reserved path
- Parse `uv run scripts/parse_metric.py /Users/ben/code/open-autolab/research/live/lm-head-wd-004.log`

## Result

- Local val_bpb: `<value>`
- Submitted: `yes|no`
- Interpretation: `<one or two sentences>`
- Failure mode, if any: `<brief note>`

## Memory-Keeper Handoff

- One short note for `research/notes.md`: `<summary>`
- Any do-not-repeat update: `<summary or none>`
