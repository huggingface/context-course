# Autolab Pi Coordinator

This repository has a Pi-native secondary control plane.

Use `AGENTS.md` as the hard rulebook. OpenCode remains canonical, but Pi
sessions in this repo should use the same local promoted master, Hugging Face
Jobs, Trackio, and `research/results.tsv` workflow.

When coordinating Autolab work:

- read `docs/pi-subagents-guide.md` before planning experiments
- use project agents in `.pi/agents/` through `pi-subagents`
- use `planner` for fresh queues, `reviewer` for rule checks, `researcher` for
  paper-derived ideas, `reporter` for HF Jobs and Trackio status, and
  `memory-keeper` for durable markdown updates
- keep active `experiment-worker` runs at or below real GPU capacity
- create reserved experiment worktrees with `uv run scripts/pi_worker.py create ...`
- launch reserved Pi workers with `uv run scripts/pi_worker.py run <experiment-id>`
- keep paid experiment workers out of the main checkout
- keep every experiment to one `train.py` hypothesis change
- never claim success or local promotion without a completed benchmark and
  `uv run scripts/submit_patch.py --comment "..."`

If the user wants a full parent-session prompt, suggest:

```text
/autolab "recent-master: follow-ups" 1 3
```
