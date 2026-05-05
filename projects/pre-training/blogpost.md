# We made an open source AI lab of agents to train models

tl;dr: a team of repo-defined OpenCode agents researches papers, proposes
hypotheses, runs parallel experiments on Hugging Face Jobs, reviews the runs,
records the results locally, and repeats.

Most ML experiment infrastructure solves the execution problem; i.e. how to get
code onto GPUs. The harder problem starts after the run finishes: what
happened, why did it fail, and what should we do next?

This post is about that second problem. The current implementation in this repo
uses three layers:

- a **control plane** implemented in OpenCode with checked-in agent roles
- an **execution plane** implemented in Hugging Face Jobs with managed `uv`
scripts, H200s, and shared HF buckets
- an **observability layer** implemented in Trackio to turn job state and
metrics into a dashboard and a retrospective data layer

We started with a few other control-plane experiments, but the current version
standardizes on OpenCode because it is simpler, repo-local, and easier to
reason about.

The code is open at [burtenshaw/openlab](https://github.com/burtenshaw/openlab),
now centered on the OpenCode implementation. The workflow below comes from real
waves of experiments on Andrej Karpathy's
[autoresearch](https://github.com/karpathy/autoresearch) benchmark.

## What the experiment actually is

`autoresearch` is a short, fixed-budget language model training run. The target
metric is `val_bpb` (validation bits-per-byte). In the current implementation,
the benchmark baseline is local: `train_orig.py`, `research/live/master.json`,
and `research/results.tsv` define the promoted master.

Each experiment follows one strict rule: **one hypothesis, one edit, one run**.
The agents refresh from the current local promoted master, change exactly one
thing in `train.py`, launch one managed benchmark job, record the run locally,
and only promote the master if the result beats the current baseline.

For education's sake, this is the script layer that sits underneath the agents:

```bash
uv run scripts/refresh_master.py --fetch-dag
uv run scripts/hf_job.py launch --mode experiment
uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/autolab-run.log
uv run scripts/submit_patch.py --comment "warmdown ratio 0.925, val_bpb 0.958973"
```

That sequence is the core experiment loop for one hypothesis. The main
questions are: what should we try next, how do we run experiments in parallel,
and how do we improve our understanding of the results?

We ran this benchmark in waves, with many workers exploring small variants in
parallel. The figure below shows the jobs running during one of those waves.

job overview

## The control plane in OpenCode

The current control plane is a repo-local OpenCode setup. The main session uses
the checked-in `autolab` primary agent and delegates to specialized roles that
already know the workflow from `AGENTS.md` and the repo agent definitions.

The role mapping is direct:


| Primitive                | OpenCode implementation                     |
| ------------------------ | ------------------------------------------- |
| Batch of work            | `research/campaigns/*.md` campaign note     |
| Unit of work             | `research/experiments/*.md` experiment note |
| Planner                  | `planner`                                   |
| Worker                   | `experiment-worker`                         |
| Review                   | `reviewer`                                  |
| Durable notebook owner   | `memory-keeper`                             |
| Fleet / metrics observer | `reporter`                                  |
| Literature scout         | `researcher`                                |
| Dispatch                 | parent `autolab` session invoking subagents |


Two design choices matter a lot:

1. `memory-keeper` is the only durable markdown writer in the main checkout.
2. `experiment-worker` is the only code-mutating role, and it runs in an
  isolated git worktree created by `scripts/opencode_worker.py`.

That makes the stack much easier to understand after the fact. The notebook,
the run ledger, and the current promoted master all live in the repo. The
workers can be parallel, but the durable state stays legible.

### Running the same experiment with OpenCode

Here is the same kind of warmdown-ratio follow-up, but expressed as a parent
OpenCode session using the checked-in roles:

```text
Read AGENTS.md, research/notes.md, research/do-not-repeat.md,
research/results.tsv, research/live/master.json, and research/live/dag.json.

Use planner to propose up to 3 fresh scheduler experiments against current local
master.

Use reviewer to reject duplicates or stale ideas before any paid run starts.

For the best approved experiment:
- create one isolated experiment-worker worktree
- refresh from current local master
- edit train.py only
- launch exactly one managed HF Jobs experiment
- parse the metric
- record the run locally
- tell memory-keeper what durable note to write

Use reporter at the end to summarize the active jobs, anomalies, and current leader.
```

That is the control plane in practice. The parent session reasons about what to
do next, but it delegates planning, execution, review, reporting, and durable
state updates to explicit subagent roles.

## The Hub as agent infrastructure

We use the Hub as an infrastructure layer for the agents:

- buckets are the shared cache and storage layer
- jobs are the execution layer
- Trackio is the observability layer
- datasets are the data layer
- papers are the research layer

The important idea is that the infrastructure is open and reusable. The agents
are not bound to one vendor-specific control plane. They can use the Hub as a
set of primitives and build a workflow on top of it.

### HF Jobs: the execution plane

Once the OpenCode control plane decides what to run, Hugging Face Jobs handles
execution as a self-contained `uv` script from the current workspace. The
launcher bundles the experiment's `train.py`, primes or reuses the shared HF
bucket cache, and submits the run as a managed job.

Under the hood, that becomes an `hf jobs uv run` call with explicit hardware,
timeout, labels, secrets, and the mounted cache bucket:

```bash
hf jobs uv run \
  --flavor h200 \
  --timeout 90m \
  --detach \
  --label autolab \
  --label mode=experiment \
  --label launcher=hf-job-py \
  --label campaign=schedule_shorter_cooldowns \
  --label experiment=warmdown_0925 \
  --label worker=worker_0 \
  --label hypothesis=warmdown_ratio_0_925 \
  --label master=935fdbf9f4ae \
  --secrets HF_TOKEN \
  --volume "hf://buckets/burtenshaw/autolab-cache:/autolab-home/.cache/autoresearch" \
  .runtime/autolab-hf-job.py
```

Those labels make each run traceable by campaign, experiment, worker, and
hypothesis. The shared HF bucket means you only pay the data bootstrap cost
once. After the first `--mode prepare` job primes the cache, every subsequent
experiment reuses it.

The agents can inspect the jobs and stream the logs:

```bash
hf jobs inspect <JOB_ID>
hf jobs logs <JOB_ID>
hf jobs ps --namespace burtenshaw
```

The final summary block contains everything needed to evaluate the result:

```text
val_bpb:          0.958973
training_seconds: 300.0
peak_vram_mb:     33609.6
mfu_percent:      46.79
total_tokens_M:   324.8
num_steps:        2478
```

## Trackio: the observability layer

Trackio turns the control-plane events and execution metadata into something you
can browse after the wave is over.

alerts

The reporter script now works from the local HF job registries plus the local
master snapshot. It groups runs by experiment and hypothesis, surfaces
duplicates and anomalies, and can keep a local dashboard open while the wave is
active.

```bash
uv run scripts/trackio_reporter.py summary --max-jobs 25
uv run scripts/trackio_reporter.py sync --project autolab
uv run scripts/trackio_reporter.py dashboard --project autolab --mcp-server --no-footer
```

This produces three useful views:

1. **A fleet summary**: active jobs, failures, anomalies, and the current leader
2. **A local job board**: every HF Job merged from the main checkout and worker
  worktrees
3. **A durable dashboard**: a Trackio-backed view that is useful both live and
  after the wave finishes

The most important use case is not the live dashboard. It is the retrospective:
someone who was not watching the system live can come back later and still
understand what happened.

## Try it out

The direct operator path is now OpenCode-first:

```bash
git clone https://github.com/burtenshaw/openlab.git
cd openlab
uv sync
hf auth login
hf auth whoami
hf buckets create "$AUTOLAB_HF_BUCKET" --private --exist-ok
opencode auth login
opencode
```

Then use the `autolab` primary agent with a prompt like:

```text
Run one autonomous local autoresearch pass in this repo using the repo-defined roles.

Use planner to propose up to 2 fresh single-change experiments against the current local promoted master.
Use reviewer to reject duplicates or stale ideas before any paid run starts.
If the shared HF cache is not ready, run the one-time prepare path using the configured HF bucket.
Then refresh the local promoted master.

For the best approved experiment, create one isolated experiment-worker worktree and launch it through Hugging Face Jobs.
Use HF Jobs for the benchmark run, the shared HF bucket for cache/data mounting, and the reserved experiment log path.
When the run finishes, parse the metric, record it locally, tell me whether it promoted, and hand the durable note text to memory-keeper.
Use reporter at the end to summarize active jobs, anomalies, and the current leader.

Start 5 jobs at once.
Do not stop until all you have completed a full pass of successful experiments.
```

If you want the exact script surface, it is all documented in `AGENTS.md` and
`docs/opencode-workflow.md`. But the point of the current stack is that you do
not need to remember all of those commands. The repo-local agents already know
the shape of the lab.