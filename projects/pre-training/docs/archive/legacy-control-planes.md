# Legacy Control Planes

This repo used to ship three alternative control-plane scaffolds:

- Gastown rig assets
- Codex repo-local subagents
- Claude Code repo-local subagents

They were removed in favor of a single OpenCode-based control plane with:

- repo-local agents under `.opencode/agent/`
- shared skills under `.agents/skills/`
- neutral campaign and experiment templates under `research/templates/`
- isolated worker launches through `scripts/opencode_worker.py`
- HF Jobs for remote execution
- Trackio for observability

If you need the old Gastown, Codex, or Claude-specific material, use git
history from before the OpenCode migration instead of reviving those files in
the active setup path.
