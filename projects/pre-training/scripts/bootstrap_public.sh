#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CREDENTIALS_PATH="${HOME}/.autolab/credentials"

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_public.sh

Validate a public operator checkout for the self-contained local-master workflow.

This script:
  - checks python3, uv, and hf
  - validates Python >= 3.10
  - loads ~/.autolab/credentials when present
  - verifies AUTOLAB_HF_BUCKET
  - runs `hf auth whoami`
  - creates the shared HF bucket

It does not launch paid jobs.
EOF
}

need_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$name" >&2
    exit 1
  fi
}

load_credentials() {
  if [[ -f "$CREDENTIALS_PATH" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$CREDENTIALS_PATH"
    set +a
  fi
}

check_python() {
  python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("python3 >= 3.10 is required")
print(f"python3 {sys.version.split()[0]}")
PY
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    printf 'missing required environment variable: %s\n' "$name" >&2
    exit 1
  fi
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

need_cmd python3
need_cmd uv
need_cmd hf
check_python
load_credentials

require_env AUTOLAB_HF_BUCKET

printf 'validating Hugging Face auth...\n'
hf auth whoami >/dev/null

printf 'ensuring shared HF bucket exists: %s\n' "$AUTOLAB_HF_BUCKET"
hf buckets create "$AUTOLAB_HF_BUCKET" --private --exist-ok >/dev/null

cat <<EOF
bootstrap checks passed for:
  repo: $ROOT
  hf bucket: $AUTOLAB_HF_BUCKET
  hf namespace: ${AUTOLAB_HF_NAMESPACE:-<default>}
  trackio project: ${AUTOLAB_TRACKIO_PROJECT:-autolab}

next commands:
  cd $ROOT
  . ~/.autolab/credentials
  uv sync
  uv run scripts/hf_job.py launch --mode prepare
  uv run scripts/refresh_master.py --fetch-dag
  uv run scripts/hf_job.py preflight
  uv run scripts/hf_job.py launch --mode experiment
  uv run scripts/submit_patch.py --comment "one-sentence hypothesis and observed val_bpb"
EOF
