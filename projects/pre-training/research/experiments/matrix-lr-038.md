# Experiment: Lower MATRIX_LR from 0.042 to 0.038 to test whether slower learning of Muon matrix parameters improves validation bpb.

## Campaign

- Campaign: `optimizer-tuning`

## Hypothesis

Lower MATRIX_LR from 0.042 to 0.038 to test whether slower learning of Muon matrix parameters improves validation bpb.

## Parent Context

- Parent master hash: `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`
- Master val_bpb at dispatch: `0.962777`
- Worker id: `worker-4`
- Worktree: `/Users/ben/code/open-autolab/.runtime/worktrees/matrix-lr-038`

## Single Variable

<What exact variable, knob, or logic change is being tested?>

## Expected Upside

<Why this might improve val_bpb or effective throughput inside the 5-minute budget>

## Duplicate Check

<Why this is not a duplicate of an open or recent experiment>

## Runtime

- Log path: `/Users/ben/code/open-autolab/research/live/matrix-lr-038.log`
- Launcher: `uv run scripts/opencode_worker.py run matrix-lr-038`

## Allowed Edit Scope

- `train.py` only

## Run Plan

- Refresh master with `uv run scripts/refresh_master.py --fetch-dag`
- Run `uv run scripts/hf_job.py preflight`
- Run `uv run scripts/hf_job.py launch --mode experiment`
- Stream logs to the reserved path
- Parse `uv run scripts/parse_metric.py /Users/ben/code/open-autolab/research/live/matrix-lr-038.log`

## Result

- Local val_bpb: `<value>`
- Submitted: `yes|no`
- Interpretation: `<one or two sentences>`
- Failure mode, if any: `<brief note>`

## Memory-Keeper Handoff

- One short note for `research/notes.md`: `<summary>`
- Any do-not-repeat update: `<summary or none>`
