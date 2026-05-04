# Codex Subagents Guide

OpenCode is the canonical control plane for this repo.

This guide describes the secondary Codex-native integration. It follows the
same local workflow:

- no hosted Autolab backend
- no Gastown assets or terminology
- local promoted master in `train_orig.py`, `research/live/master.json`, and
  `research/results.tsv`
- managed benchmark runs through Hugging Face Jobs
- observability through Trackio

The Codex-native pieces are:

- `.codex/config.toml`
- `.codex/agents/planner.toml`
- `.codex/agents/experiment-worker.toml`
- `.codex/agents/memory-keeper.toml`
- `.codex/agents/reviewer.toml`
- `.codex/agents/reporter.toml`
- `.codex/agents/researcher.toml`

## Recommended Start

Start Codex in the pre-training project root and let the main session spawn the checked-in
subagents.

For a longer prompt skeleton:

```bash
uv run scripts/print_codex_kickoff.py --gpu-slots 1
```

## Workflow

The Codex-native flow mirrors the OpenCode flow:

1. read `AGENTS.md`
2. refresh from local promoted master
3. spawn `planner` for fresh queues
4. spawn `reviewer` for rule checks
5. spawn `experiment_worker` for exactly one managed HF Jobs run
6. spawn `memory_keeper` to persist durable notes
7. spawn `reporter` for Trackio and HF Jobs summaries

## Concurrency

Codex custom agents in this repo use native project-scoped agent files and the
same local scripts as OpenCode, but this guide does not assume a built-in
Codex worktree-isolation layer for benchmark workers.

Treat one active `experiment_worker` per checkout as the safe default. If you
want more parallel benchmark runs, start additional top-level Codex sessions in
separate git worktrees.

## Durable State

Use the same repo-local notebook and ledger as OpenCode:

- `research/notes.md`
- `research/do-not-repeat.md`
- `research/campaigns/`
- `research/experiments/`
- `research/results.tsv`

Use `research/templates/` as the canonical template source. Do not recreate a
parallel Codex-specific template tree.
