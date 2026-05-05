#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / "research"
LIVE_DIR = RESEARCH_DIR / "live"
REFERENCE_DIR = RESEARCH_DIR / "reference"
RESULTS_PATH = RESEARCH_DIR / "results.tsv"
TRAIN_PATH = ROOT / "train.py"
TRAIN_ORIG_PATH = ROOT / "train_orig.py"
MASTER_PATH = LIVE_DIR / "master.json"
MASTER_DETAIL_PATH = LIVE_DIR / "master_detail.json"
DAG_PATH = LIVE_DIR / "dag.json"
MASTER_SEED_PATH = REFERENCE_DIR / "master.seed.json"
MASTER_DETAIL_SEED_PATH = REFERENCE_DIR / "master_detail.seed.json"

RESULTS_COLUMNS = [
    "run_id",
    "created_at",
    "status",
    "job_id",
    "campaign",
    "experiment_id",
    "worker_id",
    "hypothesis",
    "parent_hash",
    "candidate_hash",
    "val_bpb",
    "training_seconds",
    "total_seconds",
    "peak_vram_mb",
    "mfu_percent",
    "promoted",
    "comment",
]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def normalize_source(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.rstrip("\n")
    return text + "\n"


def source_hash(text: str) -> str:
    return hashlib.sha1(normalize_source(text).encode("utf-8")).hexdigest()


def train_files_diverged() -> bool:
    if not TRAIN_PATH.exists() or not TRAIN_ORIG_PATH.exists():
        return False
    return TRAIN_PATH.read_text(encoding="utf-8") != TRAIN_ORIG_PATH.read_text(encoding="utf-8")


def stringify_field(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value)


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def parse_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def normalize_row(row: dict[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for column in RESULTS_COLUMNS:
        normalized[column] = stringify_field(row.get(column, ""))
    return normalized


def load_results_rows() -> list[dict[str, str]]:
    if not RESULTS_PATH.exists():
        return []
    with RESULTS_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != RESULTS_COLUMNS:
            raise RuntimeError(
                f"{RESULTS_PATH.relative_to(ROOT)} has unexpected columns; expected {RESULTS_COLUMNS}, got {reader.fieldnames}"
            )
        return [normalize_row(row) for row in reader]


def write_results_rows(rows: list[dict[str, object]]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=RESULTS_COLUMNS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(normalize_row(row))


def append_result_row(row: dict[str, object]) -> dict[str, str]:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_exists = RESULTS_PATH.exists() and RESULTS_PATH.stat().st_size > 0
    normalized = normalize_row(row)
    with RESULTS_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=RESULTS_COLUMNS,
            delimiter="\t",
            lineterminator="\n",
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(normalized)
    return normalized


def reference_master_metadata() -> dict[str, Any]:
    candidates = [MASTER_PATH, MASTER_SEED_PATH]
    for path in candidates:
        data = load_json(path)
        if isinstance(data, dict):
            return data
    return {}


def reference_master_detail() -> dict[str, Any]:
    candidates = [MASTER_DETAIL_PATH, MASTER_DETAIL_SEED_PATH]
    for path in candidates:
        data = load_json(path)
        if isinstance(data, dict):
            return data
    return {}


def seed_source() -> str:
    if TRAIN_ORIG_PATH.exists():
        return normalize_source(TRAIN_ORIG_PATH.read_text(encoding="utf-8"))
    detail = reference_master_detail()
    source = detail.get("source")
    if isinstance(source, str) and source:
        return normalize_source(source)
    raise RuntimeError("could not determine seed source; train_orig.py and master detail are both missing")


def seed_row() -> dict[str, object]:
    metadata = reference_master_metadata()
    source = seed_source()
    return {
        "run_id": "legacy_seed",
        "created_at": metadata.get("created_at") or now_utc_iso(),
        "status": "legacy_seed",
        "job_id": metadata.get("job_id", ""),
        "campaign": "legacy-baseline",
        "experiment_id": "legacy-seed",
        "worker_id": "seed",
        "hypothesis": "seed local master from current train_orig.py",
        "parent_hash": metadata.get("parent_hash", ""),
        "candidate_hash": source_hash(source),
        "val_bpb": metadata.get("val_bpb", ""),
        "training_seconds": "",
        "total_seconds": "",
        "peak_vram_mb": "",
        "mfu_percent": "",
        "promoted": True,
        "comment": metadata.get("comment")
        or metadata.get("message")
        or "Seeded local master from current train_orig.py",
    }


def ensure_results_ledger() -> list[dict[str, str]]:
    rows = load_results_rows()
    if rows:
        return rows
    seeded = seed_row()
    write_results_rows([seeded])
    return [normalize_row(seeded)]


def promoted_rows(rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    resolved_rows = rows if rows is not None else ensure_results_ledger()
    return [row for row in resolved_rows if truthy(row.get("promoted"))]


def current_promoted_row(rows: list[dict[str, str]] | None = None) -> dict[str, str]:
    promoted = promoted_rows(rows)
    if not promoted:
        raise RuntimeError("research/results.tsv does not contain a promoted row")
    return promoted[-1]


def current_master_hash(rows: list[dict[str, str]] | None = None) -> str:
    return current_promoted_row(rows)["candidate_hash"]


def current_master_snapshot(rows: list[dict[str, str]] | None = None) -> dict[str, Any]:
    rows = ensure_results_ledger() if rows is None else rows
    promoted_row = current_promoted_row(rows)
    return build_master_snapshot(promoted_row)


def existing_detail_source(expected_hash: str) -> str | None:
    for path in (MASTER_DETAIL_PATH, MASTER_DETAIL_SEED_PATH):
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        source = data.get("source")
        if not isinstance(source, str) or not source:
            continue
        normalized = normalize_source(source)
        if source_hash(normalized) == expected_hash:
            return normalized
    return None


def resolve_source_for_hash(expected_hash: str) -> str:
    if TRAIN_ORIG_PATH.exists():
        source = normalize_source(TRAIN_ORIG_PATH.read_text(encoding="utf-8"))
        if source_hash(source) == expected_hash:
            return source
    detail_source = existing_detail_source(expected_hash)
    if detail_source is not None:
        return detail_source
    raise RuntimeError(
        "could not recover source for current promoted master "
        f"{expected_hash}; train_orig.py and master detail do not match"
    )


def build_master_snapshot(row: dict[str, str]) -> dict[str, Any]:
    metadata = reference_master_metadata()
    snapshot: dict[str, Any] = {
        "hash": row["candidate_hash"],
        "parent_hash": row.get("parent_hash", ""),
        "val_bpb": parse_float(row.get("val_bpb")),
        "created_at": row.get("created_at", ""),
        "job_id": row.get("job_id", ""),
        "campaign": row.get("campaign", ""),
        "experiment_id": row.get("experiment_id", ""),
        "worker_id": row.get("worker_id", ""),
        "hypothesis": row.get("hypothesis", ""),
        "status": row.get("status", ""),
        "comment": row.get("comment", ""),
        "message": row.get("comment", ""),
        "promoted": True,
        "source": "local-results-tsv",
    }
    if row.get("status") == "legacy_seed":
        legacy_hash = metadata.get("hash")
        if isinstance(legacy_hash, str) and legacy_hash and legacy_hash != row["candidate_hash"]:
            snapshot["legacy_hash"] = legacy_hash
        contributor_id = metadata.get("contributor_id")
        if isinstance(contributor_id, str) and contributor_id:
            snapshot["contributor_id"] = contributor_id
        platform = metadata.get("platform")
        if isinstance(platform, str) and platform:
            snapshot["platform"] = platform
        patch_id = metadata.get("patch_id")
        if patch_id not in (None, ""):
            snapshot["patch_id"] = patch_id
    return snapshot


def build_master_detail(snapshot: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "hash": snapshot["hash"],
        "source": normalize_source(source),
        "source_path": "train_orig.py",
        "commit": snapshot,
    }


def build_dag(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    metadata = reference_master_metadata()
    promoted = promoted_rows(rows)
    if not promoted:
        return []
    current_hash = promoted[-1]["candidate_hash"]
    dag: list[dict[str, Any]] = []
    for row in promoted:
        entry: dict[str, Any] = {
            "hash": row["candidate_hash"],
            "parent_hash": row.get("parent_hash", ""),
            "contributor_id": "local",
            "message": row.get("comment", ""),
            "val_bpb": parse_float(row.get("val_bpb")),
            "platform": "",
            "created_at": row.get("created_at", ""),
            "is_master": row["candidate_hash"] == current_hash,
            "job_id": row.get("job_id", ""),
            "campaign": row.get("campaign", ""),
            "experiment_id": row.get("experiment_id", ""),
            "worker_id": row.get("worker_id", ""),
            "hypothesis": row.get("hypothesis", ""),
            "status": row.get("status", ""),
        }
        if row.get("status") == "legacy_seed":
            contributor_id = metadata.get("contributor_id")
            if isinstance(contributor_id, str) and contributor_id:
                entry["contributor_id"] = contributor_id
            platform = metadata.get("platform")
            if isinstance(platform, str):
                entry["platform"] = platform
        dag.append(entry)
    return dag


def rebuild_live_state(rows: list[dict[str, str]] | None = None) -> dict[str, Any]:
    rows = ensure_results_ledger() if rows is None else rows
    snapshot = current_master_snapshot(rows)
    source = resolve_source_for_hash(str(snapshot["hash"]))
    write_json(MASTER_PATH, snapshot)
    write_json(MASTER_DETAIL_PATH, build_master_detail(snapshot, source))
    write_json(DAG_PATH, build_dag(rows))
    return snapshot


def write_current_master_source(source: str) -> str:
    normalized = normalize_source(source)
    TRAIN_ORIG_PATH.write_text(normalized, encoding="utf-8")
    TRAIN_PATH.write_text(normalized, encoding="utf-8")
    return normalized


def restore_workspace_from_current_master(*, force: bool = False) -> dict[str, Any]:
    if train_files_diverged() and not force:
        raise RuntimeError(
            "train.py differs from train_orig.py; use --force if you really want to overwrite it"
        )
    rows = ensure_results_ledger()
    promoted_row = current_promoted_row(rows)
    source = resolve_source_for_hash(promoted_row["candidate_hash"])
    write_current_master_source(source)
    return rebuild_live_state(rows)
