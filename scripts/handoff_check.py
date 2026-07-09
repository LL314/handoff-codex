#!/usr/bin/env python3
"""Codex Stop hook for Handoff Codex.

Reads the hook payload on stdin, inspects the transcript's latest token_count
event, and blocks the turn with extra instructions when the configured threshold
is reached.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


DEFAULT_THRESHOLD = 200_000


def debug(message: str) -> None:
    if os.environ.get("HANDOFF_CODEX_DEBUG") != "1":
        return
    try:
        with open("/tmp/handoff-codex-hook.log", "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def latest_context_tokens(transcript_path: str | None) -> int | None:
    if not transcript_path:
        return None
    path = Path(transcript_path)
    if not path.exists() or not path.is_file():
        return None

    latest: int | None = None
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Codex rollout JSONL: event_msg -> token_count.
            payload = item.get("payload") or {}
            info = payload.get("info") or {}
            usage = info.get("last_token_usage") or {}
            if item.get("type") == "event_msg" and payload.get("type") == "token_count":
                tokens = usage.get("input_tokens")
                if isinstance(tokens, int):
                    latest = tokens
                    continue

            # Claude/Cursor-compatible fallback for transcript formats with message usage.
            message = item.get("message") or {}
            msg_usage = message.get("usage") or {}
            if message.get("role") == "assistant" and msg_usage:
                parts = [
                    msg_usage.get("input_tokens", 0),
                    msg_usage.get("cache_read_input_tokens", 0),
                    msg_usage.get("cache_creation_input_tokens", 0),
                ]
                if all(isinstance(value, int) for value in parts):
                    latest = sum(parts)

    return latest


def project_name(cwd: str | None) -> str:
    if not cwd:
        cwd = os.getcwd()
    name = Path(cwd).resolve().name
    return name or "default"


def handoff_dir(cwd: str | None) -> str:
    if cwd is None:
        cwd = os.getcwd()
    configured = os.environ.get("HANDOFF_CODEX_DATA")
    if configured:
        data_root = Path(configured).expanduser()
    else:
        data_root = Path(cwd).resolve() / "work" / "handoffs"
    return str(data_root / project_name(cwd))


def main() -> int:
    debug("hook start")
    try:
        payload = json.load(sys.stdin)
    except Exception:
        debug("no valid stdin json")
        return 0

    # Avoid blocking a continuation that is already handling this Stop hook.
    if payload.get("stop_hook_active"):
        debug("stop_hook_active; skip")
        return 0

    tokens = latest_context_tokens(payload.get("transcript_path"))
    threshold = env_int("HANDOFF_CODEX_THRESHOLD", DEFAULT_THRESHOLD)
    debug(f"tokens={tokens} threshold={threshold} transcript={payload.get('transcript_path')}")
    if tokens is None or tokens < threshold:
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    target_dir = handoff_dir(cwd)
    session_id = payload.get("session_id") or "unknown"
    reason = f"""
[handoff-codex] Context {tokens:,} >= {threshold:,}; create a handoff before continuing.

Handoff Codex threshold reached.

Current context tokens: {tokens:,}
Threshold: {threshold:,}
Session ID: {session_id}
Working directory: {cwd}
Handoff directory: {target_dir}

Immediately use $handoff-codex to write a concise handoff document in the handoff directory above.
After writing it, tell the user to start a new Codex App thread and paste the resume prompt from the handoff.
Do not continue the original task in this overloaded thread unless the user explicitly asks.
""".strip()

    print(
        json.dumps(
            {
                "decision": "block",
                "reason": reason,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
