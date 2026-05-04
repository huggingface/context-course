#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse the final autolab metric block from a log.")
    parser.add_argument("log_path", help="path to the run log")
    args = parser.parse_args()

    text = Path(args.log_path).read_text()
    metrics: dict[str, int | float | str] = {}
    for line in text.splitlines():
        match = re.match(r"^([a-z_]+):\s+(.+)$", line.strip())
        if not match:
            continue
        key, value = match.groups()
        if key in SUMMARY_KEYS:
            metrics[key] = coerce_value(value)

    if "val_bpb" not in metrics:
        raise SystemExit(f"val_bpb not found in {args.log_path}")

    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
