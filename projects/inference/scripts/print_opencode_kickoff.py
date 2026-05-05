#!/usr/bin/env python3
"""Print a parent-session kickoff prompt for inference optimization."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_prompt(project_root: Path, target: str, max_candidates: int) -> str:
    return f"""Open OpenCode in:
{project_root}

Use the `inference-lab` primary agent in the inference project root.

Use a parent prompt like:

You are coordinating local llama.cpp inference optimization in this project.

Read:
- AGENTS.md
- README.md
- docs/opencode-workflow.md
- .agents/skills/huggingface-local-models/SKILL.md
- research/results.tsv
- research/notes.md
- research/do-not-repeat.md

Target model or repo:
{target}

First ask `benchmarker` to measure a reproducible baseline. Then ask
`optimizer` for up to {max_candidates} one-variable speed candidates. For the
best candidate, ask `benchmarker` to run the same benchmark and append the
result to research/results.tsv.

Keep comparisons honest:
- same model and exact GGUF unless the change is explicitly quant/model choice
- same prompt and max_tokens
- same context
- same llama.cpp build/backend
- one changed speed variable per benchmark
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print an OpenCode kickoff prompt for inference optimization."
    )
    parser.add_argument(
        "--target",
        default="<owner/repo> or current running llama-server endpoint",
        help="target model repo or endpoint description",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=3,
        help="maximum number of optimizer candidates to request",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    print(build_prompt(project_root, args.target, args.max_candidates))


if __name__ == "__main__":
    main()
