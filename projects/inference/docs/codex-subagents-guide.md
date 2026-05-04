# Codex Subagents Guide

This guide describes the Codex-native inference setup.

Codex can run locally from the terminal, inspect and edit files, and run
commands in the selected directory. Keep Codex sessions rooted in `inference/`
so project-local configuration, scripts, and result paths resolve correctly.

## Checked-In Codex Assets

- `.codex/config.toml`
  Project-scoped Codex agent registry.
- `.codex/agents/inference-lab.toml`
  Parent coordinator.
- `.codex/agents/optimizer.toml`
  Read-only speed optimizer.
- `.codex/agents/benchmarker.toml`
  Local endpoint benchmarker.

## Recommended Start

Start Codex from `inference/` and let the main session use the checked-in
subagents:

```bash
codex
```

For a longer prompt skeleton:

```bash
python3 scripts/print_codex_kickoff.py
```

## Workflow

1. Read `AGENTS.md`, `README.md`, and this guide.
2. Spawn `optimizer` for one-variable speed candidates.
3. Spawn `benchmarker` for reproducible endpoint measurements.
4. Use `scripts/resolve_hf_gguf.py` for exact GGUF command construction.
5. Append completed measurements to `research/results.tsv`.

## Docs MCP

For OpenAI product or Codex documentation questions, use the OpenAI developer
documentation MCP server when available. A user-level install can be added with:

```bash
codex mcp add openaiDeveloperDocs --url https://developers.openai.com/mcp
```

This inference project does not require OpenAI docs access for llama.cpp
benchmarking itself; the MCP note is for Codex-specific usage questions.

## References

- `https://developers.openai.com/codex/cli`
- `https://developers.openai.com/learn/docs-mcp`
