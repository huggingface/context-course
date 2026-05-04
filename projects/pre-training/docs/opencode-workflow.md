# OpenCode Workflow

OpenCode is the canonical control plane for this repo.

The benchmark surface is unchanged:

- `train.py` is the experiment file
- `prepare.py` is read-only
- Hugging Face Jobs is the only remote execution path
- Trackio is the only remote observability path
- `research/results.tsv` is the append-only local run ledger
- `train_orig.py` plus `research/live/` define the current promoted local master

## Repo Surface

- `opencode.json`
  Repo-local OpenCode config, including disabled-by-default MCP entries for
  Hugging Face and Trackio.
- `.opencode/agent/`
  The checked-in OpenCode agents: `autolab`, `planner`, `experiment-worker`,
  `reviewer`, `memory-keeper`, `researcher`, and `reporter`.
- `.agents/skills/`
  Shared repo-local skills that OpenCode can load on demand.
- `research/templates/`
  Canonical campaign, experiment, and do-not-repeat templates.
- `scripts/opencode_worker.py`
  Creates isolated worktrees and launches `experiment-worker` runs.
- `scripts/print_opencode_kickoff.py`
  Prints a standard parent-session kickoff prompt.

## Setup

1. Install dependencies:

```bash
uv sync
```

2. Create a local operator env file:

```bash
mkdir -p ~/.autolab
cp .autolab.credentials.example ~/.autolab/credentials
$EDITOR ~/.autolab/credentials
. ~/.autolab/credentials
```

3. Authenticate Hugging Face:

```bash
hf auth login
```

4. Authenticate OpenCode and select a model.

Default provider path:

```bash
opencode auth login
opencode
# inside OpenCode:
/models
```

Choose Hugging Face and then select an open model through Hugging Face
Inference Providers. Do not pin a single model in repo config.

5. Validate the environment:

```bash
bash scripts/bootstrap_public.sh
```

6. Warm the shared HF cache once:

```bash
uv run scripts/hf_job.py launch --mode prepare
```

## Parent Session Workflow

1. Refresh current local benchmark truth:

```bash
uv run scripts/refresh_master.py --fetch-dag
```

2. Review the current notebook:

- `research/notes.md`
- `research/do-not-repeat.md`
- `research/campaigns/`
- `research/experiments/`
- `research/results.tsv`
- `research/live/master.json`
- `research/live/dag.json`

3. Print a kickoff prompt if you want one:

```bash
uv run scripts/print_opencode_kickoff.py --gpu-slots 1
```

4. Start OpenCode in the pre-training project root:

```bash
opencode
```

5. Use the `autolab` primary agent. Delegate to:

- `planner` for fresh experiment queues
- `reviewer` for rule and comparability checks
- `researcher` for paper-derived ideas
- `reporter` for Trackio and HF Jobs status
- `memory-keeper` after each worker finishes

## Isolated Worker Workflow

Create one isolated worktree per experiment:

```bash
uv run scripts/opencode_worker.py create exp-warmdown-20 \
  --campaign "schedule: shorter cooldowns" \
  --hypothesis "Shorten warmdown to test whether the long cooldown tail is wasting the fixed budget." \
  --worker-id worker-0
```

This creates:

- `.runtime/worktrees/<experiment-id>/`
- `.runtime/opencode-workers/<experiment-id>.json`
- `research/experiments/<experiment-id>.md`
- `research/live/<experiment-id>.log`

Launch the worker:

```bash
uv run scripts/opencode_worker.py run exp-warmdown-20
```

The worker launcher exports:

- `AUTOLAB_CAMPAIGN`
- `AUTOLAB_EXPERIMENT_ID`
- `AUTOLAB_WORKER_ID`
- `AUTOLAB_HYPOTHESIS`
- `AUTOLAB_LOG_PATH`

Use `--dry-run` to inspect the exact `opencode run --agent experiment-worker`
command and environment without starting the run.

When the worker result has been recorded by `memory-keeper`, remove the
worktree:

```bash
uv run scripts/opencode_worker.py cleanup exp-warmdown-20
```

## Local Recording

Every completed run should be recorded with:

```bash
uv run scripts/submit_patch.py --comment "one-sentence hypothesis and observed val_bpb"
```

This appends a row to `research/results.tsv`. It promotes the local master only
when the result beats current master.

## Reporting

Use the local reporter path before launching more paid work:

```bash
uv run scripts/trackio_reporter.py summary --max-jobs 25
```

For a synced dashboard with MCP enabled:

```bash
uv run scripts/trackio_reporter.py sync --project "${AUTOLAB_TRACKIO_PROJECT:-autolab}"
uv run scripts/trackio_reporter.py dashboard --project "${AUTOLAB_TRACKIO_PROJECT:-autolab}" --mcp-server --no-footer
```

## Optional MCP

`opencode.json` ships two disabled MCP entries:

- `huggingface`
  Remote Hugging Face MCP at `https://huggingface.co/mcp`
- `trackio`
  Local Trackio MCP endpoint at `http://127.0.0.1:7860/gradio_api/mcp/`

Enable them only when you need them.

## Optional llama.cpp

The default model path is Hugging Face Inference Providers.

If you want local model execution through `llama-server`, copy the example config
from `docs/opencode-llama-cpp.example.json` into your own OpenCode config and
adjust the local model id, display name, and endpoint.
