# Autolab Notes

## Repo layout

- Seed hub snapshots live in `research/reference/`.
- Live hub refreshes should be written to `research/live/`.
- Archived local experiment diffs live in `research/diffs/`.

## Local environment

- GPU: NVIDIA H100 80GB HBM3 (GPU 0)
- Local host GLIBC is 2.31, so the Hopper-only `varunneal/flash-attention-3` wheel does not import here.
- Local runs use `sitecustomize.py` plus `run-local.sh` to redirect that kernel lookup to `kernels-community/flash-attn3` without editing `train.py`.

## Baseline

- Master hash: `765a36b0700b3a20d552f48b8ca2b75636aa3e69`
- Hub master val_bpb: `0.962777`
- Local baseline val_bpb under compatibility redirect: `0.962846`
- Local baseline peak_vram_mb: `33609.3`
- Local baseline mfu_percent: `43.84`
- Local baseline total_tokens_M: `304.5`
- Local baseline num_steps: `2323`

## Experiment: batch96

Hypothesis:
- Increase microbatch and total batch together to exploit large VRAM headroom while keeping `grad_accum_steps=1`.

Change:
- `DEVICE_BATCH_SIZE = 96`
- `TOTAL_BATCH_SIZE = 96 * 2048`

Observed early behavior:
- Peak memory around 50 GB, so it fits.
- Steady-state tok/sec stayed roughly flat around 1.02M to 1.04M instead of increasing materially.
- Training steps over the 300-second budget dropped substantially relative to baseline.

Conclusion:
- This looks weak. It spent much more memory for little or no throughput gain and likely sacrifices update count.
- Keep the diff in `research/diffs/batch96.diff` for reference, but do not treat it as a leading candidate.

## Experiment: flr021

Hypothesis:
- Lower the final LR floor from `0.025` to `0.021`.
- Post-master hub history showed `FINAL_LR_FRAC=0.021` as the strongest near-miss after current master.

Change:
- `FINAL_LR_FRAC = 0.021`

Result:
- Local val_bpb: `0.962717`
- Local training_seconds: `300.1`
- Local total_seconds: `383.7`
- Local peak_vram_mb: `33612.7`
- Local mfu_percent: `43.88`
- Local total_tokens_M: `304.7`
- Local num_steps: `2325`

Conclusion:
- This beat both the local baseline (`0.962846`) and the current hub master (`0.962777`).
- Submitted as patch `14808` against master `765a36b0700b3a20d552f48b8ca2b75636aa3e69`.
- Workspace `train.py` was reset back to master after submission so the next experiment starts clean.

## Experiment: au-41x lm_head_wd_003

Hypothesis:
- Increase only the `lm_head` AdamW weight decay from `0.002` to `0.003`.
- Slightly stronger output-layer regularization may improve validation bpb without perturbing the other optimizer groups.

Change:
- `lm_head` optimizer group `weight_decay = 0.003`

Managed H200 result:
- Master hash: `765a36b0700b3a20d552f48b8ca2b75636aa3e69`
- HF Job: `69c5a34525abd6f920b4fea3`
- val_bpb: `0.961175`
- training_seconds: `300.0`
- total_seconds: `430.2`
- peak_vram_mb: `33609.6`
- mfu_percent: `45.18`
- total_tokens_M: `313.7`
- num_steps: `2393`

Conclusion:
- This beats the current hub master (`0.962777`) by `0.001602`.
- Submitted as patch `14810`.

## Experiment: scalar-lr-08

Hypothesis:
- Increase SCALAR_LR from 0.7 to 0.8 to test whether faster learning of per-layer residual and initial scaling parameters improves validation bpb.

Change:
- `SCALAR_LR = 0.8` (was 0.7)

Managed H200 result:
- Master hash: `765a36b0700b3a20d552f48b8ca2b75636aa3e69`
- HF Job: `69cbe00334fa24114ddf47a6`
- Campaign: `optimizer-tuning`
- val_bpb: `0.963049`
- training_seconds: `300.1`
- total_seconds: `433.0`
- peak_vram_mb: `33609.6`
- mfu_percent: `44.82`
- total_tokens_M: `311.3`
- num_steps: `2375`

Conclusion:
- FAILED. Increasing SCALAR_LR degraded validation bpb by +0.000272 compared to master (0.962777).
- The faster learning rate for scalar parameters hurt generalization.

## Experiment: embedding-wd-001

Hypothesis:
- Increase embedding weight decay from 0.0005 to 0.001 to test whether stronger regularization on token embeddings improves validation bpb.

Change:
- Embedding optimizer group `weight_decay = 0.001` (was 0.0005)

Managed H200 result:
- Master hash: `765a36b0700b3a20d552f48b8ca2b75636aa3e69`
- HF Job: `69cbdff7942f980bf425a3d0`
- Campaign: `regularization-tuning`
- Status: `CANCELLED` (STUCK)
- Job got stuck at step 02348 (97.6%) during final evaluation phase for 10+ minutes.

Conclusion:
- CANCELLED due to job hanging during evaluation. No val_bpb result obtained.
- The hypothesis remains untested; may need to retry with different infrastructure or debugging.

## Experiment: unembedding-lr-015

Hypothesis:
- Increase UNEMBEDDING_LR from 0.01 to 0.015 to test whether a higher learning rate for the output layer improves validation bpb.

Change:
- `UNEMBEDDING_LR = 0.015` (was 0.01)

Managed H200 result:
- Master hash: `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`
- HF Job: `69cc18d8942f980bf425a641`
- Campaign: `optimizer-tuning`
- val_bpb: `0.970805`
- training_seconds: `300.1`
- total_seconds: `431.5`
- peak_vram_mb: `33609.6`
- mfu_percent: `44.14`
- total_tokens_M: `306.6`
- num_steps: `2339`

Conclusion:
- FAILED. Increasing UNEMBEDDING_LR degraded validation bpb by +0.008028 compared to master (0.962777).
- Higher learning rate for the output layer significantly hurt generalization.

## Experiment: warmdown-075

Hypothesis:
- Decrease WARMDOWN_RATIO from 0.825 to 0.75 to allow more time at higher learning rates before the final LR floor.

Change:
- `WARMDOWN_RATIO = 0.75` (was 0.825)

Managed H200 result:
- Master hash: `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965`
- HF Job: `69cc194534fa24114ddf48bd`
- Campaign: `schedule-tuning`
- val_bpb: `0.962980`
- training_seconds: `300.1`
- total_seconds: `431.5`
- peak_vram_mb: `33609.6`
- mfu_percent: `43.88`
- total_tokens_M: `304.7`
- num_steps: `2325`

Conclusion:
- FAILED. Decreasing WARMDOWN_RATIO degraded validation bpb by +0.000203 compared to master (0.962777).
- Shorter warmdown phase slightly hurt final convergence.
