# Pi Subagents Guide

This guide describes the Pi-native `/posttrain` workflow for the NanoChat
post-training project. It is separate from the pre-training `/autolab` flow.

## Checked-In Pi Assets

- `.pi/settings.json`
  Project Pi settings. It declares `pi-subagents` and keeps Pi session files
  under `.runtime/`.
- `.pi/APPEND_SYSTEM.md`
  Parent-session coordinator guidance appended to Pi's default prompt.
- `.pi/agents/`
  Project agents: `planner`, `reviewer`, `researcher`, `reporter`,
  `memory-keeper`, and `experiment-worker`.
- `.pi/prompts/posttrain.md`
  The reusable `/posttrain` parent-session kickoff prompt.
- `scripts/print_pi_kickoff.py`
  Prints a copy-paste parent-session prompt.

## Setup

Install Pi once if it is not already available:

```bash
npm install -g @mariozechner/pi-coding-agent
```

From the post-training project root, start Pi:

```bash
cd /Users/ben/code/multiautoresearch/post-training
pi
```

The project `.pi/settings.json` declares `npm:pi-subagents@0.22.0`. Pi should
install missing project packages on startup. If needed:

```bash
pi install npm:pi-subagents@0.22.0 -l
```

For managed Hugging Face Jobs runs:

```bash
hf auth whoami
export POSTTRAIN_HF_BUCKET=<your-private-hf-bucket>
hf buckets create "$POSTTRAIN_HF_BUCKET" --private --exist-ok
```

## Parent Session

Start Pi in the post-training project root and run:

```text
/posttrain "nanochat sft improvements" 1 3
```

Arguments are:

- campaign name
- maximum concurrent managed jobs
- maximum ideas to request from the planner

The parent session should use:

- `planner` for fresh method queues
- `reviewer` for rule and benchmark-integrity checks
- `researcher` for external post-training ideas
- `reporter` for HF Jobs status and logs
- `memory-keeper` for durable updates
- `experiment-worker` for one coherent implementation and benchmark run

## Useful Pi Commands

```text
/run planner "Propose up to 3 fresh post-training experiments for NanoChat."
/run reviewer "Review the current proposed change for benchmark integrity."
/parallel reporter "Summarize active post-training HF Jobs." -> reviewer "Check whether the completed run has enough evidence."
/run memory-keeper "Record this completed run in research/notes.md and research/results.tsv."
```

## Managed Runner

The canonical managed benchmark path is:

```bash
uv run scripts/hf_job.py launch --mode experiment
uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/posttrain-run.log
```

For a cheap managed smoke run:

```bash
uv run scripts/hf_job.py launch --mode experiment \
  --train-args "--max-steps 2 --time-budget 20 --batch-size 4 --eval-limit 8 --final-eval-limit 8" \
  --eval-args "--limit 8"
```

Artifacts are written under `runs/<JOB_ID>/` in the mounted
`POSTTRAIN_HF_BUCKET`, including `final_model/`, `metrics.json`,
`summary.json`, and logs.

## Durable State

Use the repo-local notebook and ledger:

- `research/notes.md`
- `research/results.tsv`

Do not create pre-training-style `val_bpb` records here. The primary metric is
`eval_score`, with `raw_accuracy` as supporting context.
