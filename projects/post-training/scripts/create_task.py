#!/usr/bin/env python3
"""Create an isolated PostTrainBench-style NanoChat task directory."""

from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prepare import ensure_prepared  # noqa: E402


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_timer(path: Path, num_hours: float) -> None:
    deadline = int(time.time() + num_hours * 3600)
    path.write_text(
        f"""#!/usr/bin/env bash
now=$(date +%s)
remaining=$(({deadline} - now))
if [ "$remaining" -lt 0 ]; then
  remaining=0
fi
printf '%02d:%02d:%02d\\n' $((remaining / 3600)) $(((remaining % 3600) / 60)) $((remaining % 60))
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def render_prompt(benchmark_id: str, num_hours: float, num_gpus: int) -> str:
    cmd = [
        sys.executable,
        str(ROOT / "src" / "eval" / "general" / "get_prompt.py"),
        "--model-to-train",
        "NanoChat",
        "--benchmark-id",
        benchmark_id,
        "--num-hours",
        str(num_hours),
        "--num-gpus",
        str(num_gpus),
    ]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def create_task(run_dir: Path, benchmark_id: str, num_hours: float, num_gpus: int, force: bool) -> None:
    if run_dir.exists():
        if not force:
            raise FileExistsError(f"{run_dir} already exists. Use --force to replace it.")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    ensure_prepared()
    task_src = ROOT / "src" / "eval" / "tasks" / benchmark_id
    if not task_src.is_dir():
        raise FileNotFoundError(f"Unknown benchmark id {benchmark_id!r}: {task_src}")

    for name in ["model.py", "prepare.py", "train.py", "pyproject.toml", "AGENTS.md"]:
        copy_file(ROOT / name, run_dir / name)
    copy_file(task_src / "evaluate.py", run_dir / "evaluate.py")
    copy_file(task_src / "benchmark.txt", run_dir / "benchmark.txt")
    context_dir = task_src / "task_context"
    if context_dir.is_dir():
        shutil.copytree(context_dir, run_dir / "task_context")
    write_timer(run_dir / "timer.sh", num_hours)
    (run_dir / "prompt.txt").write_text(
        render_prompt(benchmark_id, num_hours, num_gpus),
        encoding="utf-8",
    )
    (run_dir / "README.md").write_text(
        """# NanoChat Post-Training Task

Read `prompt.txt`, improve or replace `train.py`, save the best model to
`final_model/`, then run:

```bash
python evaluate.py --model-path final_model --json-output-file metrics.json
```
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local NanoChat post-training task sandbox.")
    parser.add_argument("--benchmark-id", default="nanochat")
    parser.add_argument("--num-hours", type=float, default=1.0)
    parser.add_argument("--num-gpus", type=int, default=1)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    run_dir = args.run_dir
    if run_dir is None:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        run_dir = ROOT / "runs" / f"{args.benchmark_id}-{timestamp}"
    create_task(run_dir, args.benchmark_id, args.num_hours, args.num_gpus, args.force)
    print(f"task_dir: {run_dir}")
    print(f"prompt:   {run_dir / 'prompt.txt'}")
    print("next:")
    print(f"  cd {run_dir}")
    print("  python train.py")
    print("  python evaluate.py --model-path final_model --json-output-file metrics.json")


if __name__ == "__main__":
    main()
