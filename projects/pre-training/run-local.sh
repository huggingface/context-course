#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PATH="${1:-/tmp/autolab-run.log}"
TIMEOUT_SECS="${TIMEOUT_SECS:-600}"

cd "$ROOT"

export PYTHONPATH=.
export AUTOLAB_FORCE_FA3_REDIRECT=1
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

timeout "$TIMEOUT_SECS" uv run train.py 2>&1 | tee "$LOG_PATH"
