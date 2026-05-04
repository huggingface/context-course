# Claude Code Subagents Guide

OpenCode is the canonical control plane for this repo.

This guide describes the secondary Claude Code-native integration. It follows
the same local workflow:

- no hosted Autolab backend
- no Gastown assets or terminology
- local promoted master in `train_orig.py`, `research/live/master.json`, and
  `research/results.tsv`
- managed benchmark runs through Hugging Face Jobs
- observability through Trackio

The Claude Code-native pieces are:

- `CLAUDE.md`
- `.claude/settings.json`
- `.claude/agents/autolab.md`
- `.claude/agents/planner.md`
- `.claude/agents/experiment-worker.md`
- `.claude/agents/memory-keeper.md`
- `.claude/agents/reviewer.md`
- `.claude/agents/reporter.md`
- `.claude/agents/researcher.md`

## Recommended Start

From the pre-training project root:

```bash
claude --agent autolab
```

Treat `claude --agent autolab` as the canonical launch path for this repo. Some
Claude Code builds may not list project agents consistently in `claude agents`
or `/agents`, even when direct launch works.

For a longer prompt skeleton:

```bash
uv run scripts/print_claude_kickoff.py --gpu-slots 1
```

## Workflow

The Claude-native flow mirrors the OpenCode flow:

1. read `AGENTS.md`
2. refresh from local promoted master
3. use `planner` for fresh queues
4. use `reviewer` for rule checks
5. use `experiment-worker` for exactly one managed HF Jobs run
6. use `memory-keeper` to persist durable notes in the main checkout
7. use `reporter` for Trackio and HF Jobs summaries

The worker is configured with `background: true` and `isolation: worktree`, so
it uses Claude Code's native worktree integration rather than a repo-specific
worker launcher.

## Durable State

Use the same repo-local notebook and ledger as OpenCode:

- `research/notes.md`
- `research/do-not-repeat.md`
- `research/campaigns/`
- `research/experiments/`
- `research/results.tsv`

Use `research/templates/` as the canonical template source. Do not recreate a
parallel Claude-specific template tree.
