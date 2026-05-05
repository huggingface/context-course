---
description: Start a Pi-native NanoChat post-training parent session.
argument-hint: "[campaign] [gpu-slots] [max-ideas]"
---

You are coordinating NanoChat post-training experiments in this project using
Pi and `pi-subagents`.

Arguments:

- campaign: `$1` if provided, otherwise `nanochat post-training improvements`
- gpu slots: `$2` if provided, otherwise `1`
- max ideas: `$3` if provided, otherwise `3`

Read:

- `AGENTS.md`
- `README.md`
- `program.md`
- `docs/pi-subagents-guide.md`
- `research/notes.md`
- `research/results.tsv`
- `train.py`
- `prepare.py`
- `evaluate.py`
- `model.py`
- `scripts/hf_job.py`

Use Pi project agents:

- `planner` for up to the requested max ideas for the requested campaign
- `reviewer` for read-only rule and comparability checks
- `researcher` for paper, nanochat, or PostTrainBench-derived hypotheses
- `reporter` for Hugging Face Jobs status and logs
- `memory-keeper` for durable notes in this checkout
- `experiment-worker` for one coherent post-training method change

Reject ideas that modify `evaluate.py`, alter the submitted `NanoChat`
architecture, train on eval examples, or mix unrelated method changes.

Do not allow more active managed experiment jobs than the requested GPU slots.
For implementation work, ask `experiment-worker` to make one coherent change,
run a local smoke test, then launch the managed Hugging Face Jobs benchmark if
the smoke test passes.

Keep experiments comparable:

- work from this `post-training` project root, not `../pre-training`
- prefer editing `train.py` only unless a small supporting file is justified
- keep `model.py` architecture-compatible with the fixed evaluator
- do not modify `evaluate.py` or `src/eval/tasks/*/evaluate.py`
- do not train on eval examples
- save the best checkpoint to `final_model/`
- run the fixed evaluator before reporting a score
- persist managed results under the mounted `POSTTRAIN_HF_BUCKET`
- update `research/notes.md` and `research/results.tsv` after completed runs

Suggested managed commands:

```bash
uv run scripts/hf_job.py launch --mode experiment
uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/posttrain-run.log
```
