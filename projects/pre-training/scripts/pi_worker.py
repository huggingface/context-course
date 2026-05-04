#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from worker_common import (
    ROOT,
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
    run_command = ["uv", "run", "scripts/pi_worker.py", "run", str(state["experiment_id"])]
    print(json.dumps(state, indent=2, sort_keys=True))
    print(f"state: {state_path}")
    print(f"run: {' '.join(shlex.quote(part) for part in run_command)}")
    print(f"opencode fallback: uv run scripts/opencode_worker.py run {shlex.quote(str(state['experiment_id']))}")
    print(f"hermes delegate: uv run scripts/hermes_worker.py delegate {shlex.quote(str(state['experiment_id']))}")
    return 0


def build_run_prompt(state: dict[str, object]) -> str:
    experiment_id = str(state["experiment_id"])
    hypothesis = str(state["hypothesis"])
    log_path = str(state["log_path"])
    note_path = str(state["note_path"])
    return (
        "/run experiment-worker "
        f"Execute the reserved Autolab experiment `{experiment_id}` in this worktree. "
        "Use the AUTOLAB_* environment variables for the campaign, worker id, "
        f"hypothesis, and log path. Hypothesis: {hypothesis} "
        f"Stream logs to {log_path}. "
        f"Do not edit the durable note at {note_path}; include the memory-keeper handoff in the final report."
    )


def resolve_pi_bin(args: argparse.Namespace) -> str:
    if args.pi_bin:
        return args.pi_bin
    if os.environ.get("AUTOLAB_PI_BIN"):
        return str(os.environ["AUTOLAB_PI_BIN"])
    found = shutil.which("pi")
    if found:
        return found
    if args.dry_run:
        return "pi"
    return require_tool("pi")


def run_command_for_worker(args: argparse.Namespace) -> int:
    state = load_state(args.experiment_id)
    pi_bin = resolve_pi_bin(args)
    worktree = Path(str(state["worktree_path"]))
    if not worktree.exists():
        raise SystemExit(f"missing worktree: {worktree}")

    experiment_id = str(state["experiment_id"])
    session_dir = ROOT / ".runtime" / "pi-worker-sessions" / experiment_id
    env = os.environ.copy()
    env.update(worker_env(state))
    env["PI_CODING_AGENT_SESSION_DIR"] = str(session_dir)

    prompt = build_run_prompt(state)
    argv = [pi_bin, "--session-dir", str(session_dir), "-p", prompt]

    if args.dry_run:
        print("cwd:", worktree)
        print("command:", " ".join(shlex.quote(part) for part in argv))
        for key in (
            "AUTOLAB_CAMPAIGN",
            "AUTOLAB_EXPERIMENT_ID",
            "AUTOLAB_WORKER_ID",
            "AUTOLAB_HYPOTHESIS",
            "AUTOLAB_LOG_PATH",
            "AUTOLAB_EXPERIMENT_NOTE",
            "PI_CODING_AGENT_SESSION_DIR",
        ):
            print(f"{key}={env[key]}")
        return 0

    session_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(argv, cwd=worktree, env=env, check=False)
    return result.returncode


def cleanup_command(args: argparse.Namespace) -> int:
    return cleanup_worker_state(args.experiment_id, force=args.force)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create, run, and clean isolated Pi Autolab experiment workers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create an isolated worktree, state file, note, and reserved log path")
    create.add_argument("experiment_id", help="stable experiment identifier used for the worktree, note, and log")
    create.add_argument("--campaign", required=True, help="campaign name for this experiment")
    create.add_argument("--hypothesis", required=True, help="one-sentence experiment hypothesis")
    create.add_argument("--worker-id", help="logical worker id; defaults to the experiment id")
    create.add_argument("--title", help="note title; defaults to the hypothesis")
    create.add_argument("--overwrite-note", action="store_true", help="replace an existing experiment note")

    run_worker = subparsers.add_parser("run", help="run the isolated experiment worker through Pi")
    run_worker.add_argument("experiment_id", help="experiment id created by the `create` command")
    run_worker.add_argument("--pi-bin", help="override the Pi executable")
    run_worker.add_argument("--dry-run", action="store_true", help="print the exact command and environment without running Pi")

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
