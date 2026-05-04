#!/usr/bin/env python3
"""Fixed PostTrainBench-style evaluator for the NanoChat task."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch


def add_project_path() -> None:
    here = Path(__file__).resolve()
    candidates = [Path.cwd(), *here.parents]
    for candidate in candidates:
        if (candidate / "model.py").is_file() and (candidate / "prepare.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError("Could not find model.py and prepare.py for NanoChat evaluation.")


add_project_path()

from model import load_model  # noqa: E402
from prepare import ensure_prepared, score_model, validate_model_directory  # noqa: E402


def pick_device(name: str) -> torch.device:
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a NanoChat final_model.")
    parser.add_argument("--model-path", type=Path, default=Path("final_model"))
    parser.add_argument("--split", choices=["eval"], default="eval")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=24)
    parser.add_argument("--json-output-file", type=Path, default=None)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--show-examples", type=int, default=0)
    args = parser.parse_args()

    ensure_prepared()
    validate_model_directory(args.model_path)
    device = pick_device(args.device)
    model = load_model(args.model_path, device=device)
    metrics = score_model(
        model,
        split=args.split,
        limit=args.limit,
        max_new_tokens=args.max_new_tokens,
        device=device,
        return_examples=args.show_examples > 0,
    )

    if args.show_examples > 0:
        shown = 0
        for task_metrics in metrics["tasks"].values():
            for row in task_metrics.get("examples", []):
                if shown >= args.show_examples:
                    break
                print(f"Q: {row['prompt']}")
                print(f"A: {row['answer']}")
                print(f"P: {row['prediction']}")
                print(f"correct: {row['correct']}")
                print()
                shown += 1
            if shown >= args.show_examples:
                break

    if args.json_output_file is not None:
        serializable = {k: v for k, v in metrics.items() if k != "examples"}
        with open(args.json_output_file, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)

    print("---")
    print(f"eval_score:   {float(metrics['eval_score']):.6f}")
    print(f"raw_accuracy: {float(metrics['raw_accuracy']):.6f}")
    print(f"num_correct:  {metrics['num_correct']}")
    print(f"num_examples: {metrics['num_examples']}")
    print(f"model_path:   {args.model_path}")
    print(f"split:        {args.split}")
    print("task_scores:")
    for task_name, task_metrics in metrics["tasks"].items():
        print(f"  {task_name:12s}: {float(task_metrics['accuracy']):.6f} ({task_metrics['num_correct']}/{task_metrics['num_examples']})")


if __name__ == "__main__":
    main()
