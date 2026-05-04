#!/usr/bin/env python3
"""Resolve exact Hugging Face GGUF filenames for llama.cpp commands."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
from typing import Any


USER_AGENT = "autoresearch-inference/0.1"


def fetch_json(url: str) -> Any:
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HF API error {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"HF API request failed: {exc}") from exc


def file_size(entry: dict[str, Any]) -> int | None:
    size = entry.get("size")
    if isinstance(size, int):
        return size
    lfs = entry.get("lfs")
    if isinstance(lfs, dict) and isinstance(lfs.get("size"), int):
        return lfs["size"]
    return None


def human_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(value)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    return f"{amount:.1f} {unit}"


def is_main_gguf(entry: dict[str, Any]) -> bool:
    path = str(entry.get("path", ""))
    lower = path.lower()
    name = PurePosixPath(path).name.lower()
    if entry.get("type") != "file" or not lower.endswith(".gguf"):
        return False
    if name.startswith("mmproj") or "mmproj" in name:
        return False
    if lower.startswith("bf16/") or "/bf16/" in lower:
        return False
    return True


def list_ggufs(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    files = [entry for entry in tree if is_main_gguf(entry)]
    return sorted(files, key=lambda item: str(item.get("path", "")).lower())


def score_quant_match(path: str, quant: str) -> int:
    upper_path = path.upper()
    upper_quant = quant.upper()
    if upper_path.endswith(f"{upper_quant}.GGUF"):
        return 0
    if upper_quant in upper_path:
        return 1
    compressed_path = upper_path.replace("-", "_")
    compressed_quant = upper_quant.replace("-", "_")
    if compressed_quant in compressed_path:
        return 2
    return 99


def choose_file(
    files: list[dict[str, Any]], quant: str | None, exact_file: str | None
) -> dict[str, Any]:
    if not files:
        raise SystemExit("No main `.gguf` files found in the repo tree.")

    if exact_file:
        for entry in files:
            if entry.get("path") == exact_file or PurePosixPath(
                str(entry.get("path"))
            ).name == exact_file:
                return entry
        raise SystemExit(f"Requested GGUF file was not found: {exact_file}")

    if quant:
        matches = [
            entry
            for entry in files
            if score_quant_match(str(entry.get("path", "")), quant) < 99
        ]
        if matches:
            return sorted(
                matches,
                key=lambda entry: (
                    score_quant_match(str(entry.get("path", "")), quant),
                    len(str(entry.get("path", ""))),
                ),
            )[0]

    return files[0]


def build_command(args: argparse.Namespace, selected: dict[str, Any]) -> list[str]:
    command = [
        args.binary,
        "--hf-repo",
        args.repo,
        "--hf-file",
        str(selected["path"]),
    ]
    if args.context:
        command.extend(["-c", str(args.context)])
    if args.binary == "llama-server" and args.port:
        command.extend(["--port", str(args.port)])
    for extra in args.extra_arg:
        command.extend(shlex.split(extra))
    return command


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve exact GGUF files from the Hugging Face tree API."
    )
    parser.add_argument("--repo", required=True, help="Hugging Face repo id")
    parser.add_argument(
        "--quant",
        default="Q4_K_M",
        help="Quant label to prefer when selecting a GGUF file",
    )
    parser.add_argument("--file", help="Exact GGUF path or basename to use")
    parser.add_argument(
        "--binary",
        default="llama-server",
        choices=["llama-server", "llama-cli"],
        help="llama.cpp binary for the generated command",
    )
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Additional llama.cpp flag string to append; repeatable",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all main GGUF files instead of only the selected command",
    )
    args = parser.parse_args()

    quoted_repo = urllib.parse.quote(args.repo, safe="/")
    url = f"https://huggingface.co/api/models/{quoted_repo}/tree/main?recursive=true"
    tree = fetch_json(url)
    if not isinstance(tree, list):
        raise SystemExit("Unexpected HF API response; expected a JSON list.")

    files = list_ggufs(tree)
    selected = choose_file(files, args.quant, args.file)
    command = build_command(args, selected)

    output = {
        "repo": args.repo,
        "tree_api": url,
        "selected": {
            "path": selected["path"],
            "size_bytes": file_size(selected),
            "size": human_bytes(file_size(selected)),
        },
        "quant_preference": args.quant,
        "command": command,
        "command_text": shlex.join(command),
        "gguf_files": [
            {
                "path": entry["path"],
                "size_bytes": file_size(entry),
                "size": human_bytes(file_size(entry)),
            }
            for entry in files
        ],
    }

    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
        return

    print(f"Repo: {output['repo']}")
    print(
        "Selected: "
        f"{output['selected']['path']} ({output['selected']['size']})"
    )
    print(f"Command: {output['command_text']}")
    if args.list:
        print("\nMain GGUF files:")
        for entry in output["gguf_files"]:
            marker = "*" if entry["path"] == output["selected"]["path"] else "-"
            print(f"{marker} {entry['path']} ({entry['size']})")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(1)
