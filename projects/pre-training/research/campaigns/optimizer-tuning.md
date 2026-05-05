# Optimizer Tuning Campaign

**Status**: Active

**Parent Master**: `765a36b0700b3a20d552f48b8ca2b75636aa3e69`

**Theme**: Systematic exploration of optimizer hyperparameters to improve validation bpb.

## Experiments

### scalar-lr-08 (FAILED)
- **Hypothesis**: Increase SCALAR_LR from 0.7 to 0.8 to test whether faster learning of per-layer residual and initial scaling parameters improves validation bpb.
- **Change**: `SCALAR_LR = 0.8` (was 0.7)
- **Result**: val_bpb = 0.963049 (worse than master 0.962777)
- **Conclusion**: Faster learning rate for scalar parameters hurt generalization.

## Notes

- The scalar learning rate appears to be well-tuned at 0.7; increasing it degrades performance.
- Consider exploring lower SCALAR_LR values (e.g., 0.6) to test the opposite direction.
