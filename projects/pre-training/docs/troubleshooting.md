# Troubleshooting

## `missing required environment variable: AUTOLAB_HF_BUCKET`

Cause:

- your local operator env is not loaded

Fix:

```bash
mkdir -p ~/.autolab
cp .autolab.credentials.example ~/.autolab/credentials
$EDITOR ~/.autolab/credentials
. ~/.autolab/credentials
```

## `hf auth whoami` fails

Cause:

- the Hugging Face CLI is not authenticated on this machine

Fix:

```bash
hf auth login
hf auth whoami
```

## `train.py differs from train_orig.py`

Cause:

- `uv run scripts/refresh_master.py` is trying to restore the local promoted
  master over unrecorded edits

Fix:

- record or discard the current experiment first
- rerun `uv run scripts/refresh_master.py --fetch-dag`
- if you intentionally want to overwrite `train.py`, rerun with `--force`

## `could not recover source for current promoted master`

Cause:

- `train_orig.py` and `research/live/master_detail.json` do not agree with the
  promoted hash in `research/results.tsv`

Fix:

- inspect the latest promoted row in `research/results.tsv`
- restore `train_orig.py` from a known-good checkout if it was edited manually
- rerun `uv run scripts/refresh_master.py --fetch-dag`

## `no cached local metrics were found for the selected job`

Cause:

- `scripts/submit_patch.py --dry-run` could not find a cached experiment log or
  parsed metrics on disk

Fix:

```bash
uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/autolab-run.log
uv run scripts/submit_patch.py --dry-run --comment "..." --log /tmp/autolab-run.log
```

Or rerun `uv run scripts/submit_patch.py --comment "..."` without `--dry-run`
so it can fetch the missing log from Hugging Face Jobs.

## `opencode` not found

Cause:

- OpenCode is not installed or is not on `PATH`

Fix:

```bash
which opencode
```

If that fails, install OpenCode and try again. If it is installed in a nonstandard
location, set `AUTOLAB_OPENCODE_BIN` before running
`uv run scripts/opencode_worker.py run ...`.

## Duplicate HF Jobs For One Experiment

Cause:

- the same experiment id was launched twice
- or the same hypothesis was launched concurrently under multiple experiment ids

Fix:

```bash
uv run scripts/trackio_reporter.py summary --max-jobs 25
hf jobs ps --namespace "$AUTOLAB_HF_NAMESPACE"
hf jobs cancel <DUPLICATE_JOB_ID>
```

Keep only one active experiment job per experiment id. Update the experiment
note with the surviving job id.

## Scoped `prepare` launch blocked

Cause:

- `AUTOLAB_CAMPAIGN`, `AUTOLAB_EXPERIMENT_ID`, `AUTOLAB_WORKER_ID`, or
  `AUTOLAB_HYPOTHESIS` is set in the current shell or worktree
- `uv run scripts/hf_job.py launch --mode prepare` was started from an
  experiment-scoped environment

Fix:

```bash
unset AUTOLAB_CAMPAIGN AUTOLAB_EXPERIMENT_ID AUTOLAB_WORKER_ID AUTOLAB_HYPOTHESIS
uv run scripts/hf_job.py launch --mode prepare
```

Run shared `prepare` work once from the parent checkout, not from an isolated
experiment worker.

## Stale Isolated Worktree State

Symptoms:

- an experiment worktree still exists after the result was recorded
- a rerun says the worktree already exists
- the main checkout is clean, but `.runtime/worktrees/<experiment-id>/` is not

Fix:

```bash
uv run scripts/opencode_worker.py cleanup <EXPERIMENT_ID>
```

If the worktree still has local changes you intentionally want to discard, rerun
with `--force`.

## `val_bpb not found`

Cause:

- the job ended early
- the log never reached final evaluation
- you parsed the wrong log file

Fix:

```bash
uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/autolab-run.log
uv run scripts/parse_metric.py /tmp/autolab-run.log
```

If the log still lacks `val_bpb`, treat the run as non-comparable. You may still
record it locally with `scripts/submit_patch.py`, but it will not promote the
current master.
