# Hugging Face Paper Ideas

Use this file to turn literature scans into Autolab-ready hypotheses.

Rules:

- Start from the current local promoted master and refreshed DAG state.
- Propose only ideas that fit a single disciplined change in `train.py`.
- Reject ideas that are already present in the current code or already tested in
  `research/notes.md`.
- Promote only one hypothesis per experiment.

## 2026-03-27 shortlist for `au-cyy`

Context:

- target local promoted master for the next direct-master runs is
  `935fdbf9f4ae8a5ef5bcb76552acea2bc5801965` (`val_bpb = 0.962777`)
- explicitly exclude the already-low-confidence lines from recent history:
  attention temperature scaling, `SLSL`, GQA half-KV, and `has_ve()` every
  second layer
- also exclude direct repeats that already have fresh swarm evidence:
  power-law cooldown exponent `2.0` regressed on `au-fpz`, and constant Muon
  `beta2 = 0.9` already has an archived win plus a live direct-master confirm
  experiment (`au-08h`)

### 1. WSD-style short cooldown length

- Papers: `2405.18392`, `2508.01483`
- Why this is next:
  - current `WARMDOWN_RATIO = 0.825` means the run is in cooldown for 82.5% of
    the five-minute budget
  - the scaling/cooldown papers both point toward much shorter decay tails, with
    most of the gain saturating around a 10-20% cooldown rather than a nearly
    full-run anneal
- Exact `train.py` edit surface:
  - change only `WARMDOWN_RATIO`
  - leave `get_lr_multiplier()` and `FINAL_LR_FRAC` unchanged so attribution
    stays clean
- Recommended experiment title:
  - `schedule: shorten warmdown to a 20% tail on 935fdbf`

### 2. 1-sqrt cooldown shape

- Papers: `2405.18392`, `2508.01483`
- Why this is next:
  - `2405.18392` reports that a `1-sqrt` cooldown can outperform linear decay
    once the cooldown is long enough
  - this is meaningfully different from the already-losing exponent-2 power-law
    trial because it changes the late-phase curvature without introducing an
    extra exponent hyperparameter
- Exact `train.py` edit surface:
  - change only the cooldown branch inside `get_lr_multiplier()`
  - keep `WARMDOWN_RATIO` and `FINAL_LR_FRAC` fixed for the first experiment
- Recommended experiment title:
  - `schedule: replace linear warmdown with 1-sqrt cooldown on 935fdbf`

### 3. Cooldown-only Muon `beta2` ramp

- Papers: `2508.01483`, `2601.14603`
- Why this is next:
  - `2508.01483` reports consistent gains from higher `beta2` during cooldown
  - `2601.14603` motivates variance-adaptive Muon extensions rather than
    treating `beta2` as a fixed always-on toggle
  - this avoids spending another experiment on the already-known constant
    `beta2 = 0.9` rerun and instead isolates whether the gain is specifically a
    late-phase variance-control effect
- Exact `train.py` edit surface:
  - add a `get_muon_beta2(progress)` helper next to
    `get_lr_multiplier()/get_muon_momentum()/get_weight_decay()`
  - in the training-loop param-group update, set `group["beta2"]` only for
    Muon groups while leaving matrix LR, momentum, and weight decay schedules
    unchanged
- Recommended experiment title:
  - `optimizer: ramp Muon beta2 during cooldown on 935fdbf`

## Current Paper-Derived Candidates

### Selective attention temperature

- Paper: `2411.12892` "Selective Attention: Enhancing Transformer through
  Principled Context Control"
- Why it matches this repo:
  - `train.py` already normalizes `q` and `k`, so the clean insertion point is
    the attention logit scale after QK normalization.
  - The model already uses lightweight value gating, so query-temperature or
    value-temperature extensions are architecturally compatible.
- Smallest credible experiments:
  - add one scalar attention-temperature multiplier to the attention logits
  - add one learned per-layer or per-head inverse-temperature initialized at
    `1.0`
- Keep it single-change:
  - do not combine query-temperature and value-temperature in the same run
  - do not change the window pattern in the same experiment
- Main risk:
  - over-sharpening attention may hurt sliding-window layers

### Power-law cooldown schedule

- Paper: `2408.13359` "Power Scheduler: A Batch Size and Token Number Agnostic
  Learning Rate Scheduler"
- Related cooldown analysis: `2508.01483` "Training Dynamics of the Cooldown
  Stage in Warmup-Stable-Decay Learning Rate Scheduler"
- Why it matches this repo:
  - the current schedule is a simple linear warmdown controlled by
    `WARMDOWN_RATIO` and `FINAL_LR_FRAC`
  - scheduler shape is isolated in `get_lr_multiplier`, so this is a clean
    one-function change
- Smallest credible experiments:
  - replace linear cooldown with a power-law cooldown using one new exponent
    hyperparameter
  - keep the same `FINAL_LR_FRAC` and only vary the cooldown curve shape
- Main risk:
  - changing both the cooldown shape and floor at once would make attribution
    poor

### Cooldown-stage variants

- Papers:
  - `2502.15938` "Straight to Zero: Why Linearly Decaying the Learning Rate to Zero Works Best for LLMs"
  - `2508.01483` "Training Dynamics of the Cooldown Stage in Warmup-Stable-Decay Learning Rate Scheduler"
  - `2410.05192` "Understanding Warmup-Stable-Decay Learning Rates: A River Valley Loss Landscape Perspective"
- Why they match this repo:
  - the scheduler is still concentrated in `get_lr_multiplier()` plus two scalar
    constants, so each cooldown-stage test can remain a one-function or
    one-constant change in `train.py`
  - these papers distinguish the floor choice, cooldown duration, and cooldown
    curve, which maps directly onto `FINAL_LR_FRAC`, `WARMDOWN_RATIO`, and the
    interpolation logic here
- Smallest credible experiments:
  - set only `FINAL_LR_FRAC = 0.0` to test a straight-to-zero tail
  - set only `WARMDOWN_RATIO = 0.90` to lengthen the cooldown phase
  - replace only the linear cooldown interpolation with a cosine interpolation
    while keeping the same floor and cooldown duration
- Keep it single-change:
  - do not combine a zero floor with a new cooldown shape in the same experiment
  - do not move both `WARMDOWN_RATIO` and `FINAL_LR_FRAC` together
- Main risk:
  - scheduler-only gains can be easy to overfit with multiple adjacent sweeps, so
    stagger these across separate experiments instead of treating them as a bundle

### Gradient-preserving activation scaling

- Paper: `2506.22049` "GPAS: Accelerating Convergence of LLM Pretraining via
  Gradient-Preserving Activation Scaling"
- Why it matches this repo:
  - the model is Pre-LN/RMSNorm and already has explicit residual mixing
    parameters, so residual-path balance is clearly part of the design space
  - GPAS can be tested as a local block-output scaling change without touching
    `prepare.py`
- Smallest credible experiments:
  - add one fixed or learned GPAS-style scale on block outputs while preserving
    gradients with a stop-gradient trick
  - apply it to either the attention output or the MLP output, not both
- Main risk:
  - this is a larger code change than an LR tweak, so isolate it aggressively

### Muon variance adaptation follow-ups

- Papers:
  - `2510.05491` "NorMuon: Making Muon more efficient and scalable"
  - `2601.14603` "Variance-Adaptive Muon: Accelerating LLM Pretraining with
    NSR-Modulated and Variance-Scaled Momentum"
- Why it matches this repo:
  - `train.py` already contains NorMuon-style row/column variance normalization
    in `muon_step_fused`
  - the current Muon groups still default `beta2=0.0`, so the second-moment path
    is underused by default
- Smallest credible experiments:
  - enable a non-zero Muon `beta2`
  - change only the variance statistic or normalization axis, not both
- Main risk:
  - treat this as a follow-up to the current optimizer, not a brand-new
    direction

## Low-Priority Ideas

- `2311.00684` attention alignment for long-context extrapolation:
  interesting but less aligned with the fixed short-budget Autolab benchmark.
- Structured FFN or architecture-replacement papers:
  too invasive for disciplined one-change comparisons here.

## Additional Ranked Candidates

### Local-global window interleave

- Paper: `2408.00118`
- Why it matches this repo:
  - `WINDOW_PATTERN` is already an explicit layerwise attention-pattern knob
  - switching from `SSSL` to `SLSL` is a one-string architectural test, not a
    subsystem rewrite
- Smallest credible experiment:
  - change only `WINDOW_PATTERN` from `"SSSL"` to `"SLSL"`
- Main risk:
  - a denser global pattern may buy quality at the cost of throughput or memory

### Grouped-query attention

- Paper: `2305.13245`
- Why it matches this repo:
  - attention already supports `n_kv_head <= n_head`
  - the current builder still ties `n_kv_head = num_heads`, so halving KV heads
    is a clean existing-capability toggle
- Smallest credible experiment:
  - set `n_kv_head = num_heads // 2`
- Main risk:
  - this changes parameter count and attention cache structure, so compare it
    carefully against optimizer-only wins

### Denser value-embedding cadence

- Paper: `2410.17897`
- Why it matches this repo:
  - the model already has explicit value-embedding placement and gating logic
  - recent wins suggest this subsystem is live rather than decorative
- Smallest credible experiment:
  - change `has_ve()` cadence from every third layer to every second layer
- Main risk:
  - this is adjacent to the current value-embedding regularization line, so keep
    it isolated from any weight-decay changes

### Attention branch scale reset

- Paper: `2305.02790`
- Why it matches this repo:
  - the block already hardcodes a non-residual attention amplification
  - testing `1.0` versus `1.3` is a scalar-only branch-balance experiment
- Smallest credible experiment:
  - change the attention branch scale from `1.3` to `1.0`
- Main risk:
  - the current scale may already be compensating for another architectural
    choice, so this can regress sharply
