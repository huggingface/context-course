# Program

This repo is a self-contained `autoresearch`-style benchmark checkout with a
local promoted master and a git-tracked run ledger.

Core rules:

- use `uv`
- edit `train.py` only unless explicitly authorized otherwise
- never edit `prepare.py`
- refresh from the current local promoted master before a fresh experiment:
  `uv run scripts/refresh_master.py --fetch-dag`
- treat `train_orig.py`, `research/live/master.json`, and
  `research/results.tsv` as the benchmark source of truth
- run exactly one managed Hugging Face Jobs experiment per hypothesis
- record every completed run with
  `uv run scripts/submit_patch.py --comment "..."`
- promotion is local: `scripts/submit_patch.py` updates `train_orig.py` and the
  live master snapshots only when the observed `val_bpb` beats current master

Primary workflow:

1. `uv sync`
2. `uv run scripts/refresh_master.py --fetch-dag`
3. edit `train.py`
4. `uv run scripts/hf_job.py preflight`
5. `uv run scripts/hf_job.py launch --mode experiment`
6. `uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/autolab-run.log`
7. `uv run scripts/submit_patch.py --comment "..."`

Upstream compatibility:

- `uv run scripts/sync_upstream.py --check` compares the upstream-tracked files
  against `karpathy/autoresearch`
- `uv run scripts/sync_upstream.py --apply` copies those upstream files into
  this repo without touching the local results ledger
