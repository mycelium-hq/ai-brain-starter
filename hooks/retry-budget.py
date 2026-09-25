#!/usr/bin/env python3
"""
PreToolUse Bash hook: retry budget.

Blocks the 4th invocation of an identical Bash command within 30 minutes.
Claude loops on failing commands and burns context; this hook forces an
escape at 3 attempts so the blocker gets surfaced to the user.

Bypass: prefix command with RETRY_BUDGET_BYPASS=1 when intentionally
re-running (polling a cron, expected retries, iteration on a fix where
each attempt is a real change).

State: <tempdir>/claude-retry-budget-{session_id}.json keyed by md5(norm_cmd).
Window: 30 min rolling. Commands <15 chars exempt (ls, pwd, date, etc.).

What counts as one attempt:
  * norm_cmd is the WHOLE whitespace-normalized command. A digest is
    fixed-size however much it hashes, so capping its input only merges
    distinct commands: a 400-character cap made different steps that open
    with the same long scratch path share one budget, and blocked the 4th
    distinct step as a loop.
  * One Bash call is one attempt. The harness hands every registration of
    this hook the same tool_use_id for a call, so when two installers wire
    the script twice, the later registration reuses the first one's verdict
    instead of counting the call again (which blocked the 3rd call, not the
    4th). A payload with no tool_use_id counts every invocation, as before.

Pattern inspired by Devin 2.0 ("ask user for help if CI does not pass
after the third attempt") and Cursor 2.0 ("don't loop more than 3 times
to fix linter errors").
"""
import json
import sys
import os
import time
import hashlib
import glob
import tempfile

THRESHOLD_BLOCK = 4       # 4th+ attempt blocks (3 attempts allowed)
WINDOW_SEC = 30 * 60
MIN_CMD_LEN = 15
STATE_DIR = tempfile.gettempdir()  # /tmp is POSIX-only; Windows has no /tmp
STATE_TTL_SEC = 24 * 3600
# tool_use_id -> [time counted, attempt number]. Pruned on the same window as
# the attempts themselves, so a call is remembered for as long as it counts.
CALLS_KEY = "_calls"


def _load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        return {}
    return state if isinstance(state, dict) else {}


def _save_state(path, state):
    """Replace the file whole. A second registration of the same call may be
    reading it at this moment, and a half-written file reads as an empty
    budget. os.replace also swaps out a pre-planted link instead of writing
    through it."""
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".",
                                   prefix="claude-retry-budget-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
        tmp = None
    except Exception:
        pass
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)
            except OSError:
                pass


def _within_window(value, now):
    return isinstance(value, (int, float)) and now - value < WINDOW_SEC


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name", "") != "Bash":
        sys.exit(0)

    command = (data.get("tool_input", {}) or {}).get("command", "") or ""
    if len(command.strip()) < MIN_CMD_LEN:
        sys.exit(0)

    if "RETRY_BUDGET_BYPASS=1" in command:
        sys.exit(0)

    session_id = (
        data.get("session_id")
        or os.environ.get("CLAUDE_SESSION_ID")
        or "unknown"
    )
    state_path = os.path.join(
        STATE_DIR, f"claude-retry-budget-{session_id}.json"
    )

    norm = " ".join(command.split())
    cmd_hash = hashlib.md5(norm.encode("utf-8")).hexdigest()[:12]
    call_id = data.get("tool_use_id")
    if not isinstance(call_id, str) or not call_id:
        call_id = None
    now = time.time()

    state = _load_state(state_path)
    calls = state.get(CALLS_KEY)
    if not isinstance(calls, dict):
        calls = {}

    counted = calls.get(call_id) if call_id else None
    if (isinstance(counted, list) and len(counted) == 2
            and isinstance(counted[1], int)):
        # Another registration already counted this call: same verdict,
        # nothing added.
        count = counted[1]
    else:
        history = [t for t in state.get(cmd_hash, []) if _within_window(t, now)]
        history.append(now)
        state[cmd_hash] = history
        count = len(history)
        if call_id:
            calls[call_id] = [now, count]
        # Keep the file bounded to the window: every other command's stale
        # attempts, and every call too old to be re-counted.
        for key in list(state):
            if key == CALLS_KEY:
                continue
            kept = [t for t in state[key] if _within_window(t, now)] \
                if isinstance(state[key], list) else []
            if kept:
                state[key] = kept
            else:
                del state[key]
        state[CALLS_KEY] = {
            k: v for k, v in calls.items()
            if isinstance(v, list) and len(v) == 2 and _within_window(v[0], now)
        }
        _save_state(state_path, state)

    # Best-effort cleanup of sibling state files (and temp files a killed
    # write left behind) older than 24h
    try:
        for pattern in ("claude-retry-budget-*.json", "claude-retry-budget-*.tmp"):
            for path in glob.glob(os.path.join(STATE_DIR, pattern)):
                try:
                    if now - os.path.getmtime(path) > STATE_TTL_SEC:
                        os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass

    if count >= THRESHOLD_BLOCK:
        preview = norm[:80] + ("…" if len(norm) > 80 else "")
        print(
            "BLOCKED by retry-budget hook:\n"
            f"  This command has run {count} times in the last 30 minutes:\n"
            f"    {preview}\n"
            "  Stop looping. Surface to the user: what failed on previous "
            "attempts, and what do they want to do?\n"
            "  Bypass (if you genuinely need to re-run): prefix with "
            "RETRY_BUDGET_BYPASS=1.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
