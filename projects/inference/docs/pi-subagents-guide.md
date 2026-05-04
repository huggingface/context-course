# Pi Subagents Guide

This guide describes the Pi-native inference setup.

Pi is a minimal terminal coding harness extended through packages, skills,
prompt templates, and settings. Project settings live in `.pi/settings.json`,
and `pi-subagents` reads project agents from `.pi/agents/`.

## Checked-In Pi Assets

- `.pi/settings.json`
  Project Pi settings. It declares `npm:pi-subagents`, loads the local skills,
  loads project prompt templates, and keeps sessions under `.runtime/`.
- `.pi/APPEND_SYSTEM.md`
  Parent-session inference coordinator guidance appended to Pi's default prompt.
- `.pi/agents/optimizer.md`
  Read-only speed candidate proposer.
- `.pi/agents/benchmarker.md`
  Local benchmark runner and result recorder.
- `.pi/prompts/inference-lab.md`
  Reusable `/inference-lab` kickoff prompt.

## Setup

Install Pi once if it is not already available:

```bash
npm install -g @mariozechner/pi-coding-agent
```

From `inference/`, start Pi:

```bash
pi
```

Pi should load `npm:pi-subagents` from `.pi/settings.json`. If you prefer to
install the package explicitly, run:

```bash
pi install npm:pi-subagents -l
```

Authenticate a provider with `/login`, or start Pi with the provider API key in
the environment.

## Parent Session

Run the project prompt template:

```text
/inference-lab "<owner/repo> or local endpoint on :8080" 3
```

Useful direct commands:

```text
/run benchmarker "Measure the current local endpoint baseline and append the result."
/run optimizer "Propose one safe speed candidate against the latest baseline."
/run benchmarker "Benchmark this candidate command against the baseline."
```

## Workflow

1. Resolve a target GGUF with `scripts/resolve_hf_gguf.py`.
2. Use `benchmarker` to record a baseline in `research/results.tsv`.
3. Use `optimizer` to propose one speed variable to change.
4. Use `benchmarker` to repeat the same benchmark.
5. Record the fastest reproducible command and any quality tradeoff.

Keep comparisons controlled: same model, exact GGUF, prompt, `max_tokens`,
context, and llama.cpp build unless the experiment is explicitly changing one
of those variables.

## References

- `https://pi.dev/docs/latest`
- `https://pi.dev/docs/latest/settings`
- `https://pi.dev/packages/pi-subagents`
- `https://huggingface.co/learn/context-course/unit0/introduction?tool=Pi`
