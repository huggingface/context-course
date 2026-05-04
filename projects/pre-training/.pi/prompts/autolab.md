---
description: Start a Pi-native Autolab multi-agent parent session.
argument-hint: "[campaign] [gpu-slots] [max-ideas]"
---

You are coordinating Autolab experiments in this repo using Pi and
`pi-subagents`.

Arguments:

- campaign: `$1` if provided, otherwise `recent-master: follow-ups`
- gpu slots: `$2` if provided, otherwise `1`
- max ideas: `$3` if provided, otherwise `3`

Read:

- `AGENTS.md`
- `README.md`
- `docs/pi-subagents-guide.md`
- `research/notes.md`
- `research/do-not-repeat.md`
- `research/campaigns/`
- `research/experiments/`
- `research/results.tsv`
- `research/live/master.json`
- `research/live/dag.json`

Use Pi project agents:

- `planner` for fresh experiment queues
- `reviewer` for rule and comparability checks
- `researcher` for paper-derived hypotheses
- `reporter` for Trackio and Hugging Face Jobs status
- `memory-keeper` for durable notes in the main checkout
- `experiment-worker` only through reserved worktrees

Ask `planner` for up to the requested max ideas for the requested campaign.
Reject duplicates or stale ideas before launching paid work.

Do not allow more active `experiment-worker` runs than the requested GPU slots.
Create isolated workers with `uv run scripts/pi_worker.py create ...`, launch
them with `uv run scripts/pi_worker.py run <experiment-id>`, and use
`memory-keeper` after each worker finishes.

Keep all experiments comparable:

- refresh from current local master
- edit `train.py` only unless explicitly authorized otherwise
- one hypothesis change per run
- run the canonical managed benchmark on Hugging Face Jobs
- record every completed run locally
- promote only if local `val_bpb` beats current master
