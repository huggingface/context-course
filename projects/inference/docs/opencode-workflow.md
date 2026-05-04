# OpenCode Workflow

OpenCode is the lightweight control plane for this inference project.

The target surface is local llama.cpp inference:

- `llama-server` is the preferred runtime.
- The benchmark endpoint is OpenAI-compatible chat completions.
- `.agents/skills/huggingface-local-models/` defines the GGUF discovery and
  launch workflow.
- `research/results.tsv` is the append-only local benchmark ledger.

## Setup

Install project tooling:

```bash
uv sync
```

Install or confirm llama.cpp:

```bash
llama-server --version
llama-cli --version
```

On macOS, Homebrew is the simplest path:

```bash
brew install llama.cpp
```

Authenticate if the target model is gated:

```bash
hf auth login
```

## Parent Session Workflow

1. Inspect local hardware and tools:

```bash
uv run scripts/inspect_llama_toolchain.py
```

2. Resolve a target GGUF:

```bash
uv run scripts/resolve_hf_gguf.py --repo <owner/repo> --quant Q4_K_M
```

3. Start OpenCode in `inference/`:

```bash
opencode
```

4. Use the `inference-lab` primary agent.

Delegate to:

- `optimizer` for the next one-variable speed candidate
- `benchmarker` for baseline and candidate measurements

## Benchmarking

Benchmark an existing endpoint:

```bash
uv run scripts/benchmark_llama.py \
  --base-url http://127.0.0.1:8080/v1 \
  --runs 3 \
  --append-tsv research/results.tsv
```

Launch a server for one benchmark and stop it afterward:

```bash
uv run scripts/benchmark_llama.py \
  --server-cmd "llama-server --hf-repo <owner/repo> --hf-file <file.gguf> -c 4096 --port 8080" \
  --base-url http://127.0.0.1:8080/v1 \
  --runs 3 \
  --append-tsv research/results.tsv
```

Use `--output-json .runtime/results/<experiment-id>.json` when you want a full
record for later analysis.

## Comparability

Only compare speed numbers directly when these are unchanged:

- model repo and exact GGUF file
- quant
- context
- prompt
- `max_tokens`
- llama.cpp build/backend
- server command except for the one variable being tested

When changing model or quant, record it as a throughput/quality tradeoff.
