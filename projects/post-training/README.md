# Post-Training Autoresearch

This project is a compact PostTrainBench-style benchmark for one small nano
chat model. It keeps the pre-training repo's small surface area, but follows
the post-training benchmark pattern: fixed base model, fixed evaluator, task
prompt, timer, free-form post-training work, and a required `final_model/`
artifact.

## Project Shape

- `prepare.py` builds deterministic nanochat-style task objects, preview JSONL
  files, and the fixed base checkpoint.
- `model.py` contains the single decoder-only nano chat architecture.
- `train.py` is a starter masked chat SFT baseline with optional reward
  training, not the only allowed method.
- `evaluate.py` loads `final_model/`, validates that it is still the fixed
  NanoChat architecture, and reports `eval_score`.
- `src/eval/tasks/nanochat/` is the PostTrainBench-style task definition:
  `benchmark.txt`, fixed `evaluate.py`, and `task_context/`.
- `scripts/create_task.py` creates an isolated task directory with `prompt.txt`,
  `timer.sh`, evaluator, model code, and starter training script.
- `.pi/` contains the Pi Agent `/posttrain` prompt and post-training role
  agents.
- `program.md` gives the default autonomous-agent task.

There is intentionally no support for multiple Hugging Face backbones. Every run
starts from the same local `NanoChat` base checkpoint, and the evaluator rejects
architecture substitutions.

## Quick Start

From this directory:

```bash
uv sync
uv run prepare.py
uv run train.py
uv run evaluate.py --model-path final_model
```

To create a PostTrainBench-style task sandbox:

```bash
uv run scripts/create_task.py --num-hours 1
```

The generated task directory contains the prompt, timer, evaluator, baseline
`train.py`, and all local code needed to produce and evaluate `final_model/`.

For a fast local smoke test:

```bash
uv run prepare.py
uv run train.py --max-steps 2 --time-budget 10 --eval-limit 8
uv run evaluate.py --model-path final_model --limit 8
```

## Hugging Face Jobs

Managed post-training runs use `scripts/hf_job.py`. The launcher renders a
self-contained `uv` job, mounts a private HF bucket at
`~/.cache/autoresearch-posttraining`, runs `prepare.py`, runs `train.py`, then
runs the fixed `evaluate.py`.

One-time setup:

```bash
hf auth whoami
hf buckets create "$POSTTRAIN_HF_BUCKET" --private --exist-ok
```

Launch an experiment:

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

Artifacts are written to `runs/<JOB_ID>/` inside the mounted bucket, including
`final_model/`, `metrics.json`, `summary.json`, `prepare.log`, `train.log`,
`evaluate.log`, and a source snapshot. Override hardware and timeout with
`--flavor` and `--timeout`, or with `POSTTRAIN_HF_FLAVOR` and
`POSTTRAIN_HF_TIMEOUT`.

## Pi Agent

The Pi-native parent flow is `/posttrain`:

```bash
cd /Users/ben/code/multiautoresearch/post-training
pi
```

Then run:

```text
/posttrain "nanochat sft improvements" 1 3
```

The prompt uses the project agents under `.pi/agents/` for planning, review,
research, HF Jobs reporting, memory updates, and a single `experiment-worker`.
For a copy-paste kickoff prompt:

```bash
uv run scripts/print_pi_kickoff.py --gpu-slots 1 --max-ideas 3
```

## Metric

`eval_score` is a ChatCORE-style mean over held-out synthetic chat tasks.
Generative tasks use exact answer extraction from completions, while the
multiple-choice task scores the next-token logits over the available letters.
Higher is better. Training and eval tasks use separate fixed seeds, and task
runs must not train on the eval split.

## Methods

The benchmark does not prescribe one post-training method. The included
`train.py` runs full-parameter masked chat SFT over a task mixture, and can run
a small nanochat-inspired policy-gradient reward phase with `--rl-steps`.
Agents or researchers can replace it with better methods, such as curriculum
SFT, synthetic data generation, rejection sampling, distillation,
optimizer/schedule changes, or other approaches, as long as the submitted
`final_model/` keeps the fixed NanoChat architecture and does not train on eval
examples.
