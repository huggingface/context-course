# Multi-Agent Autoresearch

This repo is a self-contained Open Source AI Lab that researches papers, manages experiments, runs GPUs, and repeats. It is based on [autoresearch](https://github.com/karpathy/autoresearch) by Andrej Karpathy.

<img width="2468" height="985" alt="gastown_wave2_running_jobs" src="https://github.com/user-attachments/assets/e1ae62ed-7a7a-4ba3-9e68-6fa97a4d86c8" />

OpenCode is the primary way to use this repo. The checked-in agents and [`AGENTS.md`](AGENTS.md) tell the agent which scripts to run and how to use them safely. There are also Hermes and Pi Agent adapters, plus older Codex and Claude Code material.

## What This Repo Contains

- `train.py`
  The working experiment surface.
- `prepare.py`
  Read-only benchmark setup and evaluation logic.
- `research/results.tsv`
  Append-only local run ledger.
- `research/live/`
  The current promoted local master snapshot and DAG.
- `research/`
  Notes, campaign state, experiment records, and templates.
- `.opencode/agent/`
  The checked-in OpenCode agents: `autolab`, `planner`, `experiment-worker`,
  `reviewer`, `memory-keeper`, `researcher`, and `reporter`.
- `.pi/`
  Optional Pi Agent project settings, role agents, and the `/autolab` prompt.
- `.agents/skills/`
  Shared repo-local skills.

## Local Setup

Install the repo and create your local operator env:

```bash
uv sync
hf auth login
hf auth whoami
opencode auth login
# optional for Hermes:
hermes setup
# optional for Pi Agent:
npm install -g @mariozechner/pi-coding-agent
```

If you have not warmed the shared Hugging Face cache yet, you can ask OpenCode
to do that as part of the first session. The exact script path is already in
[`AGENTS.md`](AGENTS.md).

## Start Hermes

From the pre-training project root:

```bash
uv run scripts/setup_hermes_profile.py --profile autolab
uv run scripts/print_hermes_kickoff.py --gpu-slots 1
autolab chat --toolsets "terminal,file,web,skills,delegation,clarify"
```

Hermes loads [`AGENTS.md`](AGENTS.md)
automatically, so the repo intentionally does not ship `.hermes.md`.

Use the parent Hermes session to delegate planner, reviewer, researcher,
reporter, experiment-worker, and memory-keeper roles. Keep Hermes child
concurrency at 3 or fewer per parent session. Use
`uv run scripts/hermes_worker.py create ...` plus
`uv run scripts/hermes_worker.py delegate <experiment-id>` to reserve each
experiment worktree and print the exact `delegate_task(...)` payload for the
worker.

## Start Pi Agent

From the pre-training project root:

```bash
uv run scripts/print_pi_kickoff.py --gpu-slots 1
pi
```

Run the project prompt template:

```text
/autolab "recent-master: follow-ups" 1 3
```

Pi uses `.pi/settings.json` to load `pi-subagents`, `.pi/agents/` for the
Autolab roles, and `scripts/pi_worker.py` for isolated experiment workers.

## Start OpenCode

From the pre-training project root:

```bash
opencode
```

Use the `autolab` primary agent. The normal pattern is:

1. Open OpenCode in the pre-training project root.
2. Give the `autolab` agent a short goal.
3. Let the repo agents and `AGENTS.md` drive the scripts.

You do not need to memorize the benchmark commands from the README.

## Simple Prompts

Use prompts like these with the `autolab` agent:

- `Refresh the local promoted master, review the notebook, and propose up to 3 fresh single-change experiments.`
- `Check whether the shared HF cache is ready. If not, run the one-time prepare path, then refresh local master.`
- `Create one isolated worker for a warmdown-ratio experiment, launch it, and tell me the experiment id, job id, and log path.`
- `Review the current reporter state and tell me whether any active experiments are duplicated or stale.`
- `Take the latest completed run, record it locally, tell me whether it promoted, and draft the note for memory-keeper.`
- `Compare this repo's upstream-tracked files against karpathy/autoresearch and summarize the diffs without applying them.`

If you want a longer parent-session kickoff prompt, run:

```bash
uv run scripts/print_opencode_kickoff.py --gpu-slots 1
```

## Autonomous Run Example

One concrete way to send off an autonomous local autoresearch session is:

1. Make sure your local env is loaded and the shared Hugging Face bucket exists:

```bash
. ~/.autolab/credentials
hf buckets create "$AUTOLAB_HF_BUCKET" --private --exist-ok
opencode
```

2. In OpenCode, use the `autolab` primary agent with a prompt like:

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

Use as many concurrent experiment-workers as possible.
Do not stop until all you have completed a full pass of successful experiments.
```

That prompt is enough for the checked-in agents plus
[`AGENTS.md`](AGENTS.md) to route the work through
the repo scripts, HF Jobs, HF buckets, and the local results ledger.

## Operating Model

- Refresh from the current local promoted master before a fresh experiment.
- Edit `train.py` only unless the task explicitly says otherwise.
- Never modify `prepare.py`.
- Make exactly one hypothesis change per run.
- Record every completed run in `research/results.tsv`.
- Local promotion only happens when observed `val_bpb` beats current master.

## Where To Look Next

- [`AGENTS.md`](AGENTS.md)
  Repo rules and the agent operating contract.
- [docs/opencode-workflow.md](docs/opencode-workflow.md)
  Full parent-session and worker workflow.
- [docs/hermes-subagents-guide.md](docs/hermes-subagents-guide.md)
  Hermes profile, kickoff, and delegation workflow.
- [docs/pi-subagents-guide.md](docs/pi-subagents-guide.md)
  Optional secondary Pi Agent-native integration.
- [docs/claude-subagents-guide.md](docs/claude-subagents-guide.md)
  Optional secondary Claude Code-native integration.
- [docs/codex-subagents-guide.md](docs/codex-subagents-guide.md)
  Optional secondary Codex-native integration.
- [docs/script-reference.md](docs/script-reference.md)
  Direct script interfaces, if you need them.
- [docs/getting-started.md](docs/getting-started.md)
  More detailed local setup notes.
- [docs/troubleshooting.md](docs/troubleshooting.md)
  Common local operator issues.

## Contribution Model

- Tooling, docs, templates, and control-plane changes belong in git history
  here.
- Benchmark runs are recorded locally in `research/results.tsv`.
- Current-master promotions happen locally from recorded winning runs.
- Failed experiment history belongs in `research/notes.md`,
  `research/do-not-repeat.md`, `research/experiments/`, and Trackio, not as a
  long tail of benchmark commits.
