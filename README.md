# The Context Course

If you like the course, **don't hesitate to ⭐ star this repository**. This helps us to make the course more visible.

The Context Course teaches you **context engineering for code agents** — the skill of giving agents the right knowledge, tools, and structure to do their best work. Whether you're using Claude Code, Codex, or open source agents, this course will help you get dramatically more out of them.

The course covers the full context engineering stack: **skills, MCP, plugins, subagents**, and even building your own agent from scratch.

Sign up here (it's free) 👉 [huggingface.co/context-course](https://huggingface.co/context-course)

| Unit | Topic | Description |
| ---- | ----- | ----------- |
| 0 | Welcome & Onboarding | Set up your tools, join the community, and get oriented. |
| 1 | Skills: Portable Knowledge | Learn to write, use, and share agent skills — portable instructions that make agents expert at specific tasks. |
| 2 | MCP: The Model Context Protocol | Build MCP servers that give agents dynamic access to external tools and data. |
| 3 | Plugins: Bundling for Distribution | Package skills and MCP servers into plugins that work across agent platforms. |
| 4 | Subagents: Multi-Agent Workflows | Orchestrate complex tasks by spawning specialized child agents. |
| 5 | Hooks: Observing and Guarding the Lifecycle | Use hooks to log, block, or automate around every step the agent takes — then visualize it live in Gradio. |
| 6 | Bonus: Nano Harness | Build your own minimal agent from scratch to understand how it all works under the hood. |

## Prerequisites

* Basic familiarity with Python and the command line
* A Hugging Face account ([hf.co/join](https://hf.co/join))
* Access to a code agent: Claude Code, Codex, or an open source alternative

## Reference Agents

This edition keeps the examples consistent by following three reference agents end-to-end:

* **Claude Code** — `claude` in your terminal
* **Codex** — `codex` CLI from OpenAI
* **OpenCode** — `opencode` from opencode.ai

If you use Cursor or GitHub Copilot, the concepts in the course still transfer, but their MCP and extension workflows are not covered step-by-step in this edition.

## Quick Start

```bash
# 1. Clone the course
git clone https://github.com/huggingface/context-course.git
cd context-course

# 2. Install the HF CLI
curl -LsSf https://hf.co/cli/install.sh | bash
hf auth login

# 3. Start with Unit 0
# Open units/en/unit0/introduction.mdx
```

## Certification

| Certificate | Requirements |
| :---------- | :----------- |
| **Context Fundamentals** | Pass the Unit 1 and Unit 2 quizzes |
| **Context Engineering** | Pass all quizzes + complete a hands-on project |

## Contributing

Contributions are welcome!

* Found a bug? [Open an issue](https://github.com/huggingface/context-course/issues/new)
* Want to improve content? [Submit a PR](https://github.com/huggingface/context-course/pulls)
* Want to add a unit? [Open an issue first](https://github.com/huggingface/context-course/issues/new) to discuss

## Citing the Course

```bibtex
@misc{context-course,
  author = {Burtenshaw, Ben},
  title = {The Context Course: Context Engineering for Code Agents},
  year = {2025},
  howpublished = {\url{https://github.com/huggingface/context-course}},
  note = {GitHub repository},
}
```
