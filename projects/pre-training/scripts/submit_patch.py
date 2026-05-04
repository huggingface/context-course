#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from local_results import (
    RESULTS_PATH,
    ROOT,
    TRAIN_ORIG_PATH,
    TRAIN_PATH,
    append_result_row,
    current_master_snapshot,
    ensure_results_ledger,
    now_utc_iso,
    normalize_source,
    parse_float,
    rebuild_live_state,
    source_hash,
    stringify_field,
    truthy,
    write_current_master_source,
)


RUNTIME_DIR = ROOT / ".runtime"
LAST_JOB_PATH = RUNTIME_DIR / "hf-job-last.json"
SUMMARY_KEYS = {
    "val_bpb",
    "training_seconds",
    "total_seconds",
    "peak_vram_mb",
    "mfu_percent",
    "total_tokens_M",
    "num_steps",
    "num_params_M",
    "depth",
}


def coerce_value(raw: str) -> int | float | str:
    raw = raw.strip()
    for caster in (int, float):
        try:
            return caster(raw)
        except ValueError:
            continue
    return raw


def parse_metrics_text(text: str) -> dict[str, int | float | str]:
    metrics: dict[str, int | float | str] = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z_]+):\s+(.+)$", line.strip())
        if not match:
            continue
        key, value = match.groups()
        if key in SUMMARY_KEYS:
            metrics[key] = coerce_value(value)
    return metrics


def load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_hf_cli() -> str:
    explicit = os.environ.get("AUTOLAB_HF_CLI")
    if explicit:
        return explicit
    preferred = Path.home() / ".local" / "bin" / "hf"
    if preferred.exists():
        return str(preferred)
    fallback = shutil.which("hf")
    if fallback:
        return fallback
    raise SystemExit("could not find `hf`; install the Hugging Face CLI first")


def job_state_paths() -> list[Path]:
    paths: list[Path] = []
    paths.extend(sorted((ROOT / ".runtime" / "hf-jobs").glob("*.json")))
    paths.extend(sorted((ROOT / ".runtime" / "worktrees").glob("*/.runtime/hf-jobs/*.json")))
    return [path for path in paths if path.is_file()]


def load_job_states() -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for path in job_state_paths():
        payload = load_json_file(path)
        if not isinstance(payload, dict):
            continue
        job_id = payload.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            continue
        payload = dict(payload)
        payload["__path"] = str(path)
        current = states.get(job_id)
        if current is None or str(payload.get("launched_at", "")) >= str(current.get("launched_at", "")):
            states[job_id] = payload
    return states


def load_last_job_state() -> dict[str, Any] | None:
    data = load_json_file(LAST_JOB_PATH)
    if not isinstance(data, dict):
        return None
    data = dict(data)
    data["__path"] = str(LAST_JOB_PATH)
    return data


def state_mode(state: dict[str, Any]) -> str | None:
    mode = state.get("mode")
    if isinstance(mode, str) and mode:
        return mode
    labels = state.get("labels")
    if isinstance(labels, dict):
        value = labels.get("mode")
        if isinstance(value, str) and value:
            return value
    return None


def base_runtime_dir_for_state(state: dict[str, Any]) -> Path:
    raw_path = state.get("__path")
    if isinstance(raw_path, str) and raw_path:
        path = Path(raw_path)
        if path.name == "hf-job-last.json":
            return ROOT / ".runtime"
        if path.parent.name == "hf-jobs":
            return path.parent.parent
    return ROOT / ".runtime"


def iter_log_candidates(job_id: str, state: dict[str, Any] | None) -> list[Path]:
    candidates: list[Path] = []
    if state is not None:
        for key in ("cached_log_path", "output_log_path", "log_path"):
            value = state.get(key)
            if isinstance(value, str) and value:
                candidates.append(Path(value))
        candidates.append(base_runtime_dir_for_state(state) / "hf-logs" / f"{job_id}.log")
    candidates.append(ROOT / ".runtime" / "hf-logs" / f"{job_id}.log")
    candidates.extend(sorted((ROOT / ".runtime" / "worktrees").glob(f"*/.runtime/hf-logs/{job_id}.log")))

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path if path.is_absolute() else ROOT / path
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def persist_state_metadata(
    state: dict[str, Any] | None,
    *,
    log_path: Path | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    if state is None:
        return
    updated = dict(state)
    if log_path is not None:
        updated["cached_log_path"] = str(log_path)
    if metrics is not None:
        updated["metrics"] = metrics

    raw_path = updated.pop("__path", None)
    if isinstance(raw_path, str) and raw_path:
        write_json_file(Path(raw_path), updated)

    last_state = load_json_file(LAST_JOB_PATH)
    if (
        isinstance(last_state, dict)
        and last_state.get("job_id") == updated.get("job_id")
    ):
        merged = dict(last_state)
        if log_path is not None:
            merged["cached_log_path"] = str(log_path)
        if metrics is not None:
            merged["metrics"] = metrics
        write_json_file(LAST_JOB_PATH, merged)


def has_local_metrics_or_logs(job_id: str, state: dict[str, Any]) -> bool:
    metrics = state.get("metrics")
    if isinstance(metrics, dict) and "val_bpb" in metrics:
        return True
    return any(path.exists() for path in iter_log_candidates(job_id, state))


def select_job_state(explicit_job_id: str | None) -> tuple[str, dict[str, Any] | None]:
    all_states = load_job_states()
    last_state = load_last_job_state()

    if explicit_job_id:
        state = all_states.get(explicit_job_id)
        if state is None and last_state and last_state.get("job_id") == explicit_job_id:
            state = last_state
        return explicit_job_id, state

    if last_state is not None:
        job_id = last_state.get("job_id")
        if isinstance(job_id, str) and job_id and state_mode(last_state) == "experiment":
            if has_local_metrics_or_logs(job_id, last_state):
                return job_id, last_state

    experiment_states: list[tuple[str, dict[str, Any]]] = []
    for job_id, state in all_states.items():
        if state_mode(state) == "experiment":
            experiment_states.append((job_id, state))
    experiment_states.sort(key=lambda item: str(item[1].get("launched_at", "")), reverse=True)

    for job_id, state in experiment_states:
        if has_local_metrics_or_logs(job_id, state):
            return job_id, state

    if last_state is not None:
        job_id = last_state.get("job_id")
        if isinstance(job_id, str) and job_id and state_mode(last_state) == "experiment":
            return job_id, last_state

    if experiment_states:
        return experiment_states[0]

    raise SystemExit(
        "could not find a managed experiment job; launch and log an experiment first, or pass --job-id/--log explicitly"
    )


def cache_path_for_job(job_id: str, state: dict[str, Any] | None) -> Path:
    runtime_dir = base_runtime_dir_for_state(state or {})
    path = runtime_dir / "hf-logs" / f"{job_id}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fetch_job_log(job_id: str, namespace: str | None) -> str:
    argv = [resolve_hf_cli(), "jobs", "logs"]
    if namespace:
        argv.extend(["--namespace", namespace])
    argv.append(job_id)
    result = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "HF_HUB_DISABLE_EXPERIMENTAL_WARNING": "1"},
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        detail = output.strip() or "command failed"
        raise SystemExit(f"unable to fetch logs for job {job_id}: {detail}")
    return output


def resolve_metrics(
    *,
    explicit_log: Path | None,
    explicit_job_id: str | None,
    dry_run: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    if explicit_log is not None:
        text = explicit_log.read_text(encoding="utf-8")
        metrics = parse_metrics_text(text)
        return metrics, None, {
            "source": "explicit_log",
            "log_path": str(explicit_log),
            "job_id": explicit_job_id or "",
        }

    job_id, state = select_job_state(explicit_job_id)

    if state is not None:
        cached_metrics = state.get("metrics")
        if isinstance(cached_metrics, dict) and "val_bpb" in cached_metrics:
            return cached_metrics, state, {
                "source": "cached_metrics",
                "job_id": job_id,
                "log_path": state.get("cached_log_path", ""),
            }

    for path in iter_log_candidates(job_id, state):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        metrics = parse_metrics_text(text)
        persist_state_metadata(state, log_path=path, metrics=metrics or None)
        return metrics, state, {
            "source": "cached_log",
            "job_id": job_id,
            "log_path": str(path),
        }

    if dry_run:
        raise SystemExit(
            "no cached local metrics were found for the selected job; stream logs first or pass --log explicitly"
        )

    namespace = None
    if state is not None:
        value = state.get("namespace")
        if isinstance(value, str) and value:
            namespace = value
    if namespace is None:
        env_namespace = os.environ.get("AUTOLAB_HF_NAMESPACE")
        if env_namespace:
            namespace = env_namespace

    text = fetch_job_log(job_id, namespace)
    metrics = parse_metrics_text(text)
    cache_path = cache_path_for_job(job_id, state)
    cache_path.write_text(text, encoding="utf-8")
    persist_state_metadata(state, log_path=cache_path, metrics=metrics or None)
    return metrics, state, {
        "source": "remote_log_fetch",
        "job_id": job_id,
        "log_path": str(cache_path),
    }


def env_context() -> dict[str, str]:
    context: dict[str, str] = {}
    for env_name, key in (
        ("AUTOLAB_CAMPAIGN", "campaign"),
        ("AUTOLAB_EXPERIMENT_ID", "experiment_id"),
        ("AUTOLAB_WORKER_ID", "worker_id"),
        ("AUTOLAB_HYPOTHESIS", "hypothesis"),
    ):
        value = os.environ.get(env_name)
        if isinstance(value, str):
            value = value.strip()
        if value:
            context[key] = value
    return context


def resolved_context(state: dict[str, Any] | None) -> dict[str, str]:
    context = env_context()
    if state is None:
        return context
    for key in ("campaign", "experiment_id", "worker_id", "hypothesis"):
        value = state.get(key)
        if key not in context and isinstance(value, str) and value:
            context[key] = value
    return context


def build_run_id(existing_rows: list[dict[str, str]], job_id: str | None, candidate_hash: str) -> str:
    if job_id:
        base = f"job-{job_id}"
    else:
        base = f"run-{candidate_hash[:12]}"
    existing_ids = {row.get("run_id", "") for row in existing_rows}
    if base not in existing_ids:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base}-{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record the current train.py result locally and promote it if it beats the local master."
    )
    parser.add_argument("--comment", required=True, help="result comment or one-sentence hypothesis summary")
    parser.add_argument("--priority", type=int, default=0, help="accepted for CLI compatibility; ignored locally")
    parser.add_argument("--parent-hash", help="override parent master hash")
    parser.add_argument("--job-id", help="use this managed HF Job instead of auto-selecting the last experiment job")
    parser.add_argument("--log", type=Path, help="parse metrics from this local log instead of a managed HF Job")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the local ledger row and promotion preview without mutating files",
    )
    args = parser.parse_args()

    existing_rows = ensure_results_ledger()
    current_master = current_master_snapshot(existing_rows)

    train_source = normalize_source(TRAIN_PATH.read_text(encoding="utf-8"))
    train_orig_source = normalize_source(TRAIN_ORIG_PATH.read_text(encoding="utf-8"))
    if train_source == train_orig_source:
        raise SystemExit("train.py matches train_orig.py; no experiment change is present")

    metrics, state, metrics_info = resolve_metrics(
        explicit_log=args.log,
        explicit_job_id=args.job_id,
        dry_run=args.dry_run,
    )
    context = resolved_context(state)

    parent_hash = args.parent_hash or stringify_field(current_master.get("hash"))
    candidate_hash = source_hash(train_source)
    master_val_bpb = parse_float(current_master.get("val_bpb"))
    candidate_val_bpb = parse_float(metrics.get("val_bpb"))
    promoted = (
        candidate_val_bpb is not None
        and master_val_bpb is not None
        and candidate_val_bpb < master_val_bpb
    )
    status = "completed" if candidate_val_bpb is not None else "missing_metric"

    job_id = stringify_field(metrics_info.get("job_id"))
    row = {
        "run_id": build_run_id(existing_rows, job_id or None, candidate_hash),
        "created_at": now_utc_iso(),
        "status": status,
        "job_id": job_id,
        "campaign": context.get("campaign", ""),
        "experiment_id": context.get("experiment_id", ""),
        "worker_id": context.get("worker_id", ""),
        "hypothesis": context.get("hypothesis", ""),
        "parent_hash": parent_hash,
        "candidate_hash": candidate_hash,
        "val_bpb": metrics.get("val_bpb", ""),
        "training_seconds": metrics.get("training_seconds", ""),
        "total_seconds": metrics.get("total_seconds", ""),
        "peak_vram_mb": metrics.get("peak_vram_mb", ""),
        "mfu_percent": metrics.get("mfu_percent", ""),
        "promoted": promoted,
        "comment": args.comment,
    }

    preview = {
        "row": {key: stringify_field(value) for key, value in row.items()},
        "metrics_source": metrics_info,
        "metrics": metrics,
        "current_master": {
            "hash": stringify_field(current_master.get("hash")),
            "val_bpb": stringify_field(current_master.get("val_bpb")),
        },
        "promotion": {
            "promoted": promoted,
            "reason": (
                f"{candidate_val_bpb} < {master_val_bpb}"
                if promoted
                else (
                    "missing val_bpb in the parsed metrics"
                    if candidate_val_bpb is None
                    else f"{candidate_val_bpb} >= {master_val_bpb}"
                )
            ),
        },
        "results_path": str(RESULTS_PATH),
        "priority": args.priority,
    }
    if args.priority:
        preview["priority_note"] = "priority is accepted for CLI compatibility but has no effect in the repo-local workflow"

    if args.dry_run:
        print(json.dumps(preview, indent=2, sort_keys=True))
        return 0

    rebuild_live_state(existing_rows)
    if truthy(row["promoted"]):
        write_current_master_source(train_source)

    appended = append_result_row(row)
    if truthy(appended["promoted"]):
        updated_rows = [*existing_rows, appended]
        rebuild_live_state(updated_rows)

    print(
        json.dumps(
            {
                **preview,
                "row": appended,
                "recorded": True,
                "promoted_files_updated": truthy(appended["promoted"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
