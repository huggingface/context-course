#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ".runtime"
DEFAULT_BUNDLE = RUNTIME_DIR / "autolab-hf-job.py"
LAST_JOB_PATH = RUNTIME_DIR / "hf-job-last.json"
HF_JOB_STATE_DIR = RUNTIME_DIR / "hf-jobs"
HF_JOB_LOG_DIR = RUNTIME_DIR / "hf-logs"
AUTOLAB_HOME = "/autolab-home"
AUTOLAB_CACHE_MOUNT = f"{AUTOLAB_HOME}/.cache/autoresearch"
TERMINAL_JOB_STAGES = {"COMPLETED", "CANCELED", "CANCELLED", "FAILED", "TIMEOUT", "ERROR"}
DEFAULT_NAMESPACE = os.environ.get("AUTOLAB_HF_NAMESPACE")
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
PREPARE_DEPENDENCIES = {
    "pyarrow",
    "requests",
    "rustbpe",
    "tiktoken",
    "torch",
}
KNOWN_CHANGE_CATEGORY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("scheduler", ("FINAL_LR_FRAC", "WARMDOWN_RATIO", "get_lr_multiplier")),
    ("lm_head_weight_decay", ("lm_head_params", "weight_decay")),
    ("value_embeds_weight_decay", ("value_embeds_params", "weight_decay")),
    ("muon_beta2", ("momentum=0.95", "beta2=")),
    ("window_pattern", ("WINDOW_PATTERN",)),
    ("gqa_kv_heads", ("n_kv_head",)),
    ("value_embed_stride", ("has_ve", "layer_idx %")),
    ("attention_branch_scale", ("1.3 *", "attn_out")),
    ("attention_temperature", ("temperature",)),
)


def load_pyproject() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        items = ", ".join(f"{key} = {toml_value(val)}" for key, val in value.items())
        return "{ " + items + " }"
    raise TypeError(f"unsupported TOML value: {value!r}")


def dependency_name(spec: str) -> str:
    match = re.match(r"^\s*([A-Za-z0-9_.-]+)", spec)
    if not match:
        raise ValueError(f"unable to parse dependency name from {spec!r}")
    return match.group(1).lower().replace("_", "-")


def build_pep723_header(mode: str) -> str:
    pyproject = load_pyproject()
    project = pyproject.get("project", {})
    tool = pyproject.get("tool", {})
    uv_tool = tool.get("uv", {}) if isinstance(tool, dict) else {}
    project_dependencies = list(project.get("dependencies", []))
    sources = uv_tool.get("sources", {}) if isinstance(uv_tool, dict) else {}
    indexes = uv_tool.get("index", []) if isinstance(uv_tool, dict) else []

    if mode == "prepare":
        dependencies = [
            dependency
            for dependency in project_dependencies
            if dependency_name(dependency) in PREPARE_DEPENDENCIES
        ]
        missing = PREPARE_DEPENDENCIES - {dependency_name(dep) for dep in dependencies}
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise RuntimeError(f"prepare dependency set missing from pyproject: {missing_list}")
        # Prepare runs on CPU and only needs data/tokenizer tooling, not CUDA wheels.
        sources = {}
        indexes = []
    else:
        dependencies = project_dependencies

    lines: list[str] = [
        f'requires-python = {toml_value(project.get("requires-python", ">=3.10"))}',
        "dependencies = [",
    ]
    for dependency in dependencies:
        lines.append(f"  {toml_value(dependency)},")
    lines.append("]")

    if sources:
        lines.append("")
        lines.append("[tool.uv.sources]")
        for package, source_value in sources.items():
            lines.append(f"{package} = {toml_value(source_value)}")

    if indexes:
        for index in indexes:
            lines.append("")
            lines.append("[[tool.uv.index]]")
            for key, value in index.items():
                lines.append(f"{key} = {toml_value(value)}")

    header = ["# /// script"]
    for line in lines:
        header.append("#" if not line else f"# {line}")
    header.append("# ///")
    return "\n".join(header)


def encode_text(path: Path) -> str:
    return base64.b64encode(path.read_text().encode("utf-8")).decode("ascii")


def build_smoke_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path


if os.environ.get("AUTOLAB_HOME"):
    os.environ["HOME"] = os.environ["AUTOLAB_HOME"]

cache_root = Path.home() / ".cache" / "autoresearch"
cache_root.mkdir(parents=True, exist_ok=True)
job_id = os.environ.get("JOB_ID", "local")
artifact_dir = cache_root / "runs" / job_id
artifact_dir.mkdir(parents=True, exist_ok=True)

payload = {
    "job_id": job_id,
    "home": str(Path.home()),
    "cache_root": str(cache_root),
    "artifact_dir": str(artifact_dir),
    "entries": sorted(path.name for path in cache_root.iterdir())[:20],
}

(artifact_dir / "smoke.json").write_text(json.dumps(payload, indent=2) + "\\n")
print(json.dumps(payload, indent=2))
"""


def build_managed_script(mode: str) -> str:
    header = build_pep723_header(mode)
    prepare_payload = encode_text(ROOT / "prepare.py")
    train_payload = encode_text(ROOT / "train.py")
    return f"""#!/usr/bin/env python3
{header}
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path


SUMMARY_KEYS = {sorted(SUMMARY_KEYS)!r}
MODE = {mode!r}
FILES = {{
    "prepare.py": {prepare_payload!r},
    "train.py": {train_payload!r},
}}


def parse_metrics(text: str) -> dict[str, int | float | str] | None:
    metrics: dict[str, int | float | str] = {{}}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z_]+):\\s+(.+)$", line.strip())
        if not match:
            continue
        key, raw = match.groups()
        if key not in SUMMARY_KEYS:
            continue
        value: int | float | str = raw
        for caster in (int, float):
            try:
                value = caster(raw)
                break
            except ValueError:
                continue
        metrics[key] = value
    return metrics if "val_bpb" in metrics else None


def apply_home_override() -> Path:
    autolab_home = os.environ.get("AUTOLAB_HOME")
    if autolab_home:
        os.environ["HOME"] = autolab_home
    cache_root = Path.home() / ".cache" / "autoresearch"
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def hydrate_workspace(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    for name, payload in FILES.items():
        target = workdir / name
        target.write_text(base64.b64decode(payload).decode("utf-8"))


def cache_missing(cache_root: Path) -> list[str]:
    missing: list[str] = []
    tokenizer_dir = cache_root / "tokenizer"
    data_dir = cache_root / "data"
    if not (tokenizer_dir / "tokenizer.pkl").exists():
        missing.append("tokenizer/tokenizer.pkl")
    if not (tokenizer_dir / "token_bytes.pt").exists():
        missing.append("tokenizer/token_bytes.pt")
    val_shard = data_dir / "shard_06542.parquet"
    if not val_shard.exists():
        missing.append("data/shard_06542.parquet")
    train_ready = False
    if data_dir.exists():
        train_ready = any(path.name != "shard_06542.parquet" for path in data_dir.glob("shard_*.parquet"))
    if not train_ready:
        missing.append("data/<train-shard>")
    return missing


def run_logged(argv: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            handle.write(line)
    return proc.wait()


def main() -> int:
    cache_root = apply_home_override()
    job_id = os.environ.get("JOB_ID", "local")
    artifact_dir = cache_root / "runs" / job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(os.environ.get("AUTOLAB_JOB_WORKDIR", f"/tmp/autolab-{{job_id}}"))
    hydrate_workspace(workdir)

    manifest = {{
        "job_id": job_id,
        "mode": MODE,
        "home": str(Path.home()),
        "cache_root": str(cache_root),
        "artifact_dir": str(artifact_dir),
        "workdir": str(workdir),
    }}
    (artifact_dir / "job-manifest.json").write_text(json.dumps(manifest, indent=2) + "\\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(workdir)
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    env.pop("AUTOLAB_FORCE_FA3_REDIRECT", None)

    if MODE == "prepare":
        log_path = artifact_dir / "prepare.log"
        rc = run_logged([sys.executable, "prepare.py"], cwd=workdir, env=env, log_path=log_path)
        if rc != 0:
            return rc
        missing = cache_missing(cache_root)
        if missing:
            print("Autolab cache bootstrap incomplete: " + ", ".join(missing), file=sys.stderr)
            return 2
        print(f"Prepared cache at {{cache_root}}")
        return 0

    missing = cache_missing(cache_root)
    if missing:
        print("Autolab cache missing: " + ", ".join(missing), file=sys.stderr)
        print("Run `uv run scripts/hf_job.py launch --mode prepare` first.", file=sys.stderr)
        return 2

    log_path = artifact_dir / "autolab-run.log"
    rc = run_logged([sys.executable, "train.py"], cwd=workdir, env=env, log_path=log_path)
    log_text = log_path.read_text(encoding="utf-8")
    metrics = parse_metrics(log_text)
    (artifact_dir / "train.py").write_text((workdir / "train.py").read_text(encoding="utf-8"))
    if metrics is None:
        print(f"val_bpb not found in {{log_path}}", file=sys.stderr)
        return rc or 3
    (artifact_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\\n")
    print(json.dumps({{"job_id": job_id, "artifact_dir": str(artifact_dir), "metrics": metrics}}, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
"""


def render_bundle(mode: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "smoke":
        script_text = build_smoke_script()
    elif mode in {"prepare", "experiment"}:
        script_text = build_managed_script(mode)
    else:
        raise SystemExit(f"unsupported mode: {mode}")
    output_path.write_text(script_text, encoding="utf-8")
    return output_path


def parse_metrics(text: str) -> dict[str, int | float | str] | None:
    metrics: dict[str, int | float | str] = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z_]+):\s+(.+)$", line.strip())
        if not match:
            continue
        key, raw = match.groups()
        if key not in SUMMARY_KEYS:
            continue
        value: int | float | str = raw
        for caster in (int, float):
            try:
                value = caster(raw)
                break
            except ValueError:
                continue
        metrics[key] = value
    return metrics if "val_bpb" in metrics else None


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_file(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def git_output(*argv: str) -> str | None:
    result = subprocess.run(
        list(argv),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def slugify_label_value(value: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        return ""
    return slug[:max_len].rstrip("_")


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


def label_value(context: dict[str, object], key: str) -> str | None:
    value = context.get(key)
    if isinstance(value, str) and value:
        slug = slugify_label_value(value)
        if slug:
            return slug
    return None


def collect_launch_context() -> dict[str, object]:
    context: dict[str, object] = {
        "workspace": str(ROOT),
        "launched_at": now_utc_iso(),
    }

    git_commit = git_output("git", "rev-parse", "HEAD")
    if git_commit:
        context["git_commit"] = git_commit

    branch = git_output("git", "rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        context["branch"] = branch

    context.update(env_context())

    master_data = load_json_file(ROOT / "research" / "live" / "master.json")
    if master_data:
        master_hash = master_data.get("hash")
        master_val_bpb = master_data.get("val_bpb")
        if isinstance(master_hash, str) and master_hash:
            context["master_hash"] = master_hash
        if isinstance(master_val_bpb, (int, float)):
            context["master_val_bpb"] = master_val_bpb

    return context


def job_stage(job: dict[str, object]) -> str:
    status = job.get("status")
    if isinstance(status, dict):
        stage = status.get("stage")
        if isinstance(stage, str) and stage:
            return stage.upper()
    return "UNKNOWN"


def fetch_active_jobs(namespace: str | None) -> list[dict[str, object]]:
    argv = [resolve_hf_cli(), "jobs", "ps", "-a", "--format", "json"]
    if namespace:
        argv.extend(["--namespace", namespace])
    result = run_command(argv, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "command failed"
        raise RuntimeError(f"unable to query active HF Jobs: {stderr}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"unable to parse HF Jobs listing: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError("unexpected `hf jobs ps` payload")
    active: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if job_stage(item) in TERMINAL_JOB_STAGES:
            continue
        active.append(item)
    return active


def train_diff_preview(limit: int = 24) -> tuple[list[str], int, int]:
    orig_path = ROOT / "train_orig.py"
    train_path = ROOT / "train.py"
    if not orig_path.exists() or not train_path.exists():
        return [], 0, 0
    orig_lines = orig_path.read_text(encoding="utf-8").splitlines()
    train_lines = train_path.read_text(encoding="utf-8").splitlines()
    diff_lines = list(
        difflib.unified_diff(
            orig_lines,
            train_lines,
            fromfile="train_orig.py",
            tofile="train.py",
            n=0,
            lineterm="",
        )
    )
    hunk_count = sum(1 for line in diff_lines if line.startswith("@@"))
    changed_line_count = sum(
        1
        for line in diff_lines
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    )
    preview = diff_lines[:limit]
    return preview, hunk_count, changed_line_count


def detect_known_change_categories(preview: list[str]) -> list[str]:
    changed_lines = [line[1:] for line in preview if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    categories: list[str] = []
    for name, needles in KNOWN_CHANGE_CATEGORY_PATTERNS:
        if all(any(needle in line for line in changed_lines) for needle in needles):
            categories.append(name)
    return categories


def build_preflight_report(context: dict[str, object], namespace: str | None) -> dict[str, object]:
    report: dict[str, object] = {
        "context": context,
        "errors": [],
        "warnings": [],
    }
    errors = report["errors"]
    warnings = report["warnings"]
    assert isinstance(errors, list)
    assert isinstance(warnings, list)

    train_path = ROOT / "train.py"
    orig_path = ROOT / "train_orig.py"
    report["train_exists"] = train_path.exists()
    report["train_orig_exists"] = orig_path.exists()
    if not train_path.exists():
        errors.append("missing train.py")
    if not orig_path.exists():
        errors.append("missing train_orig.py; run refresh_master first")

    preview, hunk_count, changed_line_count = train_diff_preview()
    report["diff_preview"] = preview
    report["diff_hunks"] = hunk_count
    report["diff_changed_lines"] = changed_line_count
    report["known_change_categories"] = detect_known_change_categories(preview)

    if orig_path.exists() and train_path.exists():
        same = train_path.read_text(encoding="utf-8") == orig_path.read_text(encoding="utf-8")
        report["train_matches_orig"] = same
        if same:
            errors.append("train.py matches train_orig.py; no experiment change is present")
        elif hunk_count == 0:
            errors.append("unable to compute a diff between train.py and train_orig.py")
        if changed_line_count > 24:
            warnings.append("train.py differs from train_orig.py by many lines; review for accidental multi-change drift")
        categories = report["known_change_categories"]
        if isinstance(categories, list) and len(categories) > 1:
            errors.append(
                "train.py appears to change multiple known hypothesis categories relative to train_orig.py: "
                + ", ".join(categories)
            )
        elif not categories and hunk_count > 3:
            warnings.append("train.py diff spans multiple hunks and does not match a known single-change category")

    experiment_id = label_value(context, "experiment_id")
    hypothesis = label_value(context, "hypothesis")
    active_conflicts: list[dict[str, object]] = []
    active_job_warnings: list[str] = []
    try:
        active_jobs = fetch_active_jobs(namespace)
    except RuntimeError as exc:
        active_jobs = []
        active_job_warnings.append(str(exc))

    for job in active_jobs:
        labels = job.get("labels")
        if not isinstance(labels, dict):
            continue
        mode = labels.get("mode")
        if isinstance(experiment_id, str) and labels.get("experiment") == experiment_id and mode == "experiment":
            active_conflicts.append(
                {
                    "job_id": job.get("id"),
                    "reason": f"active experiment already exists for experiment {experiment_id}",
                    "mode": mode,
                    "stage": job_stage(job),
                    "flavor": job.get("flavor"),
                }
            )
        elif isinstance(hypothesis, str) and labels.get("hypothesis") == hypothesis and mode == "experiment":
            active_job_warnings.append(
                f"another active experiment shares hypothesis label {hypothesis}: {job.get('id')}"
            )

    report["active_conflicts"] = active_conflicts
    report["active_job_warnings"] = active_job_warnings
    return report


def print_preflight_report(report: dict[str, object]) -> None:
    print("Preflight:")
    context = report.get("context")
    if isinstance(context, dict):
        campaign = context.get("campaign")
        experiment_id = context.get("experiment_id")
        hypothesis = context.get("hypothesis")
        worker_id = context.get("worker_id")
        master_hash = context.get("master_hash")
        parts: list[str] = []
        if isinstance(campaign, str) and campaign:
            parts.append(f"campaign={campaign}")
        if isinstance(experiment_id, str) and experiment_id:
            parts.append(f"experiment={experiment_id}")
        if isinstance(worker_id, str) and worker_id:
            parts.append(f"worker={worker_id}")
        if isinstance(hypothesis, str) and hypothesis:
            parts.append(f"hypothesis={hypothesis}")
        if isinstance(master_hash, str) and master_hash:
            parts.append(f"master={master_hash[:12]}")
        if parts:
            print("  " + " | ".join(parts))

    print(
        "  "
        + f"diff_hunks={report.get('diff_hunks', 0)}"
        + f" changed_lines={report.get('diff_changed_lines', 0)}"
        + f" categories={report.get('known_change_categories', [])}"
    )
    preview = report.get("diff_preview")
    if isinstance(preview, list) and preview:
        print("  diff preview:")
        for line in preview:
            print(f"    {line}")
    errors = report.get("errors")
    if isinstance(errors, list):
        for entry in errors:
            print(f"  ERROR: {entry}")
    warnings = report.get("warnings")
    if isinstance(warnings, list):
        for entry in warnings:
            print(f"  WARN: {entry}")
    active_job_warnings = report.get("active_job_warnings")
    if isinstance(active_job_warnings, list):
        for entry in active_job_warnings:
            print(f"  WARN: {entry}")
    active_conflicts = report.get("active_conflicts")
    if isinstance(active_conflicts, list):
        for entry in active_conflicts:
            if isinstance(entry, dict):
                print(
                    "  ERROR: "
                    + str(entry.get("reason", "active conflict"))
                    + f" ({entry.get('job_id')}, {entry.get('stage')}, {entry.get('flavor')})"
                )


def resolve_bucket(explicit: str | None) -> str | None:
    return explicit or os.environ.get("AUTOLAB_HF_BUCKET")


def default_flavor(mode: str) -> str:
    env_map = {
        "smoke": os.environ.get("AUTOLAB_HF_SMOKE_FLAVOR"),
        "prepare": os.environ.get("AUTOLAB_HF_PREPARE_FLAVOR"),
        "experiment": os.environ.get("AUTOLAB_HF_EXPERIMENT_FLAVOR") or os.environ.get("AUTOLAB_HF_FLAVOR"),
    }
    fallback = {
        "smoke": "cpu-basic",
        "prepare": "cpu-performance",
        "experiment": "h200",
    }
    return env_map.get(mode) or fallback[mode]


def default_timeout(mode: str) -> str:
    env_map = {
        "smoke": os.environ.get("AUTOLAB_HF_SMOKE_TIMEOUT"),
        "prepare": os.environ.get("AUTOLAB_HF_PREPARE_TIMEOUT"),
        "experiment": os.environ.get("AUTOLAB_HF_EXPERIMENT_TIMEOUT") or os.environ.get("AUTOLAB_HF_TIMEOUT"),
    }
    fallback = {
        "smoke": "10m",
        "prepare": "2h",
        "experiment": "90m",
    }
    return env_map.get(mode) or fallback[mode]


def default_secret_entries(mode: str) -> list[str]:
    raw = os.environ.get("AUTOLAB_HF_SECRETS")
    if raw is not None:
        return [entry for entry in re.split(r"[\s,]+", raw) if entry]
    if mode in {"prepare", "experiment"}:
        return ["HF_TOKEN"]
    return []


def resolve_secret_entries(mode: str, extra_entries: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for entry in [*default_secret_entries(mode), *extra_entries]:
        value = entry.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


def build_job_labels(mode: str, context: dict[str, object] | None = None) -> list[str]:
    labels = [
        "autolab",
        f"mode={mode}",
        "launcher=hf-job-py",
    ]
    ctx = context or {}
    master_hash = ctx.get("master_hash")
    if isinstance(master_hash, str) and master_hash:
        labels.append(f"master={master_hash[:12]}")
    for context_key, label_key in (
        ("campaign", "campaign"),
        ("experiment_id", "experiment"),
        ("worker_id", "worker"),
        ("hypothesis", "hypothesis"),
    ):
        value = label_value(ctx, context_key)
        if value:
            labels.append(f"{label_key}={value}")
    return labels


def parse_job_id(text: str) -> str | None:
    matches = re.findall(r"\b[0-9a-f]{24}\b", text)
    return matches[-1] if matches else None


def run_command(argv: list[str], capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("HF_HUB_DISABLE_EXPERIMENTAL_WARNING", "1")
    return subprocess.run(argv, text=True, capture_output=capture_output, check=False, env=env)


def parse_label_entries(entries: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for entry in entries:
        if "=" in entry:
            key, value = entry.split("=", 1)
            labels[key] = value
        else:
            labels[entry] = ""
    return labels


def persist_job_state(state: dict[str, object]) -> None:
    job_id = state.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        return
    HF_JOB_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = HF_JOB_STATE_DIR / f"{job_id}.json"
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def ensure_bucket(bucket: str) -> None:
    argv = [resolve_hf_cli(), "buckets", "create", bucket, "--private", "--exist-ok"]
    result = run_command(argv, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def launch_job(args: argparse.Namespace) -> int:
    bucket = resolve_bucket(args.bucket)
    if args.mode in {"prepare", "experiment"} and not bucket:
        raise SystemExit("AUTOLAB_HF_BUCKET is required for prepare and experiment jobs")

    context = collect_launch_context()
    preflight_report: dict[str, object] | None = None
    scoped_prepare_keys = [key for key in ("campaign", "experiment_id", "worker_id", "hypothesis") if context.get(key)]
    if args.mode == "prepare" and scoped_prepare_keys and not args.allow_scoped_prepare:
        raise SystemExit(
            "prepare jobs are shared bootstrap work; do not launch them from an experiment-scoped workspace. "
            "Run prepare once from the parent checkout, or pass --allow-scoped-prepare if you really mean it."
        )
    if args.mode == "experiment":
        preflight_report = build_preflight_report(context, args.namespace)
        print_preflight_report(preflight_report)
        errors = []
        if isinstance(preflight_report.get("errors"), list):
            errors.extend(str(item) for item in preflight_report["errors"])
        conflicts = preflight_report.get("active_conflicts")
        if isinstance(conflicts, list) and conflicts and not args.allow_duplicate:
            errors.append("active experiment conflict detected")
        if errors and not args.allow_preflight_fail:
            raise SystemExit(
                "preflight failed:\n- " + "\n- ".join(errors) + "\n"
                + "Fix the workspace or pass --allow-preflight-fail / --allow-duplicate to override."
            )

    bundle_path = render_bundle(args.mode, args.output)
    flavor = args.flavor or default_flavor(args.mode)
    timeout = args.timeout or default_timeout(args.mode)
    hf_cli = resolve_hf_cli()

    if bucket and not args.skip_bucket_create:
        ensure_bucket(bucket)

    command = [hf_cli, "jobs", "uv", "run", "--flavor", flavor, "--timeout", timeout]
    if args.namespace:
        command.extend(["--namespace", args.namespace])
    if args.detach:
        command.append("--detach")
    label_entries = build_job_labels(args.mode, context) + args.label
    for label in label_entries:
        command.extend(["--label", label])
    for env_entry in args.env:
        command.extend(["--env", env_entry])
    secret_entries = resolve_secret_entries(args.mode, args.secret)
    for secret_entry in secret_entries:
        command.extend(["--secrets", secret_entry])
    if bucket:
        command.extend(["--env", f"AUTOLAB_HOME={AUTOLAB_HOME}"])
        command.extend(["--volume", f"hf://buckets/{bucket}:{AUTOLAB_CACHE_MOUNT}"])
    command.append(str(bundle_path))

    print("Launching HF Job:")
    print("  " + " ".join(shlex.quote(part) for part in command))
    result = run_command(command, capture_output=True)
    combined_output = (result.stdout or "") + (result.stderr or "")
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        return result.returncode

    state = {
        "mode": args.mode,
        "bundle_path": str(bundle_path),
        "bucket": bucket,
        "flavor": flavor,
        "hf_cli": hf_cli,
        "timeout": timeout,
        "command": command,
        "labels": parse_label_entries(label_entries),
        "secrets": secret_entries,
    }
    if preflight_report is not None:
        state["preflight"] = preflight_report
    state.update(context)
    job_id = parse_job_id(combined_output)
    if job_id:
        state["job_id"] = job_id
    if args.namespace:
        state["namespace"] = args.namespace
    LAST_JOB_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_JOB_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    persist_job_state(state)
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


def resolve_job_id(explicit: str | None) -> str:
    if explicit:
        return explicit
    if LAST_JOB_PATH.exists():
        data = json.loads(LAST_JOB_PATH.read_text(encoding="utf-8"))
        job_id = data.get("job_id")
        if isinstance(job_id, str) and job_id:
            return job_id
    raise SystemExit("job id required; pass one explicitly or launch a job first")


def stream_logs(args: argparse.Namespace) -> int:
    job_id = resolve_job_id(args.job_id)
    argv = [resolve_hf_cli(), "jobs", "logs"]
    if args.follow:
        argv.append("--follow")
    if args.tail is not None:
        argv.extend(["--tail", str(args.tail)])
    if args.namespace:
        argv.extend(["--namespace", args.namespace])
    argv.append(job_id)

    output_handles = []
    collected: list[str] = []
    try:
        local_log_path = HF_JOB_LOG_DIR / f"{job_id}.log"
        local_log_path.parent.mkdir(parents=True, exist_ok=True)
        output_handles.append(local_log_path.open("w", encoding="utf-8"))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.output.resolve() != local_log_path.resolve():
                output_handles.append(args.output.open("w", encoding="utf-8"))
        proc = subprocess.Popen(
            argv,
            env={**os.environ, "HF_HUB_DISABLE_EXPERIMENTAL_WARNING": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            collected.append(line)
            for output_handle in output_handles:
                output_handle.write(line)
        rc = proc.wait()
    finally:
        for output_handle in output_handles:
            output_handle.close()

    metrics = parse_metrics("".join(collected))
    state = load_json_file(HF_JOB_STATE_DIR / f"{job_id}.json") or {"job_id": job_id}
    state["cached_log_path"] = str(local_log_path)
    if args.output:
        state["output_log_path"] = str(args.output)
    if metrics is not None:
        state["metrics"] = metrics
    persist_job_state(state)
    last_state = load_json_file(LAST_JOB_PATH)
    if isinstance(last_state, dict) and last_state.get("job_id") == job_id:
        last_state["cached_log_path"] = str(local_log_path)
        if args.output:
            last_state["output_log_path"] = str(args.output)
        if metrics is not None:
            last_state["metrics"] = metrics
        LAST_JOB_PATH.write_text(json.dumps(last_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if metrics is not None:
        print(json.dumps({"job_id": job_id, "metrics": metrics}, indent=2, sort_keys=True))
    return rc


def inspect_job(args: argparse.Namespace) -> int:
    job_id = resolve_job_id(args.job_id)
    argv = [resolve_hf_cli(), "jobs", "inspect"]
    if args.namespace:
        argv.extend(["--namespace", args.namespace])
    argv.append(job_id)
    result = run_command(argv, capture_output=False)
    return result.returncode


def preflight_command(args: argparse.Namespace) -> int:
    context = collect_launch_context()
    report = build_preflight_report(context, args.namespace)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_preflight_report(report)
    has_errors = isinstance(report.get("errors"), list) and bool(report["errors"])
    has_conflicts = isinstance(report.get("active_conflicts"), list) and bool(report["active_conflicts"])
    return 2 if has_errors or has_conflicts else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Autolab benchmark jobs on Hugging Face Jobs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="render the self-contained HF Jobs script")
    render_parser.add_argument("--mode", choices=("smoke", "prepare", "experiment"), default="experiment")
    render_parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)

    launch_parser = subparsers.add_parser("launch", help="render and submit an HF Job")
    launch_parser.add_argument("--mode", choices=("smoke", "prepare", "experiment"), default="experiment")
    launch_parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)
    launch_parser.add_argument("--bucket", help="HF bucket to mount at ~/.cache/autoresearch")
    launch_parser.add_argument("--flavor", help="override HF Jobs flavor")
    launch_parser.add_argument("--timeout", help="override HF Jobs timeout")
    launch_parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="run the job under this namespace")
    launch_parser.add_argument("--env", action="append", default=[], help="extra HF Jobs --env entries")
    launch_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        help="extra HF Jobs --secrets entries; defaults to HF_TOKEN for prepare/experiment unless AUTOLAB_HF_SECRETS overrides",
    )
    launch_parser.add_argument("--label", action="append", default=[], help="extra HF Jobs --label entries")
    launch_parser.add_argument("--skip-bucket-create", action="store_true", help="do not create the bucket before launch")
    launch_parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="allow launching even if an active experiment already exists for this experiment id",
    )
    launch_parser.add_argument("--allow-preflight-fail", action="store_true", help="launch even when train.py preflight reports errors")
    launch_parser.add_argument(
        "--allow-scoped-prepare",
        action="store_true",
        help="allow a prepare job from an experiment-scoped workspace (normally blocked)",
    )
    launch_parser.add_argument("--allow-bead-prepare", action="store_true", dest="allow_scoped_prepare", help=argparse.SUPPRESS)
    launch_parser.set_defaults(detach=True)
    detach_group = launch_parser.add_mutually_exclusive_group()
    detach_group.add_argument("--detach", dest="detach", action="store_true", help="submit in background (default)")
    detach_group.add_argument("--no-detach", dest="detach", action="store_false", help="stream logs during submission")

    preflight_parser = subparsers.add_parser("preflight", help="audit the current workspace before launching an experiment")
    preflight_parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="namespace that owns the jobs")
    preflight_parser.add_argument("--json", action="store_true", help="emit the preflight report as JSON")

    logs_parser = subparsers.add_parser("logs", help="stream or fetch HF Jobs logs")
    logs_parser.add_argument("job_id", nargs="?", help="HF job id; defaults to the last launched job")
    logs_parser.add_argument("--follow", action="store_true", help="stream until completion")
    logs_parser.add_argument("--tail", type=int, help="only fetch the last N lines")
    logs_parser.add_argument("--output", type=Path, help="write logs to this file while streaming")
    logs_parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="namespace that owns the job")

    inspect_parser = subparsers.add_parser("inspect", help="inspect HF Job status")
    inspect_parser.add_argument("job_id", nargs="?", help="HF job id; defaults to the last launched job")
    inspect_parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="namespace that owns the job")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "render":
        path = render_bundle(args.mode, args.output)
        print(path)
        return 0
    if args.command == "launch":
        return launch_job(args)
    if args.command == "preflight":
        return preflight_command(args)
    if args.command == "logs":
        return stream_logs(args)
    if args.command == "inspect":
        return inspect_job(args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
