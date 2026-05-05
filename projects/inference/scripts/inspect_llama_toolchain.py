#!/usr/bin/env python3
"""Inspect local llama.cpp and hardware basics for inference tuning."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


COMMANDS = [
    "llama-server",
    "llama-cli",
    "llama-bench",
    "llama-perplexity",
    "llama-quantize",
    "hf",
]


def run_short(command: list[str], timeout: float = 5.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - report environment failures verbatim
        return {"ok": False, "error": str(exc)}

    text = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    first_lines = "\n".join(text.splitlines()[:6])
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "output": first_lines,
    }


def command_info(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    info: dict[str, Any] = {"present": path is not None, "path": path}
    if path:
        info["version"] = run_short([path, "--version"])
        if not info["version"]["ok"]:
            info["help"] = run_short([path, "--help"])
    return info


def sysctl_value(key: str) -> str | None:
    try:
        completed = subprocess.run(
            ["sysctl", "-n", key],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def linux_mem_bytes() -> int | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2:
                return int(parts[1]) * 1024
    return None


def total_memory_bytes() -> int | None:
    if platform.system() == "Darwin":
        value = sysctl_value("hw.memsize")
        return int(value) if value and value.isdigit() else None
    if platform.system() == "Linux":
        return linux_mem_bytes()
    return None


def cpu_name() -> str | None:
    if platform.system() == "Darwin":
        return sysctl_value("machdep.cpu.brand_string")
    if platform.system() == "Linux":
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            for line in cpuinfo.read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    return platform.processor() or None


def gpu_info() -> dict[str, Any]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"nvidia_smi": None}
    query = [
        nvidia_smi,
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader",
    ]
    return {"nvidia_smi": nvidia_smi, "query": run_short(query)}


def main() -> None:
    mem_bytes = total_memory_bytes()
    payload = {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "cpu": {
            "name": cpu_name(),
            "logical_count": os.cpu_count(),
            "physical_count": sysctl_value("hw.physicalcpu")
            if platform.system() == "Darwin"
            else None,
        },
        "memory": {
            "bytes": mem_bytes,
            "gib": round(mem_bytes / (1024**3), 2) if mem_bytes else None,
        },
        "gpu": gpu_info(),
        "commands": {name: command_info(name) for name in COMMANDS},
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
