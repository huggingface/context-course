# Experiment: <short title>

## Campaign

- Campaign: `<theme>`

## Hypothesis

<One sentence. What single change do you expect to help, and why?>

## Parent Context

- Parent master hash: `<hash>`
- Master val_bpb at dispatch: `<value>`
- Worker id: `<worker-id>`
- Worktree: `<worktree-path>`

## Single Variable

<What exact variable, knob, or logic change is being tested?>

## Expected Upside

<Why this might improve val_bpb or effective throughput inside the 5-minute budget>

## Duplicate Check

<Why this is not a duplicate of an open or recent experiment>

## Runtime

- Log path: `<log-path>`
- Launcher: `uv run scripts/opencode_worker.py run <experiment-id>`

## Allowed Edit Scope

- `train.py` only

## Run Plan

- Refresh local master with `uv run scripts/refresh_master.py --fetch-dag`
- Run `uv run scripts/hf_job.py preflight`
- Run `uv run scripts/hf_job.py launch --mode experiment`
- Stream logs to the reserved path
- Parse `uv run scripts/parse_metric.py <log-path>`
- Record the run with `uv run scripts/submit_patch.py --comment "..."`

## Result

- Local val_bpb: `<value>`
- Recorded locally: `yes|no`
- Promoted locally: `yes|no`
- Interpretation: `<one or two sentences>`
- Failure mode, if any: `<brief note>`

## Memory-Keeper Handoff

- One short note for `research/notes.md`: `<summary>`
- Any do-not-repeat update: `<summary or none>`
