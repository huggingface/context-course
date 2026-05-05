#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex

from worker_common import build_worker_contract, cleanup_worker_state, create_worker_state, load_state


DEFAULT_TOOLSETS = ["terminal", "file", "skills"]


def build_delegate_payload(
    state: dict[str, object],
    *,
    toolsets: list[str],
    max_iterations: int,
) -> dict[str, object]:
    experiment_id = str(state["experiment_id"])
    worktree = str(state["worktree_path"])
    goal = f"Execute the Autolab experiment `{experiment_id}` from worktree `{worktree}` and return the required structured summary."
    return {
        "goal": goal,
        "context": build_worker_contract(state, include_shell_prelude=True),
        "toolsets": toolsets,
        "max_iterations": max_iterations,
    }


def build_delegate_snippet(payload: dict[str, object]) -> str:
    context = str(payload["context"]).replace('"""', '\\"\\"\\"')
    goal = json.dumps(payload["goal"])
    toolsets = json.dumps(payload["toolsets"])
    max_iterations = int(payload["max_iterations"])
    return (
        "delegate_task(\n"
        f"    goal={goal},\n"
        f'    context="""{context}""",\n'
        f"    toolsets={toolsets},\n"
        f"    max_iterations={max_iterations},\n"
        ")"
    )


def create_command(args: argparse.Namespace) -> int:
    state, state_path = create_worker_state(
        experiment_id=args.experiment_id,
        campaign=args.campaign,
        hypothesis=args.hypothesis,
        worker_id=args.worker_id,
        title=args.title,
        overwrite_note=args.overwrite_note,
    )
    print(json.dumps(state, indent=2, sort_keys=True))
    print(f"state: {state_path}")
    print(f"delegate: uv run scripts/hermes_worker.py delegate {shlex.quote(str(state['experiment_id']))}")
    print(f"pi run: uv run scripts/pi_worker.py run {shlex.quote(str(state['experiment_id']))}")
    print(f"run: uv run scripts/opencode_worker.py run {shlex.quote(str(state['experiment_id']))}")
    return 0


def delegate_command(args: argparse.Namespace) -> int:
    state = load_state(args.experiment_id)
    toolsets = [item.strip() for item in args.toolsets.split(",") if item.strip()]
    payload = build_delegate_payload(state, toolsets=toolsets, max_iterations=args.max_iterations)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("# Paste this into the parent Hermes session:")
    print(build_delegate_snippet(payload))
    print()
    print("# Payload")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cleanup_command(args: argparse.Namespace) -> int:
    return cleanup_worker_state(args.experiment_id, force=args.force)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, print delegate_task payloads for, and clean isolated Hermes Autolab experiment workers."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create an isolated worktree, state file, note, and reserved log path")
    create.add_argument("experiment_id", help="stable experiment identifier used for the worktree, note, and log")
    create.add_argument("--campaign", required=True, help="campaign name for this experiment")
    create.add_argument("--hypothesis", required=True, help="one-sentence experiment hypothesis")
    create.add_argument("--worker-id", help="logical worker id; defaults to the experiment id")
    create.add_argument("--title", help="note title; defaults to the hypothesis")
    create.add_argument("--overwrite-note", action="store_true", help="replace an existing experiment note")

    delegate = subparsers.add_parser("delegate", help="print a ready-to-use Hermes delegate_task payload")
    delegate.add_argument("experiment_id", help="experiment id created by the `create` command")
    delegate.add_argument(
        "--toolsets",
        default=",".join(DEFAULT_TOOLSETS),
        help="comma-separated Hermes toolsets for the child worker",
    )
    delegate.add_argument("--max-iterations", type=int, default=50, help="delegate_task iteration budget")
    delegate.add_argument("--json", action="store_true", help="print only the payload JSON")

    cleanup = subparsers.add_parser("cleanup", help="remove a finished worktree and its local worker state")
    cleanup.add_argument("experiment_id", help="experiment id created by the `create` command")
    cleanup.add_argument("--force", action="store_true", help="remove the worktree even when it still has local changes")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "create":
        return create_command(args)
    if args.command == "delegate":
        return delegate_command(args)
    if args.command == "cleanup":
        return cleanup_command(args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
