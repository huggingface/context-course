---
name: autolab-hermes-delegation
description: "Use Hermes delegate_task cleanly in this repo for planner, reviewer, researcher, reporter, experiment-worker, and memory-keeper roles."
version: 1.0.0
metadata:
  hermes:
    category: autolab
    requires_toolsets: [delegation, file]
---

Use this when Hermes is the parent control plane for this repo.

Hermes children get a fresh context, cannot ask the user for clarification, cannot delegate again, and only return their final summary to the parent. Pass the full role contract in every `delegate_task(...)` call.

## Parent Rules

- Keep `AGENTS.md` as the only checked-in rulebook. Do not add `.hermes.md`.
- Launch the parent with toolsets: `terminal,file,web,skills,delegation,clarify`
- Leave Hermes `memory` out of the default toolsets so repo markdown stays the durable record.
- Keep Hermes child concurrency at `min(gpu_slots, 3)` per parent session.
- If you need more than 3 parallel workers, use multiple top-level Hermes sessions or stay on OpenCode.

## Role Defaults

- `planner`
  - toolsets: `["file"]`
  - focus: fresh, non-duplicate single-change ideas only
- `reviewer`
  - toolsets: `["file"]`
  - focus: hard-rule checks, stale-master risk, duplicates, multi-change patches
- `researcher`
  - toolsets: `["web", "file", "skills", "terminal"]`
  - focus: paper-derived single-change hypotheses only
- `reporter`
  - toolsets: `["terminal", "file", "skills"]`
  - focus: HF Jobs and Trackio status, duplicate active jobs, anomalies
- `memory-keeper`
  - toolsets: `["file"]`
  - focus: durable markdown updates in the main checkout only
- `experiment-worker`
  - toolsets: `["terminal", "file", "skills"]`
  - focus: one isolated worktree, one hypothesis, one managed benchmark run

## Planner Template

```python
delegate_task(
    goal="Propose up to 3 fresh Autolab experiments against the current local promoted master.",
    context="""Read AGENTS.md, README.md, research/notes.md, research/do-not-repeat.md,
research/campaigns/, research/experiments/, research/results.tsv, research/live/master.json,
and research/live/dag.json.

Return a ranked queue of 1-3 fresh experiments. Each must include:
- short title
- one-sentence hypothesis
- parent master hash
- exact single variable being changed
- expected upside
- reason it is not a duplicate

Do not run commands that mutate the repo. Do not propose multi-change ideas.""",
    toolsets=["file"],
    max_iterations=20,
)
```

## Reviewer Template

```python
delegate_task(
    goal="Review this Autolab plan or result for rule violations and comparability risk.",
    context="""Read AGENTS.md and the provided experiment details.

Prioritize:
- hard-rule violations
- stale-master risk
- duplicate experiments
- multi-change patches
- missing benchmark evidence
- incorrect submit or no-submit decisions

Return concise findings with exact file or evidence references.""",
    toolsets=["file"],
    max_iterations=20,
)
```

## Researcher Template

```python
delegate_task(
    goal="Find up to 3 paper-derived single-change Autolab ideas that map cleanly to train.py.",
    context="""Read AGENTS.md, research/notes.md, research/do-not-repeat.md,
research/paper-ideas.md, research/results.tsv, research/live/master.json, and research/live/dag.json.

Use the repo's Hugging Face skills when useful. Reject ideas already present in code or already ruled out.
Return the smallest credible change to test for each idea and the main risk if it fails.""",
    toolsets=["web", "file", "skills", "terminal"],
    max_iterations=30,
)
```

## Reporter Template

```python
delegate_task(
    goal="Summarize current Autolab fleet status and call out duplicate or stale active jobs.",
    context="""Use the repo reporter workflow:
- . ~/.autolab/credentials
- uv run scripts/trackio_reporter.py summary --max-jobs 25
- uv run scripts/trackio_reporter.py sync --project ${AUTOLAB_TRACKIO_PROJECT:-autolab} when needed

Treat Trackio plus HF Jobs metadata as the source of truth.
Do not edit repo markdown or code.""",
    toolsets=["terminal", "file", "skills"],
    max_iterations=25,
)
```

## Experiment Worker Flow

1. Create the reserved state:
   - `uv run scripts/hermes_worker.py create <experiment-id> --campaign ... --hypothesis ...`
2. Print the delegate payload:
   - `uv run scripts/hermes_worker.py delegate <experiment-id>`
3. Paste the emitted `delegate_task(...)` block into the parent session.
4. The child must:
   - `cd` into the reserved worktree
   - export `AUTOLAB_CAMPAIGN`, `AUTOLAB_EXPERIMENT_ID`, `AUTOLAB_WORKER_ID`, `AUTOLAB_HYPOTHESIS`, `AUTOLAB_LOG_PATH`, and `AUTOLAB_EXPERIMENT_NOTE`
   - refresh local master
   - edit `train.py` only
   - run one managed experiment
   - parse the metric
   - run `submit_patch.py`

## Memory-Keeper Template

```python
delegate_task(
    goal="Update the durable Autolab markdown after a worker completed.",
    context="""Read AGENTS.md plus research/notes.md, research/do-not-repeat.md,
research/campaigns/, research/experiments/, and the worker's final summary.

Update only the durable markdown in the main checkout.
Preserve:
- hypothesis tested
- parent master hash
- local val_bpb or failure state
- submit decision
- one short interpretation""",
    toolsets=["file"],
    max_iterations=25,
)
```
