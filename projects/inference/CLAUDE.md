# Claude Code Project Instructions

This is the llama.cpp inference optimization project.

Use `AGENTS.md` as the hard rulebook. Keep this project separate from
`../pre-training` and `../post-training`.

The Claude Code-native pieces are:

- `.claude/settings.json`
- `.claude/agents/inference-lab.md`
- `.claude/agents/optimizer.md`
- `.claude/agents/benchmarker.md`

Recommended entrypoint:

```bash
claude --agent inference-lab
```

For a longer parent-session prompt:

```bash
python3 scripts/print_claude_kickoff.py
```

Rules:

- Prefer `llama-server` and the OpenAI-compatible endpoint.
- Use `.agents/skills/huggingface-local-models/SKILL.md` for GGUF discovery,
  quant choice, and launch commands.
- Benchmark with `scripts/benchmark_llama.py` before claiming speedups.
- Record completed results in `research/results.tsv`.
- Change one speed variable at a time unless explicitly running a sweep.
