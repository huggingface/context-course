#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ".runtime"
WORKTREE_ROOT = RUNTIME_DIR / "worktrees"
STATE_DIR = RUNTIME_DIR / "opencode-workers"
EXPERIMENT_DIR = ROOT / "research" / "experiments"
LIVE_DIR = ROOT / "research" / "live"
MASTER_PATH = LIVE_DIR / "master.json"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_id(name: str, value: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise SystemExit(f"{name} must match {ID_PATTERN.pattern!r}: {value!r}")
    return value


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd or ROOT, env=env, text=True, capture_output=True, check=False)


def require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise SystemExit(f"could not find `{name}` in PATH")


def load_master_snapshot() -> dict[str, object]:
    if not MASTER_PATH.exists():
        return {}
    try:
        payload = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def worker_state_path(experiment_id: str) -> Path:
    return STATE_DIR / f"{experiment_id}.json"


def worktree_path(experiment_id: str) -> Path:
    return WORKTREE_ROOT / experiment_id


def experiment_note_path(experiment_id: str) -> Path:
    return EXPERIMENT_DIR / f"{experiment_id}.md"


def experiment_log_path(experiment_id: str) -> Path:
    return LIVE_DIR / f"{experiment_id}.log"


def write_state(state: dict[str, object]) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = worker_state_path(str(state["experiment_id"]))
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_state(experiment_id: str) -> dict[str, object]:
    path = worker_state_path(experiment_id)
    if not path.exists():
        raise SystemExit(f"missing worker state: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"failed to parse worker state {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"unexpected worker state payload in {path}")
    return payload


def ensure_worktree(target: Path) -> None:
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    result = run(["git", "worktree", "add", "--detach", str(target)])
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "git worktree add failed")


def worker_env(state: dict[str, object]) -> dict[str, str]:
    return {
        "AUTOLAB_CAMPAIGN": str(state["campaign"]),
        "AUTOLAB_EXPERIMENT_ID": str(state["experiment_id"]),
        "AUTOLAB_WORKER_ID": str(state["worker_id"]),
        "AUTOLAB_HYPOTHESIS": str(state["hypothesis"]),
        "AUTOLAB_LOG_PATH": str(state["log_path"]),
        "AUTOLAB_EXPERIMENT_NOTE": str(state["note_path"]),
    }


def _master_val_text(state: dict[str, object]) -> str:
    master_val = state.get("master_val_bpb")
    if isinstance(master_val, (int, float)):
        return f"{master_val:.6f}"
    return "<value>"


def build_note(state: dict[str, object]) -> str:
    return f"""# Experiment: {state["title"]}

## Campaign

- Campaign: `{state["campaign"]}`

## Hypothesis

{state["hypothesis"]}

## Parent Context

- Parent master hash: `{state.get("master_hash") or "<hash>"}`
- Master val_bpb at dispatch: `{_master_val_text(state)}`
- Worker id: `{state["worker_id"]}`
- Worktree: `{state["worktree_path"]}`

## Single Variable

<What exact variable, knob, or logic change is being tested?>

## Expected Upside

<Why this might improve val_bpb or effective throughput inside the 5-minute budget>

## Duplicate Check

<Why this is not a duplicate of an open or recent experiment>

## Runtime

- Log path: `{state["log_path"]}`
- OpenCode launcher: `uv run scripts/opencode_worker.py run {state["experiment_id"]}`
- Pi launcher: `uv run scripts/pi_worker.py run {state["experiment_id"]}`
- Hermes delegate payload: `uv run scripts/hermes_worker.py delegate {state["experiment_id"]}`

## Allowed Edit Scope

- `train.py` only

## Run Plan

- Refresh master with `uv run scripts/refresh_master.py --fetch-dag`
- Run `uv run scripts/hf_job.py preflight`
- Run `uv run scripts/hf_job.py launch --mode experiment`
- Stream logs to the reserved path
- Parse `uv run scripts/parse_metric.py {state["log_path"]}`

## Result

- Local val_bpb: `<value>`
- Submitted: `yes|no`
- Interpretation: `<one or two sentences>`
- Failure mode, if any: `<brief note>`

## Memory-Keeper Handoff

- One short note for `research/notes.md`: `<summary>`
- Any do-not-repeat update: `<summary or none>`
"""


def write_note(path: Path, state: dict[str, object], overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return
    path.write_text(build_note(state), encoding="utf-8")


def create_worker_state(
    *,
    experiment_id: str,
    campaign: str,
    hypothesis: str,
    worker_id: str | None = None,
    title: str | None = None,
    overwrite_note: bool = False,
) -> tuple[dict[str, object], Path]:
    experiment_id = ensure_id("experiment_id", experiment_id)
    worker_id = ensure_id("worker_id", worker_id or experiment_id)
    note_path = experiment_note_path(experiment_id)
    log_path = experiment_log_path(experiment_id)
    worktree = worktree_path(experiment_id)
    ensure_worktree(worktree)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    log_path.touch(exist_ok=True)

    master = load_master_snapshot()
    state = {
        "experiment_id": experiment_id,
        "campaign": campaign,
        "hypothesis": hypothesis,
        "worker_id": worker_id,
        "title": title or hypothesis,
        "master_hash": master.get("hash"),
        "master_val_bpb": master.get("val_bpb"),
        "note_path": str(note_path),
        "log_path": str(log_path),
        "worktree_path": str(worktree),
        "created_at": utc_now(),
    }
    write_note(note_path, state, overwrite=overwrite_note)
    state_path = write_state(state)
    return state, state_path


def cleanup_worker_state(experiment_id: str, *, force: bool = False) -> int:
    state = load_state(experiment_id)
    worktree = Path(str(state["worktree_path"]))
    state_path = worker_state_path(experiment_id)
    if worktree.exists():
        status = run(["git", "status", "--short"], cwd=worktree)
        if status.returncode != 0:
            raise SystemExit(status.stderr.strip() or status.stdout.strip() or f"git status failed in {worktree}")
        if status.stdout.strip() and not force:
            raise SystemExit(f"worktree has uncommitted changes: {worktree}\npass --force to remove it anyway")
        argv = ["git", "worktree", "remove", str(worktree)]
        if force:
            argv.append("--force")
        result = run(argv)
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip() or result.stdout.strip() or "git worktree remove failed")
    if state_path.exists():
        state_path.unlink()
    return 0


def build_worker_contract(state: dict[str, object], *, include_shell_prelude: bool) -> str:
    lines = [
        "You are executing one isolated Autolab experiment in this worktree.",
        "",
        f"Worktree: {state['worktree_path']}",
        f"Campaign: {state['campaign']}",
        f"Experiment id: {state['experiment_id']}",
        f"Worker id: {state['worker_id']}",
        f"Hypothesis: {state['hypothesis']}",
        f"Reserved log path: {state['log_path']}",
        f"Durable note path in the main checkout: {state['note_path']}",
        "",
        "Read `AGENTS.md` first, then follow the repo rules exactly.",
        "",
        "Allowed edit scope:",
        "- edit `train.py` only unless explicitly authorized otherwise",
        "- never edit `prepare.py`",
        "- make exactly one hypothesis change",
        "",
        "Before editing:",
        "- confirm the assigned hypothesis is still fresh relative to current master and recent notes",
        "- confirm the expected benchmark command, log path, and worker id",
        "- state the exact single variable you will change",
    ]

    if include_shell_prelude:
        lines.extend(
            [
                "",
                "Before launch, set the worker shell context explicitly:",
                f"- `cd {shlex.quote(str(state['worktree_path']))}`",
            ]
        )
        for key, value in worker_env(state).items():
            lines.append(f"- `export {key}={shlex.quote(value)}`")

    lines.extend(
        [
            "",
            "Execution contract:",
            "- start from refreshed local master, not stale local edits",
            "- run `uv run scripts/refresh_master.py --fetch-dag` before editing unless the parent confirms the worktree is already refreshed for this hypothesis",
            "- run `uv run scripts/hf_job.py preflight`",
            "- run exactly one managed experiment with `uv run scripts/hf_job.py launch --mode experiment`",
            f"- stream logs to `{state['log_path']}`",
            f"- parse the final metric with `uv run scripts/parse_metric.py {state['log_path']}`",
            '- record the run with `uv run scripts/submit_patch.py --comment "..."`',
            "- local promotion only happens if `val_bpb` beats current master",
            "",
            "Final report must include:",
            "- hypothesis tested",
            "- parent master hash",
            "- exact single variable changed",
            "- log path used",
            "- local `val_bpb` or failure state",
            "- submit or no-submit",
            "- one short interpretation",
            "- one short note for `memory-keeper`",
            "",
            "Stop and report back instead of improvising if:",
            "- master changed materially",
            "- the task requires broader refactoring",
            "- the hypothesis is stale or duplicated by newer evidence",
            "- the run fails to produce a valid metric",
            "",
            "Do not edit the durable note in the main checkout from this worktree. In your final response, include the note text that `memory-keeper` should record.",
        ]
    )
    return "\n".join(lines)
