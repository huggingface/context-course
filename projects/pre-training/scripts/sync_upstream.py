#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPO = "karpathy/autoresearch"
UPSTREAM_FILES = [
    "prepare.py",
    "train.py",
    "program.md",
    "pyproject.toml",
    "uv.lock",
]


def fetch_upstream_text(path: str, branch: str, timeout: float) -> str:
    url = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{branch}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = f"HTTP {exc.code}"
        if body:
            detail += f": {body}"
        raise SystemExit(f"failed to fetch {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SystemExit(f"failed to fetch {url}: {exc}") from exc


def local_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def unified_diff(rel_path: str, current: str, upstream: str) -> str:
    diff_lines = list(
        difflib.unified_diff(
            current.splitlines(),
            upstream.splitlines(),
            fromfile=f"local/{rel_path}",
            tofile=f"upstream/{rel_path}",
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    return "\n".join(diff_lines) + "\n"


def apply_update(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare this repo's upstream-tracked core files against karpathy/autoresearch."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="overwrite the tracked upstream files with the fetched upstream versions",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit with status 1 when upstream diffs are present",
    )
    parser.add_argument(
        "--branch",
        default="master",
        help="upstream branch to compare against (default: master)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds for each upstream file fetch",
    )
    args = parser.parse_args()

    changed_files: list[str] = []
    for rel_path in UPSTREAM_FILES:
        upstream = fetch_upstream_text(rel_path, args.branch, args.timeout)
        path = ROOT / rel_path
        current = local_text(path)
        diff = unified_diff(rel_path, current, upstream)
        if diff:
            changed_files.append(rel_path)
            sys.stdout.write(diff)
            if args.apply:
                apply_update(path, upstream)

    if not changed_files:
        print("upstream-tracked files already match")
        return 0

    if args.apply:
        print("applied upstream updates:")
        for rel_path in changed_files:
            print(f"- {rel_path}")
        return 0

    if args.check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
