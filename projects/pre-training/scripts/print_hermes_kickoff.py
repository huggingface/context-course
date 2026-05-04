#!/usr/bin/env python3
"""Print a parent-session kickoff prompt for the repo's Hermes workflow."""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_TOOLSETS = "terminal,file,web,skills,delegation,clarify"


def build_prompt(repo_root: Path, campaign: str, gpu_slots: int, max_ideas: int) -> str:
    capped_children = min(gpu_slots, 3)
    return f"""Open Hermes in:
{repo_root}

Use the repo's `AGENTS.md` as the only checked-in rulebook. Do not add or depend on `.hermes.md`.

Start the parent session from the pre-training project root with toolsets:
`{DEFAULT_TOOLSETS}`

Use a parent prompt like:

You are coordinating Autolab experiments in this repo.

Read:
- AGENTS.md
- README.md
- docs/hermes-subagents-guide.md
- research/notes.md
- research/do-not-repeat.md
- research/campaigns/
- research/experiments/
- research/results.tsv
- research/live/master.json
- research/live/dag.json

Use `delegate_task` roles, not named checked-in Hermes subagents.

Ask the planner role for up to {max_ideas} fresh, non-duplicate experiments for the campaign "{campaign}".
Use reviewer for read-only rule checks, researcher for paper scouting, reporter for HF Jobs and Trackio status, and memory-keeper for durable markdown updates in the main checkout.

Do not run more than {capped_children} Hermes child workers concurrently in one parent session, even if you have more GPUs available. Hermes child delegation caps out at 3.
If you need more than 3 parallel workers, use multiple top-level Hermes sessions or stay on OpenCode for higher fan-out.

For an approved experiment:
- create the reserved worktree and note with `uv run scripts/hermes_worker.py create ...`
- print the worker payload with `uv run scripts/hermes_worker.py delegate <experiment-id>`
- paste that payload into `delegate_task(...)`
- keep the parent session and memory-keeper in the main checkout

Keep all experiments comparable:
- refresh from current local promoted master
- edit `train.py` only unless explicitly authorized otherwise
- one hypothesis change per run
- run the managed HF Jobs benchmark path
- submit only if local `val_bpb` beats current master
- leave Hermes `memory` out of the default toolsets so repo markdown stays the durable record
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a standard kickoff prompt for the repo's Hermes delegation workflow."
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
