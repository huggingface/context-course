# Post-Training Pi Coordinator

This project has a Pi-native `/posttrain` workflow for the fixed NanoChat
post-training benchmark.

Use `AGENTS.md` as the rulebook. This project is separate from
`../pre-training`; do not use the pre-training `/autolab` workflow, local
master refresh scripts, `val_bpb`, `train_orig.py`, or `submit_patch.py`.

When coordinating post-training work:

- read `docs/pi-subagents-guide.md` before planning experiments
- use project agents in `.pi/agents/` through `pi-subagents`
- use `planner` for method queues, `reviewer` for benchmark/rule checks,
  `researcher` for paper or benchmark-derived ideas, `reporter` for Hugging
  Face Jobs status, and `memory-keeper` for durable notes
- use `experiment-worker` for one coherent post-training method change
- keep active managed experiment jobs at or below the requested GPU slots
- keep the submitted architecture fixed as `NanoChat`
- never modify `evaluate.py` or train on eval examples
- run the fixed evaluator before claiming a score
- use `uv run scripts/hf_job.py launch --mode experiment` for managed runs

If the user wants a full parent-session prompt, suggest:

```text
/posttrain "nanochat sft improvements" 1 3
```
