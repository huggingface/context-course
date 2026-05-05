import csv
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "gastown_wave2_running_jobs.csv"
TRACKIO_DB_PATH = Path.home() / ".cache" / "huggingface" / "trackio" / "autolab.db"


def parse_optional_float(raw: str | None) -> float | None:
    if raw in (None, ""):
        return None
    return float(raw)


def load_trackio_metrics(job_ids: set[str]) -> dict[str, dict[str, float | None]]:
    if not TRACKIO_DB_PATH.exists():
        return {}

    metrics: dict[str, dict[str, float | None]] = {}
    with sqlite3.connect(TRACKIO_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        for job_id in sorted(job_ids):
            cursor.execute(
                "SELECT metrics FROM metrics WHERE run_name = ? ORDER BY timestamp",
                (job_id,),
            )
            val_bpb = None
            for row in cursor.fetchall():
                payload = json.loads(row["metrics"])
                if "val_bpb" in payload:
                    val_bpb = float(payload["val_bpb"])

            cursor.execute(
                "SELECT config FROM configs WHERE run_name = ?",
                (job_id,),
            )
            config_row = cursor.fetchone()
            master_val_bpb = None
            if config_row:
                config = json.loads(config_row["config"])
                raw_master = config.get("master_val_bpb")
                if raw_master is not None:
                    master_val_bpb = float(raw_master)

            metrics[job_id] = {
                "val_bpb": val_bpb,
                "master_val_bpb": master_val_bpb,
            }
    return metrics


rows = []
with open(CSV_PATH) as f:
    for r in csv.DictReader(f):
        rows.append(r)

trackio_metrics = load_trackio_metrics({r["job_id"] for r in rows})

jobs = defaultdict(dict)
for r in rows:
    ts = datetime.fromisoformat(r["timestamp_utc"])
    key = r["bead_id"]
    job_metrics = trackio_metrics.get(r["job_id"], {})
    jobs[key]["job_id"] = r["job_id"]
    jobs[key]["val_bpb"] = parse_optional_float(r.get("val_bpb"))
    if jobs[key]["val_bpb"] is None:
        jobs[key]["val_bpb"] = job_metrics.get("val_bpb")
    jobs[key]["master_val_bpb"] = parse_optional_float(r.get("master_val_bpb"))
    if jobs[key]["master_val_bpb"] is None:
        jobs[key]["master_val_bpb"] = job_metrics.get("master_val_bpb")
    if r["event_type"] == "start":
        jobs[key]["start"] = ts
        jobs[key]["polecat"] = r["polecat"]
        jobs[key]["convoy"] = r["convoy_theme"]
        jobs[key]["bead"] = r["bead_id"]
    else:
        jobs[key]["end"] = ts

convoy_colors = {
    "scheduler": "#4C72B0",
    "optimizer": "#DD8452",
    "architecture": "#55A868",
}

sorted_jobs = sorted(jobs.values(), key=lambda j: j.get("val_bpb") or float("inf"))

master_val_bpb = next(
    (
        job["master_val_bpb"]
        for job in sorted_jobs
        if job.get("master_val_bpb") is not None
    ),
    None,
)
best_job = min(
    (job for job in sorted_jobs if job.get("val_bpb") is not None),
    key=lambda job: job["val_bpb"],
    default=None,
)

fig, ax = plt.subplots(figsize=(13.8, 5.6))
fig.subplots_adjust(right=0.84, top=0.82)
fig.suptitle("Multi Agent Autoresearch Lab", fontsize=15, fontweight="bold", y=0.97)

subtitle = "Trackio val_bpb shown at each experiment end"
if master_val_bpb is not None:
    subtitle += f" | master {master_val_bpb:.6f}"
if best_job is not None:
    subtitle += f" | best {best_job['bead']} {best_job['val_bpb']:.6f}"
ax.set_title(subtitle, fontsize=10.5, pad=12, loc="left")

labels = []
for i, job in enumerate(sorted_jobs):
    start = job["start"]
    end = job["end"]
    duration = end - start
    color = convoy_colors.get(job["convoy"], "#999999")
    ax.barh(
        i,
        duration,
        left=start,
        height=0.6,
        color=color,
        edgecolor="white",
        linewidth=0.8,
        alpha=0.92,
    )
    mid = start + duration / 2
    ax.text(
        mid,
        i,
        f'{job["polecat"]}',
        ha="center",
        va="center",
        fontsize=8.5,
        fontweight="600",
        color="white",
    )
    if job.get("val_bpb") is not None:
        ax.text(
            end + timedelta(seconds=18),
            i,
            f'{job["val_bpb"]:.6f} bpb',
            ha="left",
            va="center",
            fontsize=8.5,
            color="#1f2937",
            bbox={
                "boxstyle": "round,pad=0.18",
                "facecolor": "white",
                "alpha": 0.78,
                "edgecolor": "none",
            },
        )
    labels.append(f'{job["bead"]}')

ax.set_yticks(range(len(sorted_jobs)))
ax.set_yticklabels(labels, fontsize=9, fontfamily="monospace")
ax.invert_yaxis()

left_pad = min(job["start"] for job in sorted_jobs) - timedelta(seconds=25)
right_pad = max(job["end"] for job in sorted_jobs) + timedelta(minutes=2, seconds=10)
ax.set_xlim(left_pad, right_pad)

ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=timezone.utc))
ax.xaxis.set_minor_locator(mdates.MinuteLocator(interval=2))
ax.tick_params(axis="x", labelsize=9)
ax.set_xlabel("Time (UTC)", fontsize=10)

from matplotlib.patches import Patch

legend_handles = [Patch(facecolor=c, label=l) for l, c in convoy_colors.items()]
ax.legend(
    handles=legend_handles,
    loc="upper left",
    bbox_to_anchor=(1.01, 1.0),
    borderaxespad=0,
    fontsize=9,
    title="Convoy",
    title_fontsize=9,
)

ax.grid(axis="x", linewidth=0.4, alpha=0.5)
ax.set_axisbelow(True)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
plt.savefig(ROOT / "gastown_wave2_running_jobs.png", dpi=180, bbox_inches="tight")
print("Saved images/gastown_wave2_running_jobs.png")
