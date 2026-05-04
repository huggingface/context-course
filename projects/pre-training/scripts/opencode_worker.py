#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path

from worker_common import (
    build_worker_contract,
    cleanup_worker_state,
    create_worker_state,
    load_state,
    require_tool,
    worker_env,
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
    run_command = ["uv", "run", "scripts/opencode_worker.py", "run", str(state["experiment_id"])]
    pi_command = ["uv", "run", "scripts/pi_worker.py", "run", str(state["experiment_id"])]
    print(json.dumps(state, indent=2, sort_keys=True))
    print(f"state: {state_path}")
    print(f"run: {' '.join(shlex.quote(part) for part in run_command)}")
    print(f"pi run: {' '.join(shlex.quote(part) for part in pi_command)}")
    print(f"delegate: uv run scripts/hermes_worker.py delegate {shlex.quote(str(state['experiment_id']))}")
    return 0


def build_prompt(state: dict[str, object]) -> str:
    return build_worker_contract(state, include_shell_prelude=False)


def run_command_for_worker(args: argparse.Namespace) -> int:
    state = load_state(args.experiment_id)
    opencode_bin = args.opencode_bin or os.environ.get("AUTOLAB_OPENCODE_BIN") or require_tool("opencode")
    worktree = Path(str(state["worktree_path"]))
    if not worktree.exists():
        raise SystemExit(f"missing worktree: {worktree}")

    prompt = build_prompt(state)
    env = os.environ.copy()
    env.update(worker_env(state))

    argv = [opencode_bin, "run", "--agent", "experiment-worker", prompt]
    if args.dry_run:
        print("cwd:", worktree)
        print("command:", " ".join(shlex.quote(part) for part in argv))
        for key in ("AUTOLAB_CAMPAIGN", "AUTOLAB_EXPERIMENT_ID", "AUTOLAB_WORKER_ID", "AUTOLAB_HYPOTHESIS", "AUTOLAB_LOG_PATH"):
            print(f"{key}={env[key]}")
        return 0

    result = subprocess.run(argv, cwd=worktree, env=env, check=False)
    return result.returncode


def cleanup_command(args: argparse.Namespace) -> int:
    return cleanup_worker_state(args.experiment_id, force=args.force)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create, run, and clean isolated OpenCode Autolab experiment workers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create an isolated worktree, state file, note, and reserved log path")
    create.add_argument("experiment_id", help="stable experiment identifier used for the worktree, note, and log")
    create.add_argument("--campaign", required=True, help="campaign name for this experiment")
    create.add_argument("--hypothesis", required=True, help="one-sentence experiment hypothesis")
    create.add_argument("--worker-id", help="logical worker id; defaults to the experiment id")
    create.add_argument("--title", help="note title; defaults to the hypothesis")
    create.add_argument("--overwrite-note", action="store_true", help="replace an existing experiment note")

    run_worker = subparsers.add_parser("run", help="run the isolated experiment worker through OpenCode")
    run_worker.add_argument("experiment_id", help="experiment id created by the `create` command")
    run_worker.add_argument("--opencode-bin", help="override the OpenCode executable")
    run_worker.add_argument("--dry-run", action="store_true", help="print the exact command and environment without running OpenCode")

    cleanup = subparsers.add_parser("cleanup", help="remove a finished worktree and its local worker state")
    cleanup.add_argument("experiment_id", help="experiment id created by the `create` command")
    cleanup.add_argument("--force", action="store_true", help="remove the worktree even when it still has local changes")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "create":
        return create_command(args)
    if args.command == "run":
        return run_command_for_worker(args)
    if args.command == "cleanup":
        return cleanup_command(args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
