# Getting Started

This repo is a self-contained Autolab operator checkout. It uses a local
promoted master plus Hugging Face Jobs and Trackio.

## Prerequisites

- Python 3.10 or newer
- `uv`
- `hf` CLI
- `opencode`
- optional: `hermes`
- optional: `pi`
- a Hugging Face account with Jobs access

## 1. Clone And Install

```bash
git clone <repo-url>
cd <repo-dir>
uv sync
```

## 2. Create Local Operator Env

```bash
mkdir -p ~/.autolab
cp .autolab.credentials.example ~/.autolab/credentials
$EDITOR ~/.autolab/credentials
. ~/.autolab/credentials
```

The env file stays in your home directory, not in the repo.

## 3. Validate Your Setup

```bash
bash scripts/bootstrap_public.sh
```

This checks:

- `python3`, `uv`, and `hf`
- Python version compatibility
- local Hugging Face auth with `hf auth whoami`
- `AUTOLAB_HF_BUCKET`
- shared HF cache bucket creation

It prints the next commands without starting paid jobs.

## 4. Authenticate Hugging Face And Bootstrap Shared Cache

```bash
hf auth login
hf auth whoami
hf buckets create "$AUTOLAB_HF_BUCKET" --private --exist-ok
uv run scripts/hf_job.py launch --mode prepare
```

This prime step keeps tokenizer and data bootstrap out of your paid experiment
loop.

## 5. Refresh To Current Local Master

```bash
uv run scripts/refresh_master.py --fetch-dag
```

This rewrites:

- `train.py`
- `train_orig.py`
- `research/live/master.json`
- `research/live/master_detail.json`
- `research/live/dag.json`

Do not use repo git history as benchmark truth. Use the refreshed files above
plus `research/results.tsv`.

## 6. Authenticate OpenCode And Choose A Model

```bash
opencode auth login
opencode
# inside OpenCode:
/models
```

Choose Hugging Face and an open model through Hugging Face Inference Providers.
Do not pin a single exact model id in repo config.

## 7. Optional: Set Up The Hermes Profile

```bash
uv run scripts/setup_hermes_profile.py --profile autolab
autolab setup
```

The setup script keeps Hermes profile state in your home directory, wires in
the repo's shared skills, and leaves `AGENTS.md` as the only checked-in repo
rulebook for Hermes. It also keeps profile-wide `worktree: true` disabled so
the parent session stays in the main checkout.

## 8. Optional: Set Up Pi Agent

```bash
npm install -g @mariozechner/pi-coding-agent
pi
```

The checked-in `.pi/settings.json` declares `pi-subagents`; Pi can install the
missing project package on startup. If you want to install it explicitly:

```bash
pi install npm:pi-subagents@0.22.0 -l
```

For the Pi path, continue with [pi-subagents-guide.md](pi-subagents-guide.md).

## 9. Start The Parent Session

```bash
uv run scripts/print_opencode_kickoff.py --gpu-slots 1
opencode
```

Use the `autolab` primary agent from the pre-training project root. For the full parent and
worker flow, continue with [opencode-workflow.md](opencode-workflow.md).

Optional Hermes parent session:

```bash
uv run scripts/print_hermes_kickoff.py --gpu-slots 1
autolab chat --toolsets "terminal,file,web,skills,delegation,clarify"
```

For the Hermes path, continue with [hermes-subagents-guide.md](hermes-subagents-guide.md).

Optional Pi parent session:

```bash
uv run scripts/print_pi_kickoff.py --gpu-slots 1
pi
# inside Pi:
/autolab "recent-master: follow-ups" 1 3
```

For the Pi path, continue with [pi-subagents-guide.md](pi-subagents-guide.md).

## 10. Run One Managed Experiment

Edit `train.py`, or launch an isolated worker with
`uv run scripts/opencode_worker.py create ...` and
`uv run scripts/opencode_worker.py run ...`.

For Hermes, reserve the worktree with `uv run scripts/hermes_worker.py create ...`
and print the worker payload with
`uv run scripts/hermes_worker.py delegate ...`.

For Pi, reserve and launch the worktree with
`uv run scripts/pi_worker.py create ...` and
`uv run scripts/pi_worker.py run ...`.

Then run:

```bash
uv run scripts/hf_job.py preflight
uv run scripts/hf_job.py launch --mode experiment
uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/autolab-run.log
uv run scripts/parse_metric.py /tmp/autolab-run.log
```

Rules:

- one hypothesis change only
- `train.py` only unless explicitly authorized otherwise
- do not modify `prepare.py`

## 11. Record The Run Locally

Every completed run should be appended to the local ledger:

```bash
uv run scripts/submit_patch.py --comment "one-sentence hypothesis and observed val_bpb"
```

This always records the run in `research/results.tsv`. It promotes the local
master only when the observed `val_bpb` beats current master.

## 12. Optional: Local Trackio Dashboard

```bash
uv run scripts/trackio_reporter.py sync --project "${AUTOLAB_TRACKIO_PROJECT:-autolab}"
uv run scripts/trackio_reporter.py dashboard --project "${AUTOLAB_TRACKIO_PROJECT:-autolab}" --mcp-server --no-footer
```

Use the reporter summary before launching more work:

```bash
uv run scripts/trackio_reporter.py summary --max-jobs 25
```
