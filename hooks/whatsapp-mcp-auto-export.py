#!/usr/bin/env python3
"""
whatsapp-mcp-auto-export.py — PostToolUse hook.

When Claude calls a WhatsApp MCP read tool (list_messages, list_chats,
search_contacts), schedule a backgrounded vault export so the conversation
lands in `🤖 AI Chats/WhatsApp/<contact>.md` with voice-note transcripts.

Behavior:
  - Reads the PostToolUse JSON event from stdin.
  - If tool_name does NOT start with mcp__whatsapp__ (or doesn't match a
    read endpoint), exits silently with continue=True.
  - Rate-limits via a state file at /tmp/whatsapp-export-last-run so
    rapid-fire MCP calls in one session don't trigger N exports.
    Default min interval: 30s.
  - Backgrounds the wrapper with `--no-wait`, returning immediately so
    the session is not blocked. The wrapper itself polls /healthcheck,
    triggers a backfill sweep, and writes Markdown files in <2s.

Codified 2026-05-05 alongside CLAUDE.md rule "WhatsApp pulled via MCP
MUST be saved to vault same session, with voice-note transcripts included."
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

WRAPPER = os.path.expanduser("~/.local/bin/whatsapp-export-vault.sh")
STATE_FILE = "/tmp/whatsapp-export-last-run"
MIN_INTERVAL_SEC = 30
LOG_PATH = os.path.expanduser("~/Library/Logs/whatsapp-mcp-auto-export.log")

# Any whatsapp MCP tool that touches message content — read OR write.
# Sends are included so Claude-authored replies land in the vault on the
# next export cycle (the daemon stores them in SQLite immediately, but
# the vault Markdown stays stale until --export-to-vault fires).
TRIGGER_TOOLS = {
    # reads
    "mcp__whatsapp__list_messages",
    "mcp__whatsapp__list_chats",
    "mcp__whatsapp__search_contacts",
    # writes (create or react to messages, then export to capture)
    "mcp__whatsapp__send_message",
    "mcp__whatsapp__confirm_send",
    "mcp__whatsapp__send_reply_quote",
    "mcp__whatsapp__send_reaction",
    "mcp__whatsapp__mark_chat_read",
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

    # Background the wrapper. --no-wait so even slow daemons don't block.
    # stdout/stderr go to the wrapper's own log inside.
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
