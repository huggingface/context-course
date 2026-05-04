# Program

Optimize local llama.cpp inference for speed.

The benchmark target is a GGUF model served through `llama-server`. Use the
local `huggingface-local-models` skill to find llama.cpp-compatible repos,
choose a quant, confirm exact `.gguf` filenames, and build portable
`--hf-repo` / `--hf-file` commands.

Start with:

```bash
uv run scripts/inspect_llama_toolchain.py
uv run scripts/resolve_hf_gguf.py --repo <owner/repo> --quant Q4_K_M
```

Then benchmark:

```bash
uv run scripts/benchmark_llama.py \
  --server-cmd "llama-server --hf-repo <owner/repo> --hf-file <file.gguf> -c 4096 --port 8080" \
  --append-tsv research/results.tsv
```

Improve one variable at a time: quant, context, backend acceleration, thread
count, GPU offload, batch sizing, cache type, or server concurrency. Do not
claim a speedup until the same benchmark has been run before and after the
change.
