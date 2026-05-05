---
description: Start a Pi-native llama.cpp inference optimization parent session.
argument-hint: "[target] [max-candidates]"
---

You are coordinating local llama.cpp inference optimization in this project
using Pi and `pi-subagents`.

Arguments:

- target: `$1` if provided, otherwise `current running llama-server endpoint`
- max candidates: `$2` if provided, otherwise `3`

Read:

- `AGENTS.md`
- `README.md`
- `docs/pi-subagents-guide.md`
- `.agents/skills/huggingface-local-models/SKILL.md`
- `research/results.tsv`
- `research/notes.md`
- `research/do-not-repeat.md`

Use Pi project agents:

- `benchmarker` for baseline and candidate measurements
- `optimizer` for one-variable speed candidates

First ask `benchmarker` to measure a reproducible baseline for the target. Then
ask `optimizer` for up to the requested max candidates. For the best candidate,
ask `benchmarker` to run the same benchmark and append the result to
`research/results.tsv`.

Keep all comparisons honest:

- same model and exact GGUF unless the change is explicitly quant/model choice
- same prompt and `max_tokens`
- same context
- same llama.cpp build/backend
- one changed speed variable per benchmark
