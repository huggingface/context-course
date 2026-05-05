#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "trackio>=0.20.0",
# ]
# ///
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
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
TERMINAL_STAGES = {"COMPLETED", "CANCELED", "CANCELLED", "FAILED", "TIMEOUT", "ERROR"}
DEFAULT_PROJECT = os.environ.get("AUTOLAB_TRACKIO_PROJECT", "autolab")
DEFAULT_NAMESPACE = os.environ.get("AUTOLAB_HF_NAMESPACE")
STEP_RE = re.compile(
    r"step\s+(?P<step>\d+)\s+\((?P<pct_done>[0-9.]+)%\)\s+\|\s+"
    r"loss:\s+(?P<loss>[0-9.]+)\s+\|\s+"
    r"lrm:\s+(?P<lrm>[0-9.]+)\s+\|\s+"
    r"dt:\s+(?P<dt_ms>[0-9.]+)ms\s+\|\s+"
    r"tok/sec:\s+(?P<tok_per_sec>[0-9.,]+)\s+\|\s+"
    r"mfu:\s+(?P<mfu_percent>[0-9.]+)%\s+\|\s+"
    r"epoch:\s+(?P<epoch>\d+)\s+\|\s+"
    r"remaining:\s+(?P<remaining_seconds>[0-9.]+)s"
)

GLOBAL_RUNTIME_DIR = ROOT / ".runtime"
STATE_PATH = GLOBAL_RUNTIME_DIR / "trackio-reporter-state.json"
SNAPSHOT_PATH = GLOBAL_RUNTIME_DIR / "trackio-latest.json"
MARKDOWN_PATH = GLOBAL_RUNTIME_DIR / "trackio-report.md"
JOBS_CACHE_PATH = GLOBAL_RUNTIME_DIR / "hf-jobs-cache.json"


def resolve_hf_cli() -> str:
    explicit = os.environ.get("AUTOLAB_HF_CLI")
    if explicit:
        return explicit
    preferred = Path.home() / ".local" / "bin" / "hf"
    if preferred.exists():
        return str(preferred)
    fallback = shutil_which("hf")
    if fallback:
        return fallback
    raise SystemExit("could not find `hf`; set AUTOLAB_HF_CLI or install the Hugging Face CLI")


def resolve_trackio_cli() -> list[str]:
    explicit = os.environ.get("AUTOLAB_TRACKIO_BIN")
    if explicit:
        return [explicit]
    preferred = Path.home() / ".venvs" / "trackio" / "bin" / "trackio"
    if preferred.exists():
        return [str(preferred)]
    return [sys.executable, "-m", "trackio.cli"]


def shutil_which(name: str) -> str | None:
    path_value = os.environ.get("PATH", "")
    for entry in path_value.split(os.pathsep):
        if not entry:
            continue
        candidate = Path(entry) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def run_command(argv: list[str], capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("HF_HUB_DISABLE_EXPERIMENTAL_WARNING", "1")
    return subprocess.run(argv, cwd=ROOT, text=True, capture_output=capture_output, check=False, env=env)


def load_json_stdout(argv: list[str]) -> Any:
    result = run_command(argv, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "command failed"
        raise SystemExit(f"{' '.join(argv)}: {stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"failed to parse JSON from {' '.join(argv)}: {exc}") from exc


def coerce_number(raw: str) -> int | float | str:
    text = raw.strip().replace(",", "")
    for caster in (int, float):
        try:
            return caster(text)
        except ValueError:
            continue
    return raw.strip()


def parse_summary_metrics(text: str) -> dict[str, int | float | str]:
    metrics: dict[str, int | float | str] = {}
    for line in text.replace("\r", "\n").splitlines():
        match = re.match(r"^([A-Za-z_]+):\s+(.+)$", line.strip())
        if not match:
            continue
        key, raw = match.groups()
        if key not in SUMMARY_KEYS:
            continue
        metrics[key] = coerce_number(raw)
    return metrics


def parse_step_metrics(text: str) -> list[dict[str, int | float]]:
    rows: dict[int, dict[str, int | float]] = {}
    for line in text.replace("\r", "\n").splitlines():
        match = STEP_RE.search(line.strip())
        if not match:
            continue
        row = {key: coerce_number(value) for key, value in match.groupdict().items()}
        step = int(row.pop("step"))
        row["step"] = step
        rows[step] = row
    return [rows[key] for key in sorted(rows)]


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"jobs": {}, "reporter": {"step": 0}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"jobs": {}, "reporter": {"step": 0}}
    if not isinstance(data, dict):
        return {"jobs": {}, "reporter": {"step": 0}}
    data.setdefault("jobs", {})
    data.setdefault("reporter", {"step": 0})
    return data


def save_state(state: dict[str, Any]) -> None:
    GLOBAL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_master_snapshot() -> dict[str, Any]:
    path = ROOT / "research" / "live" / "master.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def load_jobs_cache() -> list[dict[str, Any]]:
    if not JOBS_CACHE_PATH.exists():
        return []
    try:
        payload = json.loads(JOBS_CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def save_jobs_cache(jobs: list[dict[str, Any]]) -> None:
    GLOBAL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_CACHE_PATH.write_text(json.dumps(jobs, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_registry_entries() -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    candidates: list[Path] = []
    candidates.extend(sorted((ROOT / ".runtime" / "hf-jobs").glob("*.json")))
    candidates.extend(sorted((ROOT / ".runtime" / "worktrees").glob("*/.runtime/hf-jobs/*.json")))
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        job_id = payload.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            continue
        payload["registry_path"] = str(path)
        current = entries.get(job_id)
        if current is None or str(payload.get("launched_at", "")) >= str(current.get("launched_at", "")):
            entries[job_id] = payload
    return entries


def row_mode(row: dict[str, Any]) -> str | None:
    mode = row.get("mode")
    if isinstance(mode, str) and mode:
        return mode
    labels = row.get("labels")
    if isinstance(labels, dict):
        mode = labels.get("mode")
        if isinstance(mode, str) and mode:
            return mode
    return None


def build_anomalies(rows: list[dict[str, Any]]) -> list[str]:
    anomalies: list[str] = []
    active_rows = [row for row in rows if row["stage"] not in TERMINAL_STAGES]

    active_by_experiment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    active_by_hypothesis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in active_rows:
        experiment_id = row.get("experiment_id")
        if isinstance(experiment_id, str) and experiment_id:
            active_by_experiment[experiment_id].append(row)
        hypothesis = row.get("hypothesis")
        if isinstance(hypothesis, str) and hypothesis:
            active_by_hypothesis[hypothesis].append(row)

        mode = row_mode(row)
        if mode == "prepare" and isinstance(experiment_id, str) and experiment_id:
            anomalies.append(f"prepare job launched with experiment label `{experiment_id}`: `{row['job_id']}`")

    for experiment_id, experiment_rows in active_by_experiment.items():
        active_experiments = [row for row in experiment_rows if row_mode(row) == "experiment"]
        if len(active_experiments) > 1:
            job_ids = ", ".join(str(row["job_id"]) for row in active_experiments)
            anomalies.append(f"duplicate active experiments for experiment `{experiment_id}`: {job_ids}")

    for hypothesis, hypothesis_rows in active_by_hypothesis.items():
        active_experiments = [row for row in hypothesis_rows if row_mode(row) == "experiment"]
        unique_experiments = {
            str(row.get("experiment_id") or row["job_id"]) for row in active_experiments if row.get("experiment_id") or row.get("job_id")
        }
        if len(active_experiments) > 1 and len(unique_experiments) > 1:
            job_ids = ", ".join(str(row["job_id"]) for row in active_experiments)
            anomalies.append(f"duplicate active hypothesis `{hypothesis}` across experiments: {job_ids}")

    seen: set[str] = set()
    unique: list[str] = []
    for anomaly in anomalies:
        if anomaly in seen:
            continue
        seen.add(anomaly)
        unique.append(anomaly)
    return unique


def is_autolab_job(job: dict[str, Any], registry: dict[str, dict[str, Any]]) -> bool:
    job_id = job.get("id")
    if isinstance(job_id, str) and job_id in registry:
        return True
    labels = job.get("labels") or {}
    if isinstance(labels, dict) and "autolab" in labels:
        return True
    command = " ".join(job.get("command") or [])
    if "autolab-hf-job.py" in command or "autolab-hf-smoke.py" in command:
        return True
    environment = job.get("environment") or {}
    if environment.get("AUTOLAB_HOME") == "/autolab-home":
        return True
    return False


def job_stage(job: dict[str, Any]) -> str:
    status = job.get("status") or {}
    if isinstance(status, dict):
        stage = status.get("stage")
        if isinstance(stage, str) and stage:
            return stage.upper()
    return "UNKNOWN"


def job_sort_key(job: dict[str, Any]) -> str:
    created_at = job.get("created_at")
    return created_at if isinstance(created_at, str) else ""


def fetch_jobs(max_jobs: int, namespace: str | None, registry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    argv = [resolve_hf_cli(), "jobs", "ps", "-a", "--format", "json"]
    if namespace:
        argv.extend(["--namespace", namespace])
    try:
        payload = load_json_stdout(argv)
        if not isinstance(payload, list):
            raise SystemExit("unexpected `hf jobs ps` payload")
        save_jobs_cache([job for job in payload if isinstance(job, dict)])
    except SystemExit:
        payload = load_jobs_cache()
        if not payload:
            raise
    jobs = [job for job in payload if isinstance(job, dict) and is_autolab_job(job, registry)]
    jobs.sort(key=job_sort_key, reverse=True)
    return jobs[:max_jobs]


def fetch_job_logs(job_id: str, tail: int, namespace: str | None) -> str:
    argv = [resolve_hf_cli(), "jobs", "logs", "--tail", str(tail)]
    if namespace:
        argv.extend(["--namespace", namespace])
    argv.append(job_id)
    result = run_command(argv, capture_output=True)
    combined = (result.stdout or "") + (result.stderr or "")
    return combined


def delta_vs_master(val_bpb: object, master_val_bpb: object) -> float | None:
    if isinstance(val_bpb, (int, float)) and isinstance(master_val_bpb, (int, float)):
        return float(val_bpb) - float(master_val_bpb)
    return None


def build_job_row(
    job: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    master: dict[str, Any],
    tail: int,
    namespace: str | None,
) -> dict[str, Any]:
    job_id = str(job.get("id"))
    registry_entry = registry.get(job_id, {})
    labels = job.get("labels")
    if not isinstance(labels, dict):
        labels = {}

    log_text = fetch_job_logs(job_id, tail=tail, namespace=namespace)
    step_metrics = parse_step_metrics(log_text)
    summary = parse_summary_metrics(log_text)

    def label_or_registry(label_key: str, registry_key: str | None = None) -> str | None:
        label_value = labels.get(label_key)
        if isinstance(label_value, str) and label_value:
            return label_value
        registry_value = registry_entry.get(registry_key or label_key)
        if isinstance(registry_value, str) and registry_value:
            return registry_value
        return None

    campaign = label_or_registry("campaign")
    experiment_id = label_or_registry("experiment", "experiment_id")
    worker_id = label_or_registry("worker", "worker_id")
    hypothesis = label_or_registry("hypothesis")
    master_hash = label_or_registry("master", "master_hash")
    if not isinstance(master_hash, str) or not master_hash:
        master_hash = master.get("hash")

    row = {
        "job_id": job_id,
        "stage": job_stage(job),
        "created_at": job.get("created_at"),
        "flavor": job.get("flavor"),
        "mode": label_or_registry("mode"),
        "labels": labels,
        "campaign": campaign,
        "experiment_id": experiment_id,
        "worker_id": worker_id,
        "hypothesis": hypothesis,
        "branch": registry_entry.get("branch"),
        "git_commit": registry_entry.get("git_commit"),
        "master_hash": master_hash,
        "master_val_bpb": master.get("val_bpb"),
        "summary": summary,
        "steps": step_metrics,
        "max_step": step_metrics[-1]["step"] if step_metrics else None,
    }
    row["delta_vs_master"] = delta_vs_master(summary.get("val_bpb"), row["master_val_bpb"])
    return row


def build_run_config(row: dict[str, Any]) -> dict[str, Any]:
    config = {
        "job_id": row["job_id"],
        "stage": row["stage"],
        "mode": row["mode"],
        "flavor": row["flavor"],
        "campaign": row["campaign"],
        "experiment_id": row["experiment_id"],
        "worker_id": row["worker_id"],
        "hypothesis": row["hypothesis"],
        "branch": row["branch"],
        "git_commit": row["git_commit"],
        "master_hash": row["master_hash"],
        "master_val_bpb": row["master_val_bpb"],
        "created_at": row["created_at"],
    }
    return {key: value for key, value in config.items() if value not in (None, "", {})}


def sync_job_to_trackio(row: dict[str, Any], state: dict[str, Any], project: str) -> bool:
    import trackio

    job_id = row["job_id"]
    job_state = state.setdefault("jobs", {}).setdefault(job_id, {})
    last_training_step = int(job_state.get("last_training_step", -1))
    summary_payload = row["summary"] if isinstance(row["summary"], dict) else {}
    summary_hash = hashlib.sha1(json.dumps(summary_payload, sort_keys=True).encode("utf-8")).hexdigest()
    stage = row["stage"]
    new_steps = [step for step in row["steps"] if int(step["step"]) > last_training_step]
    should_log_summary = bool(summary_payload) and summary_hash != job_state.get("summary_hash")
    stage_changed = stage != job_state.get("stage")

    if not new_steps and not should_log_summary and not stage_changed:
        return False

    run = trackio.init(
        project=project,
        name=job_id,
        group=row.get("experiment_id") or "autolab-jobs",
        config=build_run_config(row),
        resume="allow",
        embed=False,
        auto_log_gpu=False,
    )

    for step in new_steps:
        track_metrics = {
            "train_loss": step["loss"],
            "lr_multiplier": step["lrm"],
            "step_time_ms": step["dt_ms"],
            "tokens_per_second": step["tok_per_sec"],
            "mfu_percent_live": step["mfu_percent"],
            "epoch": step["epoch"],
            "remaining_seconds": step["remaining_seconds"],
            "pct_done": step["pct_done"],
        }
        run.log(track_metrics, step=int(step["step"]))

    summary_step = int(summary_payload.get("num_steps", row.get("max_step") or max(last_training_step, 0)))
    if should_log_summary:
        final_metrics = dict(summary_payload)
        if row.get("delta_vs_master") is not None:
            final_metrics["delta_vs_master"] = row["delta_vs_master"]
        run.log(final_metrics, step=summary_step)

    if stage_changed:
        run.log({"job_stage": stage, "is_terminal": 1 if stage in TERMINAL_STAGES else 0}, step=summary_step)
        if stage in TERMINAL_STAGES and stage != "COMPLETED":
            title = f"{job_id} ended in {stage}"
            text = row.get("experiment_id") or row.get("hypothesis") or "autolab job ended unsuccessfully"
            run.alert(title=title, text=text, step=summary_step)

    run.finish()

    if new_steps:
        job_state["last_training_step"] = int(new_steps[-1]["step"])
    elif row.get("max_step") is not None:
        job_state["last_training_step"] = int(row["max_step"])
    if should_log_summary:
        job_state["summary_hash"] = summary_hash
    job_state["stage"] = stage
    job_state["updated_at"] = datetime.now().isoformat()
    return True


def build_markdown_report(rows: list[dict[str, Any]], master: dict[str, Any], anomalies: list[str]) -> str:
    lines: list[str] = []
    master_hash = master.get("hash")
    master_val = master.get("val_bpb")
    if master_hash or master_val is not None:
        lines.append("# Autolab HF Jobs")
        master_parts = []
        if isinstance(master_hash, str) and master_hash:
            master_parts.append(f"master `{master_hash[:12]}`")
        if isinstance(master_val, (int, float)):
            master_parts.append(f"master `val_bpb={master_val:.6f}`")
        lines.append("")
        lines.append("- " + ", ".join(master_parts))
        lines.append("")

    running = [row for row in rows if row["stage"] not in TERMINAL_STAGES]
    running_experiments = [row for row in running if row_mode(row) == "experiment"]
    running_other = [row for row in running if row_mode(row) != "experiment"]
    completed = [row for row in rows if row["stage"] == "COMPLETED" and isinstance(row["summary"].get("val_bpb"), (int, float))]
    completed.sort(key=lambda row: float(row["summary"]["val_bpb"]))
    failed = [row for row in rows if row["stage"] in TERMINAL_STAGES and row["stage"] != "COMPLETED"]

    lines.append("## Running Experiments")
    if running_experiments:
        for row in running_experiments:
            label = row.get("experiment_id") or row["job_id"]
            hypothesis = row.get("hypothesis") or "unlabeled"
            campaign = row.get("campaign")
            campaign_text = f" ({campaign})" if isinstance(campaign, str) and campaign else ""
            lines.append(f"- `{label}` `{row['job_id']}` `{row['stage']}` on `{row.get('flavor')}`: {hypothesis}{campaign_text}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Running Non-Experiment Jobs")
    if running_other:
        for row in running_other:
            label = row.get("experiment_id") or row["job_id"]
            mode = row_mode(row) or "unknown"
            lines.append(f"- `{label}` `{row['job_id']}` `{mode}` `{row['stage']}` on `{row.get('flavor')}`")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Leaderboard")
    if completed:
        for row in completed[:10]:
            summary = row["summary"]
            delta = row.get("delta_vs_master")
            delta_text = f" ({delta:+.6f} vs master)" if isinstance(delta, float) else ""
            label = row.get("experiment_id") or row["job_id"]
            hypothesis = row.get("hypothesis") or "unlabeled"
            lines.append(f"- `{label}` `{summary['val_bpb']:.6f}`{delta_text}: {hypothesis}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Anomalies")
    if anomalies:
        for anomaly in anomalies[:15]:
            lines.append(f"- {anomaly}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Failed")
    if failed:
        for row in failed[:10]:
            label = row.get("experiment_id") or row["job_id"]
            hypothesis = row.get("hypothesis") or "unlabeled"
            lines.append(f"- `{label}` `{row['job_id']}` ended in `{row['stage']}`: {hypothesis}")
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def sync_project_report(
    rows: list[dict[str, Any]],
    master: dict[str, Any],
    anomalies: list[str],
    state: dict[str, Any],
    project: str,
) -> bool:
    import trackio

    report = build_markdown_report(rows, master, anomalies)
    report_hash = hashlib.sha1(report.encode("utf-8")).hexdigest()
    reporter_state = state.setdefault("reporter", {"step": 0})
    if report_hash == reporter_state.get("report_hash"):
        return False

    completed = [row for row in rows if row["stage"] == "COMPLETED" and isinstance(row["summary"].get("val_bpb"), (int, float))]
    active_rows = [row for row in rows if row["stage"] not in TERMINAL_STAGES]
    active_experiments = [row for row in active_rows if row_mode(row) == "experiment"]
    active_other = [row for row in active_rows if row_mode(row) != "experiment"]
    best_val = min((float(row["summary"]["val_bpb"]) for row in completed), default=None)
    best_delta = None
    if best_val is not None and isinstance(master.get("val_bpb"), (int, float)):
        best_delta = best_val - float(master["val_bpb"])

    run = trackio.init(
        project=project,
        name="reporter",
        group="meta",
        config={"workspace": str(ROOT), "source": "hf_jobs"},
        resume="allow",
        embed=False,
        auto_log_gpu=False,
    )
    metrics: dict[str, Any] = {
        "active_jobs": len(active_rows),
        "active_experiment_jobs": len(active_experiments),
        "active_non_experiment_jobs": len(active_other),
        "completed_jobs": sum(1 for row in rows if row["stage"] == "COMPLETED"),
        "failed_jobs": sum(1 for row in rows if row["stage"] in TERMINAL_STAGES and row["stage"] != "COMPLETED"),
        "anomaly_count": len(anomalies),
        "report": trackio.Markdown(report),
    }
    if best_val is not None:
        metrics["best_val_bpb"] = best_val
    if best_delta is not None:
        metrics["best_delta_vs_master"] = best_delta

    step = int(reporter_state.get("step", 0))
    run.log(metrics, step=step)
    anomaly_hash = hashlib.sha1(json.dumps(anomalies, sort_keys=True).encode("utf-8")).hexdigest()
    if anomalies and anomaly_hash != reporter_state.get("anomaly_hash"):
        run.alert(
            title="autolab reporting anomalies detected",
            text="; ".join(anomalies[:3]),
            step=step,
        )
    run.finish()

    reporter_state["step"] = step + 1
    reporter_state["report_hash"] = report_hash
    reporter_state["anomaly_hash"] = anomaly_hash
    GLOBAL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    MARKDOWN_PATH.write_text(report, encoding="utf-8")
    SNAPSHOT_PATH.write_text(
        json.dumps({"master": master, "rows": rows, "anomalies": anomalies}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return True


def print_summary(rows: list[dict[str, Any]], master: dict[str, Any], anomalies: list[str]) -> None:
    master_hash = master.get("hash")
    master_val = master.get("val_bpb")
    header = ["Trackio sync snapshot"]
    if isinstance(master_hash, str) and master_hash:
        header.append(f"master={master_hash[:12]}")
    if isinstance(master_val, (int, float)):
        header.append(f"val_bpb={master_val:.6f}")
    print(" | ".join(header))

    completed = [row for row in rows if row["stage"] == "COMPLETED" and isinstance(row["summary"].get("val_bpb"), (int, float))]
    completed.sort(key=lambda row: float(row["summary"]["val_bpb"]))
    if completed:
        best = completed[0]
        best_delta = best.get("delta_vs_master")
        delta_text = f" ({best_delta:+.6f} vs master)" if isinstance(best_delta, float) else ""
        print(f"best: {best['job_id']} {best['summary']['val_bpb']:.6f}{delta_text}")
    else:
        print("best: none")

    active = [row for row in rows if row["stage"] not in TERMINAL_STAGES]
    active_experiments = [row for row in active if row_mode(row) == "experiment"]
    active_other = [row for row in active if row_mode(row) != "experiment"]
    print(f"active_jobs: {len(active)} (experiments={len(active_experiments)}, other={len(active_other)})")
    for row in active[:10]:
        label = row.get("experiment_id") or row["job_id"]
        hypothesis = row.get("hypothesis") or row.get("campaign") or "unlabeled"
        mode = row_mode(row) or "unknown"
        print(f"  {label} {mode} {row['stage']} {row['job_id']} {hypothesis}")
    if anomalies:
        print(f"anomalies: {len(anomalies)}")
        for anomaly in anomalies[:5]:
            print(f"  {anomaly}")


def sync_once(args: argparse.Namespace) -> list[dict[str, Any]]:
    state = load_state()
    registry = load_registry_entries()
    master = load_master_snapshot()
    jobs = fetch_jobs(max_jobs=args.max_jobs, namespace=args.namespace, registry=registry)
    rows = [build_job_row(job, registry, master, tail=args.tail, namespace=args.namespace) for job in jobs]
    anomalies = build_anomalies(rows)

    touched = 0
    for row in rows:
        if sync_job_to_trackio(row, state, project=args.project):
            touched += 1
    if sync_project_report(rows, master, anomalies, state, project=args.project):
        touched += 1
    save_state(state)

    print_summary(rows, master, anomalies)
    print(f"synced: {touched} update(s)")
    return rows


def sync_loop(args: argparse.Namespace) -> int:
    while True:
        try:
            sync_once(args)
        except Exception as exc:
            if not args.watch:
                raise
            print(f"trackio sync error: {exc}", file=sys.stderr, flush=True)
        if not args.watch:
            return 0
        time.sleep(args.interval)


def summary_command(args: argparse.Namespace) -> int:
    registry = load_registry_entries()
    master = load_master_snapshot()
    jobs = fetch_jobs(max_jobs=args.max_jobs, namespace=args.namespace, registry=registry)
    rows = [build_job_row(job, registry, master, tail=args.tail, namespace=args.namespace) for job in jobs]
    anomalies = build_anomalies(rows)
    print(build_markdown_report(rows, master, anomalies), end="")
    return 0


def dashboard_command(args: argparse.Namespace) -> int:
    argv = resolve_trackio_cli() + ["show", "--project", args.project, "--host", args.host]
    if args.mcp_server:
        argv.append("--mcp-server")
    if args.no_footer:
        argv.append("--no-footer")
    result = run_command(argv, capture_output=False)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync Hugging Face Jobs metrics into local Trackio.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="sync recent autolab HF Jobs into Trackio")
    sync_parser.add_argument("--project", default=DEFAULT_PROJECT, help="Trackio project name")
    sync_parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="Hugging Face namespace that owns the jobs")
    sync_parser.add_argument("--tail", type=int, default=5000, help="tail this many log lines per job")
    sync_parser.add_argument("--max-jobs", type=int, default=25, help="inspect at most this many recent jobs")
    sync_parser.add_argument("--watch", action="store_true", help="keep syncing on an interval")
    sync_parser.add_argument("--interval", type=int, default=300, help="watch interval in seconds")

    summary_parser = subparsers.add_parser("summary", help="print the current autolab HF Jobs report")
    summary_parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="Hugging Face namespace that owns the jobs")
    summary_parser.add_argument("--tail", type=int, default=5000, help="tail this many log lines per job")
    summary_parser.add_argument("--max-jobs", type=int, default=25, help="inspect at most this many recent jobs")

    dashboard_parser = subparsers.add_parser("dashboard", help="run the local Trackio dashboard")
    dashboard_parser.add_argument("--project", default=DEFAULT_PROJECT, help="Trackio project name")
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="host to bind the dashboard to")
    dashboard_parser.add_argument("--mcp-server", action="store_true", help="enable Trackio's MCP server")
    dashboard_parser.add_argument("--no-footer", action="store_true", help="hide the Gradio footer")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "sync":
        return sync_loop(args)
    if args.command == "summary":
        return summary_command(args)
    if args.command == "dashboard":
        return dashboard_command(args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
