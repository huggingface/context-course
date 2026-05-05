# Autolab Do-Not-Repeat Ledger

Use this ledger to keep failed or stale ideas searchable.

## Duplicate Rule

Treat two experiments as duplicates if they share:

- the same parent master hash
- the same subsystem or change class
- the same hypothesis in materially similar form

## Known Regressions

### Throughput / Batching

- Master `765a36b0700b3a20d552f48b8ca2b75636aa3e69`: increasing both
  `DEVICE_BATCH_SIZE` and `TOTAL_BATCH_SIZE` to a 96-token microbatch fit in
  memory but did not materially improve tok/sec and likely lost too many update
  steps inside the 300-second budget.

### Optimizer Tuning

- Master `765a36b0700b3a20d552f48b8ca2b75636aa3e69`: increasing `SCALAR_LR`
  from 0.7 to 0.8 degraded validation bpb by +0.000272 (0.963049 vs 0.962777).
  Faster learning of per-layer residual and initial scaling parameters hurt
  generalization.

### Regularization Tuning

- Master `765a36b0700b3a20d552f48b8ca2b75636aa3e69`: increasing embedding weight
  decay from 0.0005 to 0.001 caused the job to hang at step 02348 (97.6%) during
  final evaluation. The hypothesis remains untested due to infrastructure issues.

### Optimizer Tuning (continued)

- Master `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`: increasing `UNEMBEDDING_LR`
  from 0.01 to 0.015 degraded validation bpb by +0.008028 (0.970805 vs 0.962777).
  Higher learning rate for the output layer significantly hurt generalization.

### Schedule Tuning

- Master `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`: decreasing `WARMDOWN_RATIO`
  from 0.825 to 0.75 degraded validation bpb by +0.000203 (0.962980 vs 0.962777).
  Shorter warmdown phase slightly hurt final convergence.

## Stale-Master Notes

- If master changes materially after planning but before a worker runs or
  submits, stop and replan instead of improvising on stale context.
