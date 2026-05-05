# Agent Instructions

This repo is a live Autolab experiment repo with a local promoted master.

## Goal

Lower `val_bpb` on the benchmark with disciplined, comparable single-change
experiments.

## Hard Rules

- Edit `train.py` only unless the task explicitly says otherwise.
- Never modify `prepare.py`.
- Start from the current local promoted master, not stale local history.
- Treat `uv run scripts/refresh_master.py --fetch-dag`,
  `research/live/master.json`, `research/results.tsv`, and `train_orig.py` as
  the benchmark source of truth.
- Do not use repo git history such as `main` or `origin/main` to decide whether
  an experiment is fresh; this repository also carries control-plane commits.
- Make exactly one hypothesis change per run.
- Run the timed benchmark before claiming success.
- Record every completed run with `uv run scripts/submit_patch.py --comment "..."`
- Promotion is local and only happens when local `val_bpb` beats current
  master.
- Keep machine-local compatibility shims out of promoted diffs.

## OpenCode Control Plane

- Repo-scoped OpenCode config lives in `opencode.json`.
- Custom repo agents live in `.opencode/agent/`.
- Shared repo skills live in `.agents/skills/`.
- `planner`, `reviewer`, `researcher`, and `reporter` stay read-only.
- `memory-keeper` is the only writer in the main checkout and owns durable
  markdown updates under `research/`.
- `experiment-worker` is the only code-mutating agent and must run in an
  isolated git worktree created through `uv run scripts/opencode_worker.py create`.
- Active `experiment-worker` count must never exceed real GPU capacity.

## Secondary Native Integrations

- OpenCode remains the canonical implementation in this repo.
- Optional Claude Code-native assets live in `.claude/` plus `CLAUDE.md`.
- Optional Codex-native assets live in `.codex/`.
- Optional Pi Agent-native assets live in `.pi/`.
- These secondary integrations must follow the same local-master, HF Jobs,
  Trackio, and `research/results.tsv` workflow as OpenCode.
- Do not reintroduce hosted Autolab or Gastown-era control-plane state through
  these secondary integrations.

## Managed Runner

The default benchmark path in this repo is Hugging Face Jobs, not a local CUDA
host.

One-time bootstrap:
- `hf auth whoami`
- `hf buckets create "$AUTOLAB_HF_BUCKET" --private --exist-ok`
- `uv run scripts/hf_job.py launch --mode prepare`

Per experiment:
- `uv run scripts/hf_job.py launch --mode experiment`
- note the job id from the output
- `uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/autolab-run.log`
- `uv run scripts/parse_metric.py /tmp/autolab-run.log`
- `uv run scripts/submit_patch.py --comment "..."`

## Standard Workflow

1. Refresh from the local promoted master:
   - `uv run scripts/refresh_master.py --fetch-dag`
   - this rewrites `train.py`, `train_orig.py`, and the live local snapshots
2. Edit `train.py`.
3. Launch one managed benchmark job:
   - `uv run scripts/hf_job.py launch --mode experiment`
   - `uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/autolab-run.log`
4. Parse the result:
   - `uv run scripts/parse_metric.py /tmp/autolab-run.log`
5. Record the hypothesis and outcome in `research/notes.md`.
6. Record the run locally:
   - `uv run scripts/submit_patch.py --comment "..."`

## Parent Session Workflow

1. Refresh current local master:
   - `uv run scripts/refresh_master.py --fetch-dag`
2. Review the notebook:
   - `research/notes.md`
   - `research/do-not-repeat.md`
   - `research/campaigns/`
   - `research/experiments/`
3. Start OpenCode in the pre-training project root:
   - `uv run scripts/print_opencode_kickoff.py --gpu-slots 1`
   - `opencode`
4. Use the `autolab` primary agent to plan and review work.
5. Create isolated workers with:
   - `uv run scripts/opencode_worker.py create <experiment-id> --campaign ... --hypothesis ...`
6. Run isolated workers with:
   - `uv run scripts/opencode_worker.py run <experiment-id>`
7. Persist durable notes with `memory-keeper`, then clean up finished worktrees.

## Repo Layout

- Root benchmark files are the experiment surface.
- `program.md` is the upstream-compatible benchmark entrypoint note.
- `opencode.json` is the repo-scoped OpenCode config.
- `.opencode/agent/` contains the repo-scoped OpenCode agents.
- `.pi/` contains optional Pi Agent project settings, prompts, and agents.
- `.agents/skills/` contains repo-local shared skills.
- `research/results.tsv` is the append-only local run ledger.
- `research/live/` contains the current local promoted master and DAG.
- `research/` is the durable experiment notebook.
- `research/templates/` contains the canonical campaign, experiment, and
  do-not-repeat templates.
- `.runtime/worktrees/` is the local home for isolated experiment worktrees.

## Literature Scouting

When the task is planner or literature research rather than a timed benchmark
run:

- You may edit `research/*.md` and operator docs.
- Use the local `hf-cli` skill plus Hugging Face paper search and read tooling
  to find relevant work.
- Translate papers into single-change `train.py` hypotheses that can be tested
  cleanly.
- Record paper-derived ideas in `research/paper-ideas.md`.
- Do not claim a win or promote locally without a benchmark run.

## Local Skills

- `autolab-managed-experiment`
  Use for any single planned experiment that should become exactly one managed
  HF Jobs run.
- `autolab-hermes-delegation`
  Use when Hermes is the parent control plane and the repo should drive
  planner, reviewer, researcher, reporter, experiment-worker, and
  memory-keeper roles through explicit `delegate_task(...)` contracts.
- `autolab-reporter`
  Use for Trackio, active-job review, anomaly review, and experiment-board
  summaries.
- `hf-cli`
  Use for Hugging Face Hub CLI operations such as jobs, buckets, auth, and
  papers.

## Local Compatibility

`run-local.sh` sets `AUTOLAB_FORCE_FA3_REDIRECT=1`, and `sitecustomize.py`
redirects the Hopper FA3 kernel lookup for hosts that cannot import the default
wheel locally. Do not bake that redirect into `train.py`. Keep `run-local.sh`
as a local fallback only; do not use it as the default rig path.
