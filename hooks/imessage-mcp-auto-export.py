#!/usr/bin/env python3
"""imessage-mcp-auto-export.py — PostToolUse hook.

When Claude calls an iMessage MCP read tool, fire-and-forget the vault export
wrapper so the conversation lands in `🤖 AI Chats/iMessage/<contact>.md` with
voice-note transcripts and attachments. Mirrors whatsapp-mcp-auto-export.py.

Behavior:
  - Reads the PostToolUse JSON event from stdin.
  - If tool_name does NOT match an iMessage MCP tool, exits with continue=True.
  - Rate-limits via /tmp/imessage-export-last-run so rapid-fire MCP calls
    don't trigger N parallel exports. Default min interval: 30s.
  - Backgrounds the wrapper with --no-wait, returning immediately so the
    session is not blocked.

Codified 2026-05-07 alongside the imessage-mcp build.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

WRAPPER = os.path.expanduser("~/.local/bin/imessage-export-vault.sh")
STATE_FILE = "/tmp/imessage-export-last-run"
MIN_INTERVAL_SEC = 30
LOG_PATH = os.path.expanduser("~/Library/Logs/imessage-mcp-auto-export.log")

TRIGGER_TOOLS = {
    # reads
    "mcp__imessage__list_messages",
    "mcp__imessage__list_chats",
    "mcp__imessage__search_contacts",
    "mcp__imessage__search_messages",
    "mcp__imessage__get_chat",
    "mcp__imessage__get_message_context",
    "mcp__imessage__get_unread",
    "mcp__imessage__get_thread",
    # writes (capture sends + reads same way as WhatsApp)
    "mcp__imessage__send_message",
    "mcp__imessage__confirm_send",
    "mcp__imessage__mark_chat_read",
}


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def should_throttle() -> bool:
    try:
        last = os.path.getmtime(STATE_FILE)
        return (time.time() - last) < MIN_INTERVAL_SEC
    except FileNotFoundError:
        return False


def mark_run() -> None:
    try:
        with open(STATE_FILE, "w") as f:
            f.write(str(time.time()))
    except Exception as e:
        log(f"mark_run failed: {e}")


def main() -> None:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        emit({"continue": True})
        return

    tool_name = event.get("tool_name") or ""
    if tool_name not in TRIGGER_TOOLS:
        emit({"continue": True})
        return

    if not os.path.isfile(WRAPPER) or not os.access(WRAPPER, os.X_OK):
        log(f"wrapper missing or not executable at {WRAPPER}")
        emit({"continue": True})
        return

    if should_throttle():
        emit({"continue": True})
        return

    mark_run()

    try:
        subprocess.Popen(
            [WRAPPER, "--no-wait"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log(f"backgrounded export after tool={tool_name}")
    except Exception as e:
        log(f"failed to spawn wrapper: {e}")

    emit({"continue": True})


if __name__ == "__main__":
    main()
