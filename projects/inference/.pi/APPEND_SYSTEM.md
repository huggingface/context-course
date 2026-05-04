# llama.cpp Inference Pi Coordinator

This repository has a Pi-native secondary control plane for the `inference/`
project.

Use `AGENTS.md` as the hard rulebook. Keep work inside `inference/`; do not
modify `../pre-training` or `../post-training`.

When coordinating inference work:

- read `docs/pi-subagents-guide.md` before planning runs
- use project agents in `.pi/agents/` through `pi-subagents`
- use `optimizer` for one-variable speed candidates
- use `benchmarker` for reproducible endpoint benchmarks
- use `.agents/skills/huggingface-local-models/SKILL.md` for GGUF discovery,
  quant choice, and llama.cpp launch commands
- prefer `llama-server` and OpenAI-compatible endpoint benchmarks
- record completed benchmark results in `research/results.tsv`

If the user wants a full parent-session prompt, suggest:

```text
/inference-lab "<owner/repo> or local endpoint on :8080" 3
```
