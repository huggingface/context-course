#!/usr/bin/env python3
"""Benchmark a llama-server OpenAI-compatible chat endpoint."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shlex
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROMPT = (
    "Write a concise technical checklist for making local LLM inference faster. "
    "Keep it practical and specific."
)


TSV_FIELDS = [
    "timestamp",
    "experiment_id",
    "model",
    "server_command",
    "base_url",
    "runs",
    "warmup",
    "max_tokens",
    "prompt_sha256",
    "completion_tokens_mean",
    "seconds_mean",
    "tokens_per_second_mean",
    "tokens_per_second_median",
    "prompt_tokens_mean",
    "success",
    "notes",
    "output_json",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    return args.prompt


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def parse_metadata(values: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"metadata must be KEY=VALUE, got: {value}")
        key, item = value.split("=", 1)
        metadata[key] = item
    return metadata


def post_json(url: str, payload: dict[str, Any], api_key: str, timeout: float) -> Any:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "autoresearch-inference/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def get_url(url: str, api_key: str, timeout: float) -> bool:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "autoresearch-inference/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def wait_for_server(base_url: str, api_key: str, timeout: float) -> None:
    base = base_url.rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    candidates = [f"{base}/models", f"{root}/health"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(get_url(url, api_key, timeout=2) for url in candidates):
            return
        time.sleep(1)
    raise RuntimeError(
        "Timed out waiting for server. Tried: " + ", ".join(candidates)
    )


def estimate_tokens(text: str) -> int:
    words = [part for part in text.replace("\n", " ").split(" ") if part]
    return max(1, int(round(len(words) * 1.3)))


def chat_once(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    system: str | None,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    url = f"{base_url.rstrip('/')}/chat/completions"
    started = time.perf_counter()
    response = post_json(url, payload, api_key, timeout)
    elapsed = time.perf_counter() - started

    if isinstance(response, dict) and response.get("error"):
        raise RuntimeError(f"Endpoint returned error: {response['error']}")

    choices = response.get("choices") if isinstance(response, dict) else None
    if not choices:
        raise RuntimeError(f"Endpoint response had no choices: {response}")
    message = choices[0].get("message", {})
    content = message.get("content") or ""
    usage = response.get("usage", {}) if isinstance(response, dict) else {}
    completion_tokens = usage.get("completion_tokens")
    token_source = "usage.completion_tokens"
    if not isinstance(completion_tokens, int) or completion_tokens <= 0:
        completion_tokens = estimate_tokens(content)
        token_source = "estimated_from_text"

    prompt_tokens = usage.get("prompt_tokens")
    tokens_per_second = completion_tokens / elapsed if elapsed > 0 else 0.0
    return {
        "seconds": elapsed,
        "completion_tokens": completion_tokens,
        "prompt_tokens": prompt_tokens if isinstance(prompt_tokens, int) else None,
        "tokens_per_second": tokens_per_second,
        "token_source": token_source,
        "content_chars": len(content),
        "finish_reason": choices[0].get("finish_reason"),
    }


def launch_server(
    command_text: str, experiment_id: str, startup_timeout: float
) -> tuple[subprocess.Popen[bytes], Any, Path]:
    args = shlex.split(command_text)
    if not args:
        raise SystemExit("--server-cmd cannot be empty")

    log_dir = Path(".runtime/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{experiment_id}.server.log"
    log_handle = log_path.open("ab")
    proc = subprocess.Popen(
        args,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if startup_timeout <= 0:
        return proc, log_handle, log_path
    return proc, log_handle, log_path


def stop_server(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        proc.wait(timeout=5)


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    tps = [float(run["tokens_per_second"]) for run in runs]
    seconds = [float(run["seconds"]) for run in runs]
    completion_tokens = [int(run["completion_tokens"]) for run in runs]
    prompt_tokens = [
        int(run["prompt_tokens"])
        for run in runs
        if isinstance(run.get("prompt_tokens"), int)
    ]
    return {
        "runs": len(runs),
        "tokens_per_second_mean": statistics.mean(tps),
        "tokens_per_second_median": statistics.median(tps),
        "seconds_mean": statistics.mean(seconds),
        "completion_tokens_mean": statistics.mean(completion_tokens),
        "prompt_tokens_mean": statistics.mean(prompt_tokens)
        if prompt_tokens
        else None,
        "token_sources": sorted({str(run["token_source"]) for run in runs}),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_tsv(path: Path, payload: dict[str, Any], output_json: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    summary = payload["summary"]
    config = payload["config"]
    row = {
        "timestamp": payload["timestamp"],
        "experiment_id": config["experiment_id"],
        "model": config["model"],
        "server_command": config.get("server_command") or "",
        "base_url": config["base_url"],
        "runs": config["runs"],
        "warmup": config["warmup"],
        "max_tokens": config["max_tokens"],
        "prompt_sha256": config["prompt_sha256"],
        "completion_tokens_mean": f"{summary['completion_tokens_mean']:.3f}",
        "seconds_mean": f"{summary['seconds_mean']:.6f}",
        "tokens_per_second_mean": f"{summary['tokens_per_second_mean']:.6f}",
        "tokens_per_second_median": f"{summary['tokens_per_second_median']:.6f}",
        "prompt_tokens_mean": ""
        if summary["prompt_tokens_mean"] is None
        else f"{summary['prompt_tokens_mean']:.3f}",
        "success": "true",
        "notes": config.get("notes", ""),
        "output_json": output_json or "",
    }
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TSV_FIELDS, delimiter="\t")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark a llama-server OpenAI-compatible endpoint."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY", "no-key"),
        help="Bearer token for the local endpoint",
    )
    parser.add_argument("--model", default="local-gguf")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--prompt-file")
    parser.add_argument("--system")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--startup-timeout", type=float, default=180)
    parser.add_argument("--server-cmd", help="llama-server command to launch")
    parser.add_argument(
        "--keep-server",
        action="store_true",
        help="Leave a launched server running after the benchmark",
    )
    parser.add_argument("--experiment-id")
    parser.add_argument("--notes", default="")
    parser.add_argument("--metadata", action="append", default=[])
    parser.add_argument("--output-json")
    parser.add_argument("--append-tsv")
    args = parser.parse_args()

    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    if args.warmup < 0:
        raise SystemExit("--warmup cannot be negative")

    experiment_id = args.experiment_id or "bench-" + datetime.now(
        timezone.utc
    ).strftime("%Y%m%d-%H%M%S")
    prompt = read_prompt(args)
    proc: subprocess.Popen[bytes] | None = None
    log_handle: Any | None = None
    server_log: Path | None = None

    try:
        if args.server_cmd:
            proc, log_handle, server_log = launch_server(
                args.server_cmd, experiment_id, args.startup_timeout
            )
        wait_for_server(args.base_url, args.api_key, args.startup_timeout)

        for _ in range(args.warmup):
            chat_once(
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                prompt=prompt,
                system=args.system,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                timeout=args.timeout,
            )

        runs = [
            chat_once(
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                prompt=prompt,
                system=args.system,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                timeout=args.timeout,
            )
            for _ in range(args.runs)
        ]
        summary = summarize(runs)
        output = {
            "timestamp": utc_now(),
            "config": {
                "experiment_id": experiment_id,
                "base_url": args.base_url,
                "model": args.model,
                "server_command": args.server_cmd,
                "server_log": str(server_log) if server_log else None,
                "prompt_sha256": prompt_hash(prompt),
                "prompt_chars": len(prompt),
                "max_tokens": args.max_tokens,
                "temperature": args.temperature,
                "runs": args.runs,
                "warmup": args.warmup,
                "notes": args.notes,
                "metadata": parse_metadata(args.metadata),
            },
            "summary": summary,
            "runs": runs,
        }

        if args.output_json:
            write_json(Path(args.output_json), output)
        if args.append_tsv:
            append_tsv(Path(args.append_tsv), output, args.output_json)
        print(json.dumps(output, indent=2, sort_keys=True))
    finally:
        if proc is not None and not args.keep_server:
            stop_server(proc)
        if log_handle is not None:
            log_handle.close()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(1)
