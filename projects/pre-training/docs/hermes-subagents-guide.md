# Winning Autolab With Hermes Delegation

This guide adds a Hermes-native coordination path to this repo while keeping
OpenCode canonical.

The goal is unchanged: maximize useful, non-duplicated experiments per
GPU-hour until you beat current master on `val_bpb`.

## Concept Map

- repo rules -> `AGENTS.md`
- Hermes parent workflow -> `delegate_task(...)`
- repo-local shared skills -> `.agents/skills/`
- experiment worker state -> `scripts/hermes_worker.py` and `scripts/opencode_worker.py`
- durable ledger -> `research/notes.md`, `research/do-not-repeat.md`, and
  `research/experiments/`

## Checked-In Hermes Assets

- `AGENTS.md`
  The only checked-in repo rulebook Hermes should load.
- `docs/hermes-subagents-guide.md`
  Hermes-specific operator guide.
- `scripts/setup_hermes_profile.py`
  Creates or updates a local Hermes `autolab` profile home and wires in the
  repo skill directory.
- `scripts/print_hermes_kickoff.py`
  Prints a standard parent-session kickoff prompt.
- `scripts/hermes_worker.py`
  Creates isolated worktrees and prints ready-to-use `delegate_task` payloads
  for experiment workers.
- `.agents/skills/`
  Shared repo-local skills, including `autolab-hermes-delegation`.

The repo intentionally does **not** ship `.hermes.md`. Hermes gives
`.hermes.md` higher priority than `AGENTS.md`, which would create a second
drifting rulebook.

## Minimal Workflow

1. Refresh current local benchmark truth:

```bash
uv run scripts/refresh_master.py --fetch-dag
```

2. Create or update the local Hermes profile home:

```bash
uv run scripts/setup_hermes_profile.py --profile autolab
```

This script prefers `hermes profile create autolab --clone` when your Hermes
build supports profile subcommands. On older builds that only expose
`HERMES_HOME`, it creates `~/.hermes/profiles/autolab/` directly and writes an
`autolab` wrapper in `~/.local/bin/`.

3. If you have not configured a model/provider for Hermes yet, do that once:

```bash
autolab setup
```

Fallback if the wrapper is not on `PATH` yet:

```bash
HERMES_HOME=~/.hermes/profiles/autolab hermes setup
```

4. Print a kickoff prompt and start the parent session from the pre-training project root:

```bash
uv run scripts/print_hermes_kickoff.py --gpu-slots 1
autolab chat --toolsets "terminal,file,web,skills,delegation,clarify"
```

5. In the parent Hermes session:

- use `delegate_task(...)` for planner, reviewer, researcher, reporter, and
  memory-keeper
- keep Hermes `memory` out of the default toolsets so repo markdown stays the
  durable record
- keep Hermes child concurrency at `min(gpu_slots, 3)`
- if you need more than 3 child workers, use multiple top-level Hermes sessions
  or use OpenCode instead

## Role Contracts

Use the `autolab-hermes-delegation` skill as the canonical contract for Hermes
roles. The default toolsets are:

- planner and reviewer: `["file"]`
- memory-keeper: `["file"]`
- researcher: `["web", "file", "skills", "terminal"]`
- reporter and experiment-worker: `["terminal", "file", "skills"]`

Hermes children get a fresh context, cannot ask the user for clarification,
cannot delegate again, and only return their final summary to the parent. Pass
the full role contract in every delegation call.

## Experiment Worker Flow

Create one explicit worktree reservation per experiment:

```bash
uv run scripts/hermes_worker.py create exp-warmdown-20 \
  --campaign "schedule: shorter cooldowns" \
  --hypothesis "Shorten warmdown to test whether the long cooldown tail is wasting the fixed budget."
```

Then print the worker payload:

```bash
uv run scripts/hermes_worker.py delegate exp-warmdown-20
```

Paste the emitted `delegate_task(...)` block into the parent Hermes session.
That payload includes:

- the absolute worktree path
- the experiment id
- the reserved log path
- the allowed edit scope
- the required commands
- the required final report fields

The worker stays in the isolated worktree. The parent session and
`memory-keeper` stay in the main checkout.

When the run is fully recorded, clean up the worktree:

```bash
uv run scripts/hermes_worker.py cleanup exp-warmdown-20
```

## Worktree Rules

- Do not enable profile-wide `worktree: true` for the Hermes parent by default.
  This repo expects the coordinating parent to stay in the main checkout.
- Use explicit worker worktrees through `scripts/hermes_worker.py` for paid
  experiment runs.
- `scripts/setup_hermes_profile.py` forces `worktree: false` in the Hermes
  profile config for that reason.

## What Good Looks Like

You are using the Hermes-native flow well when:

- `AGENTS.md` remains the only checked-in repo context file Hermes loads
- planners reject duplicate or stale ideas before a paid run starts
- each worker payload stays single-change and worktree-isolated
- memory updates happen in the main checkout after the worker summary returns
- no parent session tries to exceed Hermes' 3-child delegation ceiling
