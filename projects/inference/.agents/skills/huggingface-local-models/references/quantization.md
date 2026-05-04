# GGUF Quantization Guide

## Hub-first quant selection

Before using generic tables, open the model repo with:

```text
https://huggingface.co/<repo>?local-app=llama.cpp
```

Prefer the exact quant labels and sizes shown in the `Hardware compatibility`
section of the fetched `?local-app=llama.cpp` page text or HTML. Then confirm
the matching filenames in:

```text
https://huggingface.co/api/models/<repo>/tree/main?recursive=true
```

Use the Hub page first, and only fall back to generic heuristics when the repo
page does not expose a clear recommendation.

## Format Comparison

| Format | Size tendency | Speed tendency | Notes |
|--------|---------------|----------------|-------|
| FP16 | largest | slowest | original quality |
| Q8_0 | large | slower | nearly lossless |
| Q6_K | medium-large | medium | strong quality/size choice |
| Q5_K_M | medium | medium-fast | useful for code and technical workloads |
| Q4_K_M | smaller | fast | default balance |
| Q4_K_S | smaller | faster | lower quality than Q4_K_M |
| Q3_K_M | small | faster | acceptable only when memory constrained |
| Q2_K | smallest | fastest | usually too much quality loss |

Default to `Q4_K_M` unless the repo page or hardware profile suggests
otherwise. For code and technical workloads, prefer `Q5_K_M` or `Q6_K` when
memory allows.

## Conversion

Convert only when the repo does not already expose GGUF files.

```bash
hf download <repo-without-gguf> --local-dir ./model-src
python convert_hf_to_gguf.py ./model-src \
  --outfile model-f16.gguf \
  --outtype f16
llama-quantize model-f16.gguf model-q4_k_m.gguf Q4_K_M
```

## Troubleshooting

- Out of memory: use a smaller quant, lower context, or offload fewer layers.
- Slow inference: try lower precision, backend acceleration, lower context, or
  tuned thread/batch settings.
- Gibberish output: try a less aggressive quant and verify the GGUF was built
  correctly.
