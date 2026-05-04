# NanoChat Task Context

The task uses one fixed local base model: `NanoChat`.

Useful files in a generated task directory:

- `model.py` defines the only allowed architecture.
- `prepare.py` creates the fixed train/eval data and base checkpoint.
- `train.py` is a starter nanochat-style masked SFT baseline with optional
  reward training. You may replace or extend it.
- `evaluate.py` is the fixed benchmark evaluator. It scores generative tasks by
  task-specific answer extraction and scores multiple-choice tasks from
  next-token logits over the available letters. Do not modify it.
- `timer.sh` prints the remaining task budget.

The best model must be saved as `final_model/config.json` and
`final_model/model.pt`. The evaluator rejects architecture substitutions.
