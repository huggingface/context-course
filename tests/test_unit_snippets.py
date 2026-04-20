from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
import json
from dataclasses import dataclass
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
UNITS_DIR = ROOT / "units" / "en"
CODE_FENCE_RE = re.compile(r"```(?P<lang>[^\n]*)\n(?P<code>.*?)\n```", re.DOTALL)
MISSING = object()


@dataclass(frozen=True)
class FenceBlock:
    path: Path
    lang: str
    ordinal: int
    start: int
    code: str
    text: str


def iter_blocks(path: Path) -> list[FenceBlock]:
    text = path.read_text(encoding="utf-8")
    blocks: list[FenceBlock] = []
    ordinal = 0
    for match in CODE_FENCE_RE.finditer(text):
        ordinal += 1
        blocks.append(
            FenceBlock(
                path=path,
                lang=match.group("lang").strip(),
                ordinal=ordinal,
                start=match.start(),
                code=match.group("code"),
                text=text,
            )
        )
    return blocks


def block_after(path: Path, marker: str, lang: str, occurrence: int = 1) -> FenceBlock:
    marker_pos = path.read_text(encoding="utf-8").index(marker)
    matches = [block for block in iter_blocks(path) if block.lang == lang and block.start > marker_pos]
    return matches[occurrence - 1]


def is_pseudocode(block: FenceBlock) -> bool:
    prefix = block.text[max(0, block.start - 160) : block.start]
    return "Pseudocode" in prefix


@contextlib.contextmanager
def patched_modules(modules: dict[str, types.ModuleType]):
    previous: dict[str, object] = {}
    try:
        for name, module in modules.items():
            previous[name] = sys.modules.get(name, MISSING)
            sys.modules[name] = module
        yield
    finally:
        for name, old_value in previous.items():
            if old_value is MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_value


def exec_snippet(
    code: str,
    *,
    filename: str,
    modules: dict[str, types.ModuleType] | None = None,
    as_main: bool = False,
) -> dict[str, object]:
    namespace: dict[str, object] = {
        "__name__": "__main__" if as_main else "__snippet__",
    }
    with patched_modules(modules or {}):
        exec(compile(code, filename, "exec"), namespace)
    return namespace


class FakeFastMCP:
    instances: list["FakeFastMCP"] = []

    def __init__(self, name: str):
        self.name = name
        self.tools: dict[str, object] = {}
        self.resources: dict[str, object] = {}
        self.prompts: dict[str, object] = {}
        self.run_calls = 0
        type(self).instances.append(self)

    def tool(self, *_args, **_kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, uri: str, *_args, **_kwargs):
        def decorator(fn):
            self.resources[uri] = fn
            return fn

        return decorator

    def prompt(self, *_args, **_kwargs):
        def decorator(fn):
            self.prompts[fn.__name__] = fn
            return fn

        return decorator

    def run(self, *_args, **_kwargs):
        self.run_calls += 1


class FakeBlocks:
    instances: list["FakeBlocks"] = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.launch_calls: list[dict[str, object]] = []
        type(self).instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def launch(self, **kwargs):
        self.launch_calls.append(kwargs)


class FakeTab:
    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeComponent:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class FakeButton(FakeComponent):
    clicks: list[tuple[object, object, object]] = []

    def click(self, fn, inputs, outputs):
        type(self).clicks.append((fn, inputs, outputs))
        return None


class FakeTool:
    def __init__(self, name: str):
        self.name = name


class FakeSmolAgentsMCPClient:
    instances: list["FakeSmolAgentsMCPClient"] = []

    def __init__(self, config):
        self.config = config
        self.get_tools_calls = 0
        type(self).instances.append(self)

    def get_tools(self):
        self.get_tools_calls += 1
        return [FakeTool("calculator")]


class FakeCodeAgent:
    instances: list["FakeCodeAgent"] = []

    def __init__(self, *, tools, model_id):
        self.tools = tools
        self.model_id = model_id
        self.prompts: list[str] = []
        type(self).instances.append(self)

    def run(self, prompt: str):
        self.prompts.append(prompt)
        return "ok"


class FakeHFChunk:
    def __init__(self, text: str):
        delta = types.SimpleNamespace(content=text)
        choice = types.SimpleNamespace(delta=delta)
        self.choices = [choice]


class FakeHubMCPClient:
    instances: list["FakeHubMCPClient"] = []

    def __init__(self, *, model=None, provider=None):
        self.model = model
        self.provider = provider
        self.servers: list[dict[str, object]] = []
        self.messages: list[dict[str, object]] | None = None
        type(self).instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def add_mcp_server(self, **kwargs):
        self.servers.append(kwargs)

    async def process_single_turn_with_tools(self, messages):
        self.messages = messages
        yield FakeHFChunk("streamed output")


class FakeResponsesAPI:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(output_text='```python\nfinal_answer("done")\n```')


class FakeOpenAI:
    instances: list["FakeOpenAI"] = []

    def __init__(self, *, api_key=None, base_url=None):
        self.api_key = api_key
        self.base_url = base_url
        self.responses = FakeResponsesAPI()
        type(self).instances.append(self)


class UnitSnippetTests(unittest.TestCase):
    def test_copy_pasteable_python_snippets_compile(self):
        failures: list[str] = []
        for path in sorted(UNITS_DIR.rglob("*.mdx")):
            for block in iter_blocks(path):
                if block.lang != "python" or is_pseudocode(block):
                    continue
                try:
                    compile(block.code, f"{path}:{block.ordinal}", "exec")
                except SyntaxError as exc:
                    failures.append(f"{path}:{block.ordinal}: {exc.msg} (line {exc.lineno})")
        self.assertEqual([], failures, "\n".join(failures))

    def test_fastmcp_calculator_snippet_registers_tools(self):
        FakeFastMCP.instances.clear()

        fastmcp_module = types.ModuleType("mcp.server.fastmcp")
        fastmcp_module.FastMCP = FakeFastMCP
        modules = {
            "mcp": types.ModuleType("mcp"),
            "mcp.server": types.ModuleType("mcp.server"),
            "mcp.server.fastmcp": fastmcp_module,
        }

        block = block_after(
            UNITS_DIR / "unit2" / "building-servers.mdx",
            "Let's build a simple calculator server. Create `calculator_server.py`:",
            "python",
        )
        exec_snippet(block.code, filename=str(block.path), modules=modules, as_main=True)

        server = FakeFastMCP.instances[-1]
        self.assertEqual("calculator", server.name)
        self.assertEqual(1, server.run_calls)
        self.assertEqual(5, server.tools["add"](2, 3))
        self.assertEqual(6, server.tools["multiply"](2, 3))

    def test_gradio_mcp_snippet_launches_with_mcp_enabled(self):
        FakeBlocks.instances.clear()
        FakeButton.clicks.clear()

        gradio_module = types.ModuleType("gradio")
        gradio_module.Blocks = FakeBlocks
        gradio_module.Tab = FakeTab
        gradio_module.Textbox = FakeComponent
        gradio_module.Number = FakeComponent
        gradio_module.Button = FakeButton
        gradio_module.Markdown = lambda *args, **kwargs: None

        block = block_after(
            UNITS_DIR / "unit2" / "building-servers.mdx",
            "Create a Gradio app with MCP:",
            "python",
        )
        globals_dict = exec_snippet(
            block.code,
            filename=str(block.path),
            modules={"gradio": gradio_module},
            as_main=True,
        )

        demo = FakeBlocks.instances[-1]
        self.assertEqual([{"mcp_server": True}], demo.launch_calls)
        self.assertEqual({"letter_counter", "reverse_text"}, {fn.__name__ for fn, _, _ in FakeButton.clicks})
        self.assertEqual(2, globals_dict["letter_counter"]("Hello", "l"))
        self.assertEqual("cba", globals_dict["reverse_text"]("abc"))

    def test_gradio_auth_snippet_uses_supported_surface(self):
        block = block_after(
            UNITS_DIR / "unit2" / "building-servers.mdx",
            "### Authentication in Gradio MCP",
            "python",
        )
        self.assertIn('auth=("admin", "secret")', block.code)
        self.assertNotIn("gr.Header", block.code)

    def test_unit6_main_loop_documents_responses_api(self):
        block = block_after(
            UNITS_DIR / "unit6" / "agent-loop.mdx",
            "### The Main Loop",
            "python",
        )
        self.assertIn("client.responses.create(", block.code)
        self.assertIn("content = response.output_text", block.code)
        self.assertIn('result = "Executed successfully"', block.code)
        self.assertNotIn("client.messages.create(", block.code)

    def test_unit6_extended_harness_runs_against_openai_compatible_client(self):
        FakeOpenAI.instances.clear()

        openai_module = types.ModuleType("openai")
        openai_module.OpenAI = FakeOpenAI

        block = block_after(
            UNITS_DIR / "unit6" / "hands-on.mdx",
            "Create `nano_harness_extended.py` with all tools:",
            "python",
        )

        with mock.patch.dict(os.environ, {"HF_TOKEN": "hf_test_token"}, clear=False):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                globals_dict = exec_snippet(
                    block.code,
                    filename=str(block.path),
                    modules={"openai": openai_module},
                )
                globals_dict["main"]()

        client = FakeOpenAI.instances[-1]
        request = client.responses.calls[-1]
        self.assertEqual("https://router.huggingface.co/v1", client.base_url)
        self.assertEqual("hf_test_token", client.api_key)
        self.assertEqual("zai-org/GLM-5", request["model"])
        self.assertEqual("system", request["input"][0]["role"])
        self.assertIn("code-first agent", request["input"][0]["content"])
        self.assertEqual("user", request["input"][1]["role"])
        self.assertIn("Task complete", stdout.getvalue())

    def test_codex_plugin_manifest_references_skills_and_mcp_config(self):
        block = block_after(
            UNITS_DIR / "unit3" / "building-plugins.mdx",
            "Create `.codex-plugin/plugin.json`:",
            "json",
        )
        plugin_json = json.loads(block.code)
        self.assertEqual("./skills/", plugin_json["skills"])
        self.assertEqual("./.mcp.json", plugin_json["mcpServers"])

    def test_opencode_local_plugin_is_documented_module(self):
        block = block_after(
            UNITS_DIR / "unit3" / "building-plugins.mdx",
            "Create `.opencode/plugins/text-processor-plugin.ts`:",
            "ts",
        )
        self.assertIn("export const TextProcessorPlugin = async", block.code)
        self.assertIn('"tool.execute.before"', block.code)
        self.assertNotIn("../text-processor-mcp/server.py", block.code)


if __name__ == "__main__":
    unittest.main()
