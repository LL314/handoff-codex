#!/usr/bin/env python3
"""Codex hooks for Handoff Codex.

Reads the hook payload on stdin, inspects the transcript's latest token_count
event, and defers handoff instructions until the next user prompt so the current
assistant response can finish normally.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
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


def safe_session_id(session_id: str | None) -> str:
    raw = session_id or "unknown"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")
    return safe or "unknown"


def pending_path(cwd: str | None, session_id: str | None) -> Path:
    return Path(handoff_dir(cwd)) / f".handoff-codex-pending-{safe_session_id(session_id)}.json"


def write_pending(payload: dict, tokens: int, threshold: int) -> Path:
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id") or "unknown"
    target_dir = Path(handoff_dir(cwd))
    target_dir.mkdir(parents=True, exist_ok=True)
    marker = pending_path(cwd, session_id)
    marker.write_text(
        json.dumps(
            {
                "tokens": tokens,
                "threshold": threshold,
                "session_id": session_id,
                "cwd": cwd,
                "handoff_dir": str(target_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return marker


def read_pending(payload: dict) -> dict | None:
    marker = pending_path(payload.get("cwd"), payload.get("session_id"))
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    data["_marker_path"] = str(marker)
    return data


def pending_context(pending: dict) -> str:
    tokens = pending.get("tokens", "unknown")
    threshold = pending.get("threshold", "unknown")
    handoff_target = pending.get("handoff_dir", "")
    cwd = pending.get("cwd", "")
    return f"""
[handoff-codex] A handoff was deferred until the previous assistant response finished.

Before handling the user's new request, use $handoff-codex to write a concise handoff document.

Current context tokens when threshold was reached: {tokens}
Threshold: {threshold}
Working directory: {cwd}
Handoff directory: {handoff_target}

After writing the handoff, tell the user to start a new Codex App thread and paste the resume prompt from the handoff.
Do not continue other work in this overloaded thread unless the user explicitly asks after the handoff is complete.
""".strip()


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

    event_name = payload.get("hook_event_name") or "Stop"
    if event_name == "UserPromptSubmit":
        pending = read_pending(payload)
        if not pending:
            return 0
        context = pending_context(pending)
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context,
                    },
                    "systemMessage": "Handoff Codex deferred handoff is pending.",
                },
                ensure_ascii=False,
            )
        )
        return 0

    tokens = latest_context_tokens(payload.get("transcript_path"))
    threshold = env_int("HANDOFF_CODEX_THRESHOLD", DEFAULT_THRESHOLD)
    debug(
        f"event={event_name} tokens={tokens} threshold={threshold} "
        f"transcript={payload.get('transcript_path')}"
    )
    if tokens is None or tokens < threshold:
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    target_dir = handoff_dir(cwd)
    marker = write_pending(payload, tokens, threshold)
    debug(f"pending marker written: {marker}")

    print(
        json.dumps(
            {
                "systemMessage": (
                    f"Handoff Codex deferred handoff: context {tokens:,} >= {threshold:,}. "
                    f"The current response was allowed to finish. Handoff will be requested on the next user prompt. "
                    f"Handoff directory: {target_dir}"
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
