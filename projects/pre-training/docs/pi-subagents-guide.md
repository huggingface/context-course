# Pi Subagents Guide

OpenCode is the canonical control plane for this repo.

This guide describes the secondary Pi-native integration. It follows the same
local workflow:

- no hosted Autolab backend
- no Gastown assets or terminology
- local promoted master in `train_orig.py`, `research/live/master.json`, and
  `research/results.tsv`
- managed benchmark runs through Hugging Face Jobs
- observability through Trackio

## Checked-In Pi Assets

- `.pi/settings.json`
  Project Pi settings. It declares the `pi-subagents` package and keeps Pi
  session files under `.runtime/`.
- `.pi/APPEND_SYSTEM.md`
  Parent-session Autolab coordinator guidance appended to Pi's default prompt.
- `.pi/agents/`
  Project agents: `planner`, `reviewer`, `researcher`, `reporter`,
  `memory-keeper`, and `experiment-worker`.
- `.pi/prompts/autolab.md`
  A reusable `/autolab` parent-session kickoff prompt.
- `scripts/print_pi_kickoff.py`
  Prints a standard parent-session prompt.
- `scripts/pi_worker.py`
  Creates isolated worktrees and launches `experiment-worker` through Pi.

## Setup

Install Pi once if it is not already available:

```bash
npm install -g @mariozechner/pi-coding-agent
```

From the pre-training project root, start Pi:

```bash
pi
```

The project `.pi/settings.json` declares `npm:pi-subagents@0.22.0`. Pi should
install missing project packages on startup. If you prefer to install the
package explicitly, run:

```bash
pi install npm:pi-subagents@0.22.0 -l
```

Authenticate a provider with `/login`, or start Pi with the provider API key in
the environment.

## Parent Session

Refresh current benchmark truth before planning:

```bash
uv run scripts/refresh_master.py --fetch-dag
```

Print a kickoff prompt if you want a copy-paste skeleton:

```bash
uv run scripts/print_pi_kickoff.py --gpu-slots 1
```

Start Pi in the pre-training project root and run the project prompt template:

```text
/autolab "recent-master: follow-ups" 1 3
```

The parent session should use:

- `planner` for fresh queues
- `reviewer` for rule and comparability checks
- `researcher` for paper-derived ideas
- `reporter` for HF Jobs and Trackio status
- `memory-keeper` for durable markdown updates in the main checkout
- `experiment-worker` only from reserved experiment worktrees

## Useful Pi Commands

```text
/run planner "Propose up to 3 fresh single-change experiments for the current campaign."
/run reviewer "Review this planned experiment for stale-master, duplicate, and multi-change risk."
/parallel reporter "Summarize active HF Jobs and Trackio anomalies." -> reviewer "Check whether the next launch is comparable."
/run memory-keeper "Record this completed worker summary in the durable notebook."
```

`pi-subagents` also scans legacy `.agents/**/*.md` files. In this repo that
means the shared `.agents/skills/*/SKILL.md` files can appear in `/agents`.
Treat the canonical Pi role agents as the files under `.pi/agents/`.

Pi supports background subagent runs with `--bg`, but do not exceed real GPU
capacity for active experiment workers.

## Experiment Worker Flow

Create one explicit worktree reservation per experiment:

```bash
uv run scripts/pi_worker.py create exp-warmdown-20 \
  --campaign "schedule: shorter cooldowns" \
  --hypothesis "Shorten warmdown to test whether the long cooldown tail is wasting the fixed budget."
```

Launch the worker:

```bash
uv run scripts/pi_worker.py run exp-warmdown-20
```

The launcher runs Pi from the reserved worktree, invokes the project
`experiment-worker` agent, and exports:

- `AUTOLAB_CAMPAIGN`
- `AUTOLAB_EXPERIMENT_ID`
- `AUTOLAB_WORKER_ID`
- `AUTOLAB_HYPOTHESIS`
- `AUTOLAB_LOG_PATH`
- `AUTOLAB_EXPERIMENT_NOTE`

Use `--dry-run` to inspect the exact `pi -p` command and environment without
starting the worker.

When the run is fully recorded by `memory-keeper`, remove the worktree:

```bash
uv run scripts/pi_worker.py cleanup exp-warmdown-20
```

## Worktree Rules

The `pi-subagents` package has its own worktree option for generic parallel
coding tasks. For paid Autolab experiments, prefer `scripts/pi_worker.py`
instead because it reserves the experiment id, worktree, note path, and log path
using the same repo-local state as the OpenCode and Hermes launchers.

The parent Pi session stays in the main checkout. Experiment workers run from
`.runtime/worktrees/<experiment-id>/`.

## Durable State

Use the same repo-local notebook and ledger as OpenCode:

- `research/notes.md`
- `research/do-not-repeat.md`
- `research/campaigns/`
- `research/experiments/`
- `research/results.tsv`

Use `research/templates/` as the canonical template source. Do not recreate a
parallel Pi-specific template tree.
