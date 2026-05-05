#!/usr/bin/env python3
"""Create or update a repo-local Hermes profile home for Autolab."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_SKILL_DIR = ROOT / ".agents" / "skills"


def run(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, env=env, text=True, capture_output=True, check=False)


def require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise SystemExit(f"could not find `{name}` in PATH")


def hermes_supports_profiles(hermes_bin: str) -> bool:
    result = run([hermes_bin, "--help"])
    return result.returncode == 0 and re.search(r"(^|\s)profile(\s|,|\})", result.stdout) is not None


def hermes_root() -> Path:
    return Path.home() / ".hermes"


def source_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or hermes_root()).expanduser()


def profile_home(profile: str) -> Path:
    return hermes_root() / "profiles" / profile


def profile_alias(profile: str) -> Path:
    return Path.home() / ".local" / "bin" / profile


def parse_path_list(value: str) -> list[str]:
    text = value.strip()
    if not text:
        return []
    candidates = [text]
    try:
        parsed = ast.literal_eval(text)
    except Exception:
        parsed = None
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    if isinstance(parsed, str):
        candidates.insert(0, parsed)
    for candidate in candidates:
        try:
            parsed_json = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed_json, list):
            return [str(item) for item in parsed_json]
        if isinstance(parsed_json, str):
            return [parsed_json]
    return [text.strip("\"'")]


def read_external_dirs_block(section_lines: list[str], start: int) -> tuple[list[str], int]:
    line = section_lines[start]
    match = re.match(r"^  external_dirs:\s*(.*)$", line)
    if match is None:
        return [], start + 1
    trailing = match.group(1).strip()
    if trailing:
        return parse_path_list(trailing), start + 1

    values: list[str] = []
    index = start + 1
    while index < len(section_lines):
        current = section_lines[index]
        stripped = current.strip()
        if not stripped:
            index += 1
            continue
        if current.lstrip().startswith("#"):
            index += 1
            continue
        if current.startswith("    - "):
            values.extend(parse_path_list(current[6:].strip()))
            index += 1
            continue
        break
    return values, index


def update_external_dirs(config_text: str, skill_dir: Path) -> str:
    skill_dir_text = str(skill_dir)
    lines = config_text.splitlines()

    def top_level_key(line: str) -> str | None:
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            return None
        match = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", line.split("#", 1)[0].rstrip())
        return match.group(1) if match else None

    skills_start = None
    for index, line in enumerate(lines):
        if top_level_key(line) == "skills":
            skills_start = index
            break

    if skills_start is None:
        prefix = config_text.rstrip("\n")
        block = "skills:\n  external_dirs:\n    - " + json.dumps(skill_dir_text) + "\n"
        if not prefix:
            return block
        return prefix + "\n\n" + block

    skills_end = len(lines)
    for index in range(skills_start + 1, len(lines)):
        if top_level_key(lines[index]) is not None:
            skills_end = index
            break

    section = lines[skills_start:skills_end]
    external_start = None
    for index, line in enumerate(section[1:], start=1):
        if re.match(r"^  external_dirs:\s*(.*)$", line):
            external_start = index
            break

    if external_start is None:
        updated_section = section + ["  external_dirs:", f"    - {json.dumps(skill_dir_text)}"]
    else:
        values, external_end = read_external_dirs_block(section, external_start)
        merged: list[str] = []
        for item in values + [skill_dir_text]:
            if item and item not in merged:
                merged.append(item)
        replacement = ["  external_dirs:"] + [f"    - {json.dumps(item)}" for item in merged]
        updated_section = section[:external_start] + replacement + section[external_end:]

    updated_lines = lines[:skills_start] + updated_section + lines[skills_end:]
    return "\n".join(updated_lines).rstrip() + "\n"


def clone_file_if_missing(source: Path, destination: Path, *, actions: list[str], dry_run: bool) -> None:
    if not source.exists() or destination.exists():
        return
    actions.append(f"copy {source} -> {destination}")
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def write_wrapper(alias_path: Path, hermes_bin: str, target_home: Path, *, actions: list[str], dry_run: bool) -> None:
    content = (
        "#!/bin/sh\n"
        f"export HERMES_HOME={shlex.quote(str(target_home))}\n"
        f"exec {shlex.quote(hermes_bin)} \"$@\"\n"
    )
    actions.append(f"write alias wrapper {alias_path}")
    if dry_run:
        return
    alias_path.parent.mkdir(parents=True, exist_ok=True)
    alias_path.write_text(content, encoding="utf-8")
    alias_path.chmod(alias_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_profile_home(
    profile: str,
    *,
    hermes_bin: str,
    dry_run: bool,
    actions: list[str],
) -> tuple[Path, bool]:
    target_home = profile_home(profile)
    if target_home.exists():
        return target_home, False

    if hermes_supports_profiles(hermes_bin):
        actions.append(f"run {hermes_bin} profile create {profile} --clone")
        if not dry_run:
            result = run([hermes_bin, "profile", "create", profile, "--clone"], env=os.environ.copy())
            if result.returncode != 0:
                raise SystemExit(result.stderr.strip() or result.stdout.strip() or "hermes profile create failed")
        return target_home, True

    src_home = source_home()
    actions.append(f"create fallback Hermes profile home {target_home}")
    if not dry_run:
        target_home.mkdir(parents=True, exist_ok=True)
    clone_file_if_missing(src_home / "config.yaml", target_home / "config.yaml", actions=actions, dry_run=dry_run)
    clone_file_if_missing(src_home / ".env", target_home / ".env", actions=actions, dry_run=dry_run)
    clone_file_if_missing(src_home / "SOUL.md", target_home / "SOUL.md", actions=actions, dry_run=dry_run)
    write_wrapper(profile_alias(profile), hermes_bin, target_home, actions=actions, dry_run=dry_run)
    return target_home, True


def set_profile_worktree_false(hermes_bin: str, target_home: Path, *, actions: list[str], dry_run: bool) -> None:
    actions.append(f"set worktree=false in {target_home / 'config.yaml'}")
    if dry_run:
        return
    env = os.environ.copy()
    env["HERMES_HOME"] = str(target_home)
    result = run([hermes_bin, "config", "set", "worktree", "false"], env=env)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "failed to set Hermes worktree=false")


def update_profile_config(target_home: Path, *, actions: list[str], dry_run: bool) -> Path:
    config_path = target_home / "config.yaml"
    current_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    updated_text = update_external_dirs(current_text, REPO_SKILL_DIR)
    if updated_text == current_text:
        return config_path
    actions.append(f"update skills.external_dirs in {config_path}")
    if not dry_run:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(updated_text, encoding="utf-8")
    return config_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a local Hermes Autolab profile and wire in repo skills.")
    parser.add_argument("--profile", default="autolab", help="Hermes profile name to create or update")
    parser.add_argument("--hermes-bin", help="override the Hermes executable")
    parser.add_argument("--dry-run", action="store_true", help="print planned actions without changing local Hermes state")
    args = parser.parse_args()

    hermes_bin = args.hermes_bin or require_tool("hermes")
    actions: list[str] = []
    target_home, created = ensure_profile_home(args.profile, hermes_bin=hermes_bin, dry_run=args.dry_run, actions=actions)
    set_profile_worktree_false(hermes_bin, target_home, actions=actions, dry_run=args.dry_run)
    config_path = update_profile_config(target_home, actions=actions, dry_run=args.dry_run)

    for action in actions:
        print(action)

    print()
    if args.dry_run:
        print("dry-run only; no local Hermes files were changed")
    else:
        print(f"profile home: {target_home}")
        print(f"config path: {config_path}")
        print(f"repo skill dir: {REPO_SKILL_DIR}")
        if created:
            print("profile status: created or bootstrapped")
        else:
            print("profile status: updated in place")
        print()
        print("next:")
        print(
            f"  {args.profile} chat --toolsets "
            '"terminal,file,web,skills,delegation,clarify"'
        )
        print("fallback:")
        print(
            "  "
            f"HERMES_HOME={shlex.quote(str(target_home))} {shlex.quote(hermes_bin)} chat --toolsets "
            '"terminal,file,web,skills,delegation,clarify"'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
