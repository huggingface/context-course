#!/usr/bin/env python3
"""Print a parent-session kickoff prompt for post-training Pi subagents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_prompt(project_root: Path, campaign: str, gpu_slots: int, max_ideas: int) -> str:
    posttrain_command = f"/posttrain {json.dumps(campaign)} {gpu_slots} {max_ideas}"
    worker_phrase = "job" if gpu_slots == 1 else "jobs"
    return f"""Open Pi in:
{project_root}

This session should use the native Pi `/posttrain` workflow with the project
`pi-subagents` setup.

One-time local setup, if needed:
- `npm install -g @mariozechner/pi-coding-agent`
- start `pi` once in this project so `.pi/settings.json` can install `pi-subagents`
- set `POSTTRAIN_HF_BUCKET` to a private Hugging Face bucket

Start with:
- `pi`
- `{posttrain_command}`

Use a parent prompt like:

You are coordinating NanoChat post-training experiments in this project with Pi.

Read:
- AGENTS.md
- README.md
- program.md
- docs/pi-subagents-guide.md
- research/notes.md
- research/results.tsv
- train.py
- prepare.py
- evaluate.py
- scripts/hf_job.py

Use `planner` for up to {max_ideas} fresh, non-duplicate method ideas for the
campaign "{campaign}".

Use `reviewer` for benchmark-integrity checks, `researcher` for outside ideas,
`reporter` for Hugging Face Jobs status, and `memory-keeper` after each run to
update the durable notebook.

Do not allow more than {gpu_slots} active managed experiment {worker_phrase}.
Use `experiment-worker` for exactly one coherent method change at a time.

Keep experiments comparable:
- work in this post-training project, not ../pre-training
- prefer editing train.py only
- do not modify evaluate.py
- do not alter the submitted NanoChat architecture
- do not train on eval examples
- save the best checkpoint to final_model/
- run the fixed evaluator before reporting a score
- use `uv run scripts/hf_job.py launch --mode experiment` for managed runs
- record completed runs in research/notes.md and research/results.tsv
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a standard kickoff prompt for the post-training Pi workflow."
    )
    parser.add_argument(
        "--campaign",
        default="nanochat post-training improvements",
        help="Campaign name to mention in the kickoff prompt.",
    )
    parser.add_argument(
        "--gpu-slots",
        type=int,
        default=1,
        help="Maximum concurrent managed experiment jobs to allow.",
    )
    parser.add_argument(
        "--max-ideas",
        type=int,
        default=3,
        help="Maximum number of experiment ideas to ask the planner for.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    print(build_prompt(project_root, args.campaign, args.gpu_slots, args.max_ideas))


if __name__ == "__main__":
    main()
