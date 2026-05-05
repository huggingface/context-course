#!/usr/bin/env python3
"""Print a parent-session kickoff prompt for the repo's Pi subagents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_prompt(repo_root: Path, campaign: str, gpu_slots: int, max_ideas: int) -> str:
    autolab_command = f"/autolab {json.dumps(campaign)} {gpu_slots} {max_ideas}"
    worker_phrase = "run" if gpu_slots == 1 else "runs"
    return f"""Open Pi in:
{repo_root}

OpenCode is the canonical control plane, but this session should use the native
Pi implementation with the project `pi-subagents` setup.

One-time local setup, if needed:
- `npm install -g @mariozechner/pi-coding-agent`
- start `pi` once in this repo so `.pi/settings.json` can install `pi-subagents`

Start with:
- `pi`
- `{autolab_command}`

Use a parent prompt like:

You are coordinating local Autolab experiments in this repo with Pi.

Read:
- AGENTS.md
- README.md
- docs/pi-subagents-guide.md
- research/notes.md
- research/do-not-repeat.md
- research/campaigns/
- research/experiments/
- research/results.tsv
- research/live/master.json
- research/live/dag.json

Use `planner` for up to {max_ideas} fresh, non-duplicate experiments for the
campaign "{campaign}".

Use `reviewer` for read-only rule checks, `researcher` for paper scouting,
`reporter` for Trackio/HF Jobs status, and `memory-keeper` after each worker
finishes to update the durable notebook in the main checkout.

Do not allow more than {gpu_slots} active `experiment-worker` {worker_phrase}. Use
`uv run scripts/pi_worker.py create ...` to create each reserved worktree and
`uv run scripts/pi_worker.py run <experiment-id>` to launch the Pi worker.

Keep all experiments comparable:
- refresh from current local master
- edit `train.py` only unless explicitly authorized otherwise
- one hypothesis change per run
- run the canonical managed benchmark on Hugging Face Jobs
- record every completed run locally
- promote only if local `val_bpb` beats current master
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a standard kickoff prompt for the repo's Pi subagent workflow."
    )
    parser.add_argument(
        "--campaign",
        default="recent-master: follow-ups",
        help="Campaign name to mention in the kickoff prompt.",
    )
    parser.add_argument(
        "--gpu-slots",
        type=int,
        default=1,
        help="Maximum concurrent experiment workers to allow.",
    )
    parser.add_argument(
        "--max-ideas",
        type=int,
        default=3,
        help="Maximum number of experiment ideas to ask the planner for.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    print(build_prompt(repo_root, args.campaign, args.gpu_slots, args.max_ideas))


if __name__ == "__main__":
    main()
