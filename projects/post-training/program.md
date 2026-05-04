# Program

We want to post-train the local `NanoChat` base model to maximize held-out
`eval_score`.

The fixed benchmark files are:

- `prepare.py`
- `evaluate.py`
- `model.py`

The starter experiment file is:

- `train.py`

Start with:

```bash
uv run prepare.py
```

Then improve the post-training method in `train.py`, or create additional
supporting files. Prefer nanochat-style methods: chat task mixtures, masked
assistant-token SFT, task-specific eval loops, rejection sampling, curriculum
SFT, distillation, or lightweight reward training over generated completions.
You may change data mixing, schedules, optimization, loss shaping, or other
training strategy details, but keep the benchmark honest:

- do not train on the eval split
- do not modify `evaluate.py`
- do not modify generated eval records
- do not substitute another architecture
- save the best checkpoint to `final_model/`

Always finish with:

```bash
uv run evaluate.py --model-path final_model
```

For managed cloud runs, use the post-training HF Jobs launcher:

```bash
uv run scripts/hf_job.py launch --mode experiment
uv run scripts/hf_job.py logs <JOB_ID> --follow --output /tmp/posttrain-run.log
```

The job persists `final_model/`, metrics, logs, and the source snapshot under
`runs/<JOB_ID>/` in the mounted `POSTTRAIN_HF_BUCKET`.

For Pi Agent orchestration, start Pi in this project root and run:

```text
/posttrain "nanochat sft improvements" 1 3
```

The Pi flow is project-local and should not use the pre-training `/autolab`
workflow.

To mirror the PostTrainBench workflow more closely, create a sandbox first:

```bash
uv run scripts/create_task.py --num-hours 1
```

Read the generated `prompt.txt`, work inside that directory, and finish by
running its copied `evaluate.py`.
