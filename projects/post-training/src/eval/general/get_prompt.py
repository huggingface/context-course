#!/usr/bin/env python3
"""Render the PostTrainBench-style task prompt for this project."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read_benchmark_name(benchmark_id: str) -> str:
    path = ROOT / "src" / "eval" / "tasks" / benchmark_id / "benchmark.txt"
    if not path.is_file():
        raise FileNotFoundError(f"Unknown benchmark id {benchmark_id!r}: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_prompt(model: str, benchmark_id: str, num_hours: str, num_gpus: int) -> str:
    template = (ROOT / "src" / "eval" / "general" / "prompt.txt").read_text(encoding="utf-8")
    benchmark = read_benchmark_name(benchmark_id)
    if num_gpus == 1:
        gpu_info = "- The machine has one GPU if available; CPU/MPS runs are supported for smoke tests."
    else:
        gpu_info = f"- The machine has {num_gpus} GPUs available."
    rendered = template.replace("{model}", model)
    rendered = rendered.replace("{benchmark}", benchmark)
    rendered = rendered.replace("{num_hours}", str(num_hours))
    rendered = rendered.replace("{gpu_info}", gpu_info)
    now = subprocess.run(["date", "-u"], capture_output=True, text=True, check=False).stdout.strip()
    return rendered + f"\n\nCurrent UTC time: {now}\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-to-train", default="NanoChat")
    parser.add_argument("--benchmark-id", default="nanochat")
    parser.add_argument("--num-hours", default="1")
    parser.add_argument("--num-gpus", type=int, default=1)
    args = parser.parse_args()
    print(build_prompt(args.model_to_train, args.benchmark_id, args.num_hours, args.num_gpus))


if __name__ == "__main__":
    main()
