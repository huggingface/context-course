# Regularization Tuning Campaign

**Status**: Active

**Parent Master**: `765a36b0700b3a20d552f48b8ca2b75636aa3e69`

**Theme**: Systematic exploration of regularization hyperparameters to improve validation bpb.

## Experiments

### embedding-wd-001 (CANCELLED)
- **Hypothesis**: Increase embedding weight decay from 0.0005 to 0.001 to test whether stronger regularization on token embeddings improves validation bpb.
- **Change**: Embedding optimizer group `weight_decay = 0.001` (was 0.0005)
- **Result**: Job cancelled due to hanging at step 02348 (97.6%) during final evaluation phase.
- **Conclusion**: Hypothesis remains untested due to infrastructure issues.

## Notes

- The embedding weight decay experiment encountered a job hang during evaluation, not during training.
- This suggests the issue may be related to the evaluation phase or infrastructure rather than the training configuration itself.
- Consider retrying this experiment or investigating the evaluation phase bottleneck.
