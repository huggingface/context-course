# Agent Instructions

This is the llama.cpp inference optimization project. It is separate from
`../pre-training` and `../post-training`.

## Goal

Get a local GGUF model running through llama.cpp as fast as possible while
keeping benchmark comparisons reproducible.

## Rules

- Run project commands from `inference/`.
- Do not modify files under `../pre-training` or `../post-training`.
- Use the local `huggingface-local-models` skill in
  `.agents/skills/huggingface-local-models/SKILL.md` for model discovery,
  GGUF file selection, quant choice, and llama.cpp launch commands.
- Prefer `llama-server` and its OpenAI-compatible endpoint for benchmarks.
  Use `llama-cli` only for terminal-only checks.
- Confirm a model repo actually exposes `.gguf` files before calling it
  llama.cpp-runnable.
- Prefer exact `--hf-repo` plus `--hf-file` commands when the GGUF filename is
  known.
- Change one speed variable at a time unless the task explicitly asks for a
  sweep.
- Benchmark before claiming a speedup. Compare runs only when model, quant,
  prompt, `max_tokens`, context, and toolchain are controlled.
- Record completed benchmark results in `research/results.tsv`.
- Keep downloaded model weights, logs, and transient server state out of git.

## Agents

- `inference-lab`
  Primary coordinator for local inference optimization.
- `optimizer`
  Proposes the next narrow llama.cpp speed change from hardware, model, and
  benchmark evidence.
- `benchmarker`
  Runs repeatable local endpoint benchmarks, records metrics, and reports
  regressions or measurement issues.

## Native Integrations

- OpenCode assets live in `.opencode/agent/`.
- Claude Code assets live in `CLAUDE.md` and `.claude/`.
- Codex assets live in `.codex/`.
- Pi assets live in `.pi/`.

All integrations use the same local skill, scripts, and result ledger. Do not
create integration-specific benchmark ledgers.

## Standard Workflow

1. Inspect the local toolchain:
   - `uv run scripts/inspect_llama_toolchain.py`
2. Resolve an exact GGUF file for the target model:
   - `uv run scripts/resolve_hf_gguf.py --repo <owner/repo> --quant Q4_K_M`
3. Start or benchmark a `llama-server` command:
   - `uv run scripts/benchmark_llama.py --server-cmd "<llama-server command>" --append-tsv research/results.tsv`
4. Ask `optimizer` for one next speed change.
5. Ask `benchmarker` to run the same benchmark with that change.
6. Keep the fastest reproducible command and note any quality or latency
   tradeoff.

## Speed Variables

Prefer this order unless current evidence says otherwise:

- quant and GGUF file
- context length
- GPU offload layers or backend-specific acceleration
- thread count and CPU placement
- batch and ubatch size
- flash attention or cache type
- parallel slots and server concurrency

Do not hide a lower-quality model or shorter generation behind a faster
tokens/sec number. Record those changes explicitly.
