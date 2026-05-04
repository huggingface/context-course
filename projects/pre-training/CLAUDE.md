# Claude Code Project Instructions

OpenCode is the canonical control plane for this repo.

The Claude Code implementation is a secondary native integration. It should
follow the same local workflow:

- no hosted Autolab backend
- no Gastown assets
- no duplicate control-plane state outside the repo notebook
- use the local promoted master in `train_orig.py`, `research/live/master.json`,
  and `research/results.tsv`
- use Hugging Face Jobs and the shared HF bucket for managed runs
- use Trackio for observability

Before running work in Claude Code:

1. Read `AGENTS.md`.
2. Prefer the project subagents under `.claude/agents/`.
3. Use `research/templates/` as the canonical campaign and experiment
   templates.
4. Keep `prepare.py` read-only.

Recommended entrypoints:

- `claude --agent autolab`

If a given Claude Code build does not surface project agents reliably in
`claude agents` or `/agents`, prefer the explicit `--agent autolab` entrypoint.

For a longer parent-session prompt, use:

```bash
uv run scripts/print_claude_kickoff.py --gpu-slots 1
```
