#!/usr/bin/env python3
"""Manage NanoChat post-training runs on Hugging Face Jobs."""

from __future__ import annotations

import argparse
import base64
import gzip
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
DEFAULT_BUNDLE = RUNTIME_DIR / "posttrain-hf-job.py"
LAST_JOB_PATH = RUNTIME_DIR / "hf-job-last.json"
HF_JOB_STATE_DIR = RUNTIME_DIR / "hf-jobs"
HF_JOB_LOG_DIR = RUNTIME_DIR / "hf-logs"
POSTTRAIN_HOME = "/posttrain-home"
POSTTRAIN_CACHE_MOUNT = f"{POSTTRAIN_HOME}/.cache/autoresearch-posttraining"
TERMINAL_JOB_STAGES = {"COMPLETED", "CANCELED", "CANCELLED", "FAILED", "TIMEOUT", "ERROR"}
DEFAULT_NAMESPACE = os.environ.get("POSTTRAIN_HF_NAMESPACE") or os.environ.get("AUTOLAB_HF_NAMESPACE")
SUMMARY_KEYS = {
    "eval_score",
    "raw_accuracy",
    "num_correct",
    "num_examples",
    "train_loss",
    "training_seconds",
    "best_step",
    "best_limited_score",
}
ROOT_SOURCE_FILES = (
    "AGENTS.md",
    "README.md",
    "evaluate.py",
    "model.py",
    "prepare.py",
    "program.md",
    "pyproject.toml",
    "train.py",
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


def build_pep723_header() -> str:
    pyproject = load_pyproject()
    project = pyproject.get("project", {})
    tool = pyproject.get("tool", {})
    uv_tool = tool.get("uv", {}) if isinstance(tool, dict) else {}
    dependencies = list(project.get("dependencies", []))
    sources = uv_tool.get("sources", {}) if isinstance(uv_tool, dict) else {}
    indexes = uv_tool.get("index", []) if isinstance(uv_tool, dict) else []

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


def collect_source_files() -> list[Path]:
    paths: list[Path] = []
    for rel in ROOT_SOURCE_FILES:
        path = ROOT / rel
        if path.is_file():
            paths.append(path)
    src_root = ROOT / "src"
    if src_root.is_dir():
        for path in src_root.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def encode_source_files() -> dict[str, str]:
    encoded: dict[str, str] = {}
    for path in collect_source_files():
        rel = path.relative_to(ROOT).as_posix()
        payload = gzip.compress(path.read_bytes(), mtime=0)
        encoded[rel] = base64.b64encode(payload).decode("ascii")
    return encoded


def build_smoke_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path


if os.environ.get("POSTTRAIN_HOME"):
    os.environ["HOME"] = os.environ["POSTTRAIN_HOME"]

cache_root = Path(os.environ.get("POSTTRAIN_CACHE_DIR", Path.home() / ".cache" / "autoresearch-posttraining")).expanduser()
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
    body = r'''
from __future__ import annotations

import base64
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


SUMMARY_KEYS = __SUMMARY_KEYS__
MODE = __MODE__
FILES = __FILES__


def parse_metrics(text: str) -> dict[str, int | float | str] | None:
    metrics: dict[str, int | float | str] = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z_]+):\s+(.+)$", line.strip())
        if not match:
            continue
        key, raw = match.groups()
        if key not in SUMMARY_KEYS:
            continue
        value: int | float | str = raw.strip()
        for caster in (int, float):
            try:
                value = caster(raw)
                break
            except ValueError:
                continue
        metrics[key] = value
    return metrics if "eval_score" in metrics else None


def load_json_file(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def read_arg_vector(env_name: str) -> list[str]:
    raw = os.environ.get(env_name)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{env_name} must be a JSON list of strings: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise SystemExit(f"{env_name} must be a JSON list of strings")
    return data


def apply_home_override() -> Path:
    posttrain_home = os.environ.get("POSTTRAIN_HOME")
    if posttrain_home:
        os.environ["HOME"] = posttrain_home
    default_cache = Path.home() / ".cache" / "autoresearch-posttraining"
    cache_root = Path(os.environ.get("POSTTRAIN_CACHE_DIR", str(default_cache))).expanduser()
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ["POSTTRAIN_CACHE_DIR"] = str(cache_root)
    return cache_root


def hydrate_workspace(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    for name, payload in FILES.items():
        target = workdir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gzip.decompress(base64.b64decode(payload.encode("ascii"))))


def cache_ready(cache_root: Path) -> bool:
    return (
        (cache_root / "base_model" / "config.json").exists()
        and (cache_root / "base_model" / "model.pt").exists()
        and (cache_root / "data").is_dir()
    )


def run_logged(argv: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        print("running: " + " ".join(argv), flush=True)
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


def copy_source_snapshot(workdir: Path, artifact_dir: Path) -> None:
    source_dir = artifact_dir / "source"
    if source_dir.exists():
        shutil.rmtree(source_dir)
    for name in FILES:
        src = workdir / name
        dst = source_dir / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_final_model(workdir: Path, artifact_dir: Path) -> None:
    src = workdir / "final_model"
    if not src.is_dir():
        raise FileNotFoundError("train.py did not create final_model/")
    dst = artifact_dir / "final_model"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def merge_metric_dicts(*items: dict[str, object] | None) -> dict[str, object]:
    merged: dict[str, object] = {}
    for item in items:
        if not item:
            continue
        for key, value in item.items():
            if key == "examples":
                continue
            merged[key] = value
    return merged


def run_prepare(workdir: Path, artifact_dir: Path, env: dict[str, str]) -> int:
    argv = [sys.executable, "prepare.py"] + read_arg_vector("POSTTRAIN_PREPARE_ARGV")
    return run_logged(argv, cwd=workdir, env=env, log_path=artifact_dir / "prepare.log")


def main() -> int:
    cache_root = apply_home_override()
    job_id = os.environ.get("JOB_ID", "local")
    artifact_dir = cache_root / "runs" / job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(os.environ.get("POSTTRAIN_JOB_WORKDIR", f"/tmp/posttrain-{job_id}"))
    hydrate_workspace(workdir)

    manifest = {
        "job_id": job_id,
        "mode": MODE,
        "home": str(Path.home()),
        "cache_root": str(cache_root),
        "artifact_dir": str(artifact_dir),
        "workdir": str(workdir),
    }
    (artifact_dir / "job-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(workdir)
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

    if MODE == "prepare":
        rc = run_prepare(workdir, artifact_dir, env)
        if rc != 0:
            return rc
        if not cache_ready(cache_root):
            print(f"Post-training cache bootstrap incomplete at {cache_root}", file=sys.stderr)
            return 2
        copy_source_snapshot(workdir, artifact_dir)
        print(json.dumps({"job_id": job_id, "artifact_dir": str(artifact_dir), "cache_root": str(cache_root)}, indent=2))
        return 0

    prepare_rc = run_prepare(workdir, artifact_dir, env)
    if prepare_rc != 0:
        return prepare_rc

    train_argv = [sys.executable, "train.py"] + read_arg_vector("POSTTRAIN_TRAIN_ARGV")
    train_log = artifact_dir / "train.log"
    train_rc = run_logged(train_argv, cwd=workdir, env=env, log_path=train_log)
    train_metrics = parse_metrics(train_log.read_text(encoding="utf-8"))
    if train_rc != 0:
        return train_rc

    copy_final_model(workdir, artifact_dir)
    eval_argv = [
        sys.executable,
        "evaluate.py",
        *read_arg_vector("POSTTRAIN_EVAL_ARGV"),
        "--model-path",
        "final_model",
        "--json-output-file",
        "metrics.json",
    ]
    eval_log = artifact_dir / "evaluate.log"
    eval_rc = run_logged(eval_argv, cwd=workdir, env=env, log_path=eval_log)
    eval_log_metrics = parse_metrics(eval_log.read_text(encoding="utf-8"))
    eval_json_metrics = load_json_file(workdir / "metrics.json")
    metrics = merge_metric_dicts(train_metrics, eval_log_metrics, eval_json_metrics)
    if "eval_score" not in metrics:
        print(f"eval_score not found in {eval_log}", file=sys.stderr)
        return eval_rc or 3

    copy_source_snapshot(workdir, artifact_dir)
    shutil.copy2(workdir / "metrics.json", artifact_dir / "metrics.json")
    (artifact_dir / "summary.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"job_id": job_id, "artifact_dir": str(artifact_dir), "metrics": metrics}, indent=2, sort_keys=True))
    return eval_rc


if __name__ == "__main__":
    raise SystemExit(main())
'''
    script = "#!/usr/bin/env python3\n" + build_pep723_header() + "\n" + body
    replacements = {
        "__SUMMARY_KEYS__": repr(sorted(SUMMARY_KEYS)),
        "__MODE__": repr(mode),
        "__FILES__": repr(encode_source_files()),
    }
    for key, value in replacements.items():
        script = script.replace(key, value)
    return script


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
        value: int | float | str = raw.strip()
        for caster in (int, float):
            try:
                value = caster(raw)
                break
            except ValueError:
                continue
        metrics[key] = value
    return metrics if "eval_score" in metrics else None


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
        ("POSTTRAIN_EXPERIMENT_ID", "experiment_id"),
        ("POSTTRAIN_RUN_ID", "run_id"),
        ("POSTTRAIN_HYPOTHESIS", "hypothesis"),
    ):
        value = os.environ.get(env_name)
        if isinstance(value, str):
            value = value.strip()
        if value:
            context[key] = value
    return context


def collect_launch_context() -> dict[str, object]:
    context: dict[str, object] = {
        "workspace": str(ROOT),
        "launched_at": now_utc_iso(),
        "benchmark": "nanochat",
    }
    git_commit = git_output("git", "rev-parse", "HEAD")
    if git_commit:
        context["git_commit"] = git_commit
    branch = git_output("git", "rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        context["branch"] = branch
    context.update(env_context())
    return context


def label_value(context: dict[str, object], key: str) -> str | None:
    value = context.get(key)
    if isinstance(value, str) and value:
        slug = slugify_label_value(value)
        if slug:
            return slug
    return None


def build_job_labels(mode: str, context: dict[str, object] | None = None) -> list[str]:
    labels = [
        "posttrain",
        "benchmark=nanochat",
        f"mode={mode}",
        "launcher=hf-job-py",
    ]
    ctx = context or {}
    for context_key, label_key in (
        ("experiment_id", "experiment"),
        ("run_id", "run"),
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
    explicit = os.environ.get("POSTTRAIN_HF_CLI") or os.environ.get("AUTOLAB_HF_CLI")
    if explicit:
        return explicit
    preferred = Path.home() / ".local" / "bin" / "hf"
    if preferred.exists():
        return str(preferred)
    fallback = shutil.which("hf")
    if fallback:
        return fallback
    raise SystemExit("could not find `hf`; install the Hugging Face CLI first")


def resolve_bucket(explicit: str | None) -> str | None:
    return explicit or os.environ.get("POSTTRAIN_HF_BUCKET") or os.environ.get("AUTOLAB_HF_BUCKET")


def ensure_bucket(bucket: str) -> None:
    argv = [resolve_hf_cli(), "buckets", "create", bucket, "--private", "--exist-ok"]
    result = run_command(argv, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def default_flavor(mode: str) -> str:
    env_map = {
        "smoke": os.environ.get("POSTTRAIN_HF_SMOKE_FLAVOR"),
        "prepare": os.environ.get("POSTTRAIN_HF_PREPARE_FLAVOR"),
        "experiment": os.environ.get("POSTTRAIN_HF_EXPERIMENT_FLAVOR") or os.environ.get("POSTTRAIN_HF_FLAVOR"),
    }
    fallback = {
        "smoke": "cpu-basic",
        "prepare": "cpu-basic",
        "experiment": "h200",
    }
    return env_map.get(mode) or fallback[mode]


def default_timeout(mode: str) -> str:
    env_map = {
        "smoke": os.environ.get("POSTTRAIN_HF_SMOKE_TIMEOUT"),
        "prepare": os.environ.get("POSTTRAIN_HF_PREPARE_TIMEOUT"),
        "experiment": os.environ.get("POSTTRAIN_HF_EXPERIMENT_TIMEOUT") or os.environ.get("POSTTRAIN_HF_TIMEOUT"),
    }
    fallback = {
        "smoke": "10m",
        "prepare": "20m",
        "experiment": "90m",
    }
    return env_map.get(mode) or fallback[mode]


def default_secret_entries(mode: str) -> list[str]:
    raw = os.environ.get("POSTTRAIN_HF_SECRETS")
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


def set_env_entry(entries: list[str], key: str, value: str) -> None:
    prefix = f"{key}="
    entries[:] = [entry for entry in entries if not entry.startswith(prefix)]
    entries.append(f"{key}={value}")


def json_argv(raw: str | None, option_name: str) -> str | None:
    if raw is None:
        return None
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        raise SystemExit(f"{option_name} could not be parsed: {exc}") from exc
    return json.dumps(parts)


def launch_job(args: argparse.Namespace) -> int:
    bucket = resolve_bucket(args.bucket)
    if args.mode in {"prepare", "experiment"} and not bucket:
        raise SystemExit("POSTTRAIN_HF_BUCKET is required for prepare and experiment jobs")

    bundle_path = render_bundle(args.mode, args.output)
    flavor = args.flavor or default_flavor(args.mode)
    timeout = args.timeout or default_timeout(args.mode)
    hf_cli = resolve_hf_cli()
    context = collect_launch_context()

    if bucket and not args.skip_bucket_create:
        ensure_bucket(bucket)

    job_env = list(args.env)
    prepare_argv = json_argv(args.prepare_args, "--prepare-args")
    train_argv = json_argv(args.train_args, "--train-args")
    eval_argv = json_argv(args.eval_args, "--eval-args")
    if prepare_argv is not None:
        set_env_entry(job_env, "POSTTRAIN_PREPARE_ARGV", prepare_argv)
    if train_argv is not None:
        set_env_entry(job_env, "POSTTRAIN_TRAIN_ARGV", train_argv)
    if eval_argv is not None:
        set_env_entry(job_env, "POSTTRAIN_EVAL_ARGV", eval_argv)

    command = [hf_cli, "jobs", "uv", "run", "--flavor", flavor, "--timeout", timeout]
    if args.namespace:
        command.extend(["--namespace", args.namespace])
    if args.detach:
        command.append("--detach")
    label_entries = build_job_labels(args.mode, context) + args.label
    for label in label_entries:
        command.extend(["--label", label])
    for env_entry in job_env:
        command.extend(["--env", env_entry])
    secret_entries = resolve_secret_entries(args.mode, args.secret)
    for secret_entry in secret_entries:
        command.extend(["--secrets", secret_entry])
    if bucket:
        command.extend(["--env", f"POSTTRAIN_HOME={POSTTRAIN_HOME}"])
        command.extend(["--volume", f"hf://buckets/{bucket}:{POSTTRAIN_CACHE_MOUNT}"])
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

    state: dict[str, object] = {
        "mode": args.mode,
        "bundle_path": str(bundle_path),
        "bucket": bucket,
        "flavor": flavor,
        "hf_cli": hf_cli,
        "timeout": timeout,
        "command": command,
        "labels": parse_label_entries(label_entries),
        "secrets": secret_entries,
        "env": job_env,
    }
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage NanoChat post-training jobs on Hugging Face Jobs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="render the self-contained HF Jobs script")
    render_parser.add_argument("--mode", choices=("smoke", "prepare", "experiment"), default="experiment")
    render_parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)

    launch_parser = subparsers.add_parser("launch", help="render and submit an HF Job")
    launch_parser.add_argument("--mode", choices=("smoke", "prepare", "experiment"), default="experiment")
    launch_parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)
    launch_parser.add_argument("--bucket", help="HF bucket to mount at ~/.cache/autoresearch-posttraining")
    launch_parser.add_argument("--flavor", help="override HF Jobs flavor")
    launch_parser.add_argument("--timeout", help="override HF Jobs timeout")
    launch_parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="run the job under this namespace")
    launch_parser.add_argument("--env", action="append", default=[], help="extra HF Jobs --env entries")
    launch_parser.add_argument(
        "--secret",
        action="append",
        default=[],
        help="extra HF Jobs --secrets entries; defaults to HF_TOKEN for prepare/experiment unless POSTTRAIN_HF_SECRETS overrides",
    )
    launch_parser.add_argument("--label", action="append", default=[], help="extra HF Jobs --label entries")
    launch_parser.add_argument("--prepare-args", help="shell-style extra args for prepare.py")
    launch_parser.add_argument("--train-args", help="shell-style extra args for train.py")
    launch_parser.add_argument("--eval-args", help="shell-style extra args for evaluate.py")
    launch_parser.add_argument("--skip-bucket-create", action="store_true", help="do not create the bucket before launch")
    launch_parser.set_defaults(detach=True)
    detach_group = launch_parser.add_mutually_exclusive_group()
    detach_group.add_argument("--detach", dest="detach", action="store_true", help="submit in background (default)")
    detach_group.add_argument("--no-detach", dest="detach", action="store_false", help="stream logs during submission")

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
    if args.command == "logs":
        return stream_logs(args)
    if args.command == "inspect":
        return inspect_job(args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
