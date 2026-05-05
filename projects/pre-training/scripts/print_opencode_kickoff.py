#!/usr/bin/env python3
"""Print a parent-session kickoff prompt for the repo's OpenCode workflow."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_prompt(repo_root: Path, campaign: str, gpu_slots: int, max_ideas: int) -> str:
    return f"""Open OpenCode in:
{repo_root}

Use the `autolab` primary agent in the pre-training project root.

Use a parent prompt like:

You are coordinating Autolab experiments in this repo.

Read:
- AGENTS.md
- README.md
- docs/opencode-workflow.md
- research/notes.md
- research/do-not-repeat.md
- research/campaigns/
- research/experiments/
- research/results.tsv
- research/live/master.json
- research/live/dag.json

Ask `planner` for up to {max_ideas} fresh, non-duplicate experiments for the
campaign "{campaign}".

Do not run more than {gpu_slots} isolated experiment workers concurrently.
Use `uv run scripts/opencode_worker.py create ...` to create each worktree and
`uv run scripts/opencode_worker.py run <experiment-id>` to launch it.
Use `reviewer` for read-only rule checks, `reporter` for Trackio/HF Jobs status,
and `memory-keeper` after each worker finishes to update the durable notebook.

Keep all experiments comparable:
- refresh from current master
- edit `train.py` only unless explicitly authorized otherwise
- one hypothesis change per run
- run the canonical managed benchmark
- record every completed run locally
- promote only if local `val_bpb` beats current master
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a standard kickoff prompt for the repo's OpenCode workflow."
    )
    parser.add_argument(
        "--campaign",
        default="recent-master: follow-ups",
        help="campaign name to mention in the kickoff prompt",
    )
    parser.add_argument(
        "--gpu-slots",
        type=int,
        default=1,
        help="maximum concurrent experiment workers to allow",
    )
    parser.add_argument(
        "--max-ideas",
        type=int,
        default=3,
        help="maximum number of experiment ideas to ask the planner for",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    print(build_prompt(repo_root, args.campaign, args.gpu_slots, args.max_ideas))


if __name__ == "__main__":
    main()
