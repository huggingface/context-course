# Contributing

This repository has two different contribution paths:

1. Repo changes
   - Docs, helper scripts, control-plane changes, and reporting improvements
     belong in git history here.
2. Benchmark improvements
   - Benchmark runs are recorded locally with `uv run scripts/submit_patch.py`,
     and only local promotions that beat current master should update
     `train_orig.py` and `research/live/`.

## Before You Start

- Install dependencies with `uv sync`.
- Copy `.autolab.credentials.example` to `~/.autolab/credentials`, fill in your
  values, and load it with `. ~/.autolab/credentials`.
- Run `bash scripts/bootstrap_public.sh` to validate your local operator setup.

## Benchmark Rules

These rules are the contribution contract for any timed benchmark run:

- Refresh from the current local promoted master with
  `uv run scripts/refresh_master.py --fetch-dag`.
- Treat `research/live/master.json`, `research/live/master_detail.json`,
  `research/results.tsv`, and `train_orig.py` as the benchmark source of truth.
- Edit `train.py` only unless the task explicitly says otherwise.
- Never modify `prepare.py`.
- Make exactly one hypothesis change per run.
- Launch one managed HF Jobs benchmark run per hypothesis.
- Record every completed run with `uv run scripts/submit_patch.py --comment "..."`
- Promotion is local and only happens if observed `val_bpb` beats current
  master.
- Keep machine-local compatibility shims out of promoted diffs.

## What To Open As A Pull Request

Use pull requests for changes such as:

- public docs and setup improvements
- helper script fixes
- OpenCode agent and control-plane updates
- Trackio and reporting improvements
- research template and notebook workflow updates
- non-benchmark tooling changes

When you change a public command or workflow, update the docs in the same pull
request.

## What Not To Commit

Do not commit:

- `~/.autolab/credentials` or any other secret material
- local runtime state under `.runtime/`
- ad hoc failed experiment history that belongs in `research/results.tsv` or
  `research/notes.md`

## Useful Checks

Run the checks that match your change:

```bash
uv sync
bash -n scripts/bootstrap_public.sh
uv run scripts/hf_job.py preflight
uv run scripts/opencode_worker.py --help
uv run scripts/refresh_master.py --help
uv run scripts/submit_patch.py --help
uv run scripts/sync_upstream.py --check
uv run scripts/print_opencode_kickoff.py --help
uv run scripts/trackio_reporter.py summary --max-jobs 5
```

For docs-only changes, verify that all referenced files and commands exist.
