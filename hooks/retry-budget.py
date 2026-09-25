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
  * Calls race on one file (subagents share their parent's session_id), so
    each read-modify-write holds a sidecar lock. The wait is bounded: a
    holder that never lets go costs LOCK_WAIT_SEC, then the hook proceeds
    unlocked. It runs before every Bash call, so it fails OPEN on its own
    errors: a broken budget must never become a broken shell.

Pattern inspired by Devin 2.0 ("ask user for help if CI does not pass
after the third attempt") and Cursor 2.0 ("don't loop more than 3 times
to fix linter errors").
"""
import json
import sys
import os
import math
import stat
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
LOCK_WAIT_SEC = 2.0
MAX_STATE_BYTES = 4 * 1024 * 1024
# An attempt stamped this far ahead of the clock is still honoured (clock
# skew between processes); beyond it, it is bogus and dropped.
FUTURE_SKEW_SEC = 60


def _load_state(path):
    """Read the budget, accepting only a regular file of sane size. The path
    is predictable, so a FIFO or a link planted there must neither hang the
    hook nor steer its count."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return {}
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_STATE_BYTES:
            return {}
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            fd = None
            state = json.load(f)
    except Exception:
        return {}
    finally:
        if fd is not None:
            os.close(fd)
    return state if isinstance(state, dict) else {}


def _save_state(path, state):
    """Replace the file whole. A reader that could not get the lock may be
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


def _acquire_lock(path):
    """An fd holding an exclusive lock on `path`, or None (no lock taken)."""
    try:
        import fcntl  # POSIX only; elsewhere the hook proceeds unlocked
    except ImportError:
        return None
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError:
        return None
    deadline = time.monotonic() + LOCK_WAIT_SEC
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(0.005)
    try:
        os.utime(path)  # a lock in use is never the 24h-stale file cleanup removes
    except OSError:
        pass
    return fd


def _within_window(value, now):
    """A usable attempt time: a finite number inside the window, not far in
    the future. A planted Infinity or a clock stepped backwards must not pin
    a command's budget, and no value may crash the hook."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        age = now - float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(age) and -FUTURE_SKEW_SEC <= age < WINDOW_SEC


def _count(state, cmd_hash, call_id, now):
    """Record this call (once) and return its attempt number. Mutates state;
    returns (count, changed)."""
    calls = state.get(CALLS_KEY)
    if not isinstance(calls, dict):
        calls = {}
    counted = calls.get(call_id) if call_id else None
    if (isinstance(counted, list) and len(counted) == 2
            and isinstance(counted[1], int) and not isinstance(counted[1], bool)
            and counted[1] >= 1 and _within_window(counted[0], now)):
        # Another registration already counted this call: same verdict,
        # nothing added.
        return counted[1], False

    history = state.get(cmd_hash)
    history = [t for t in history if _within_window(t, now)] \
        if isinstance(history, list) else []
    history.append(now)
    state[cmd_hash] = history
    count = len(history)
    if call_id:
        calls[call_id] = [now, count]
    # Keep the file bounded to the window. Every top-level key other than
    # CALLS_KEY is a fingerprint mapping to a list of attempt times, and
    # anything else is dropped here: a new bookkeeping key must be exempted
    # beside CALLS_KEY or it will not survive a single call.
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
    return count, True


def _run():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if not isinstance(data, dict) or data.get("tool_name", "") != "Bash":
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str):
        sys.exit(0)
    norm = " ".join(command.split())
    if len(norm) < MIN_CMD_LEN:
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

    # surrogatepass: a lone surrogate in a command must be counted, not crash
    cmd_hash = hashlib.md5(norm.encode("utf-8", "surrogatepass")).hexdigest()[:12]
    call_id = data.get("tool_use_id")
    if not isinstance(call_id, str) or not call_id:
        call_id = None
    now = time.time()

    lock_fd = _acquire_lock(state_path + ".lock")
    try:
        state = _load_state(state_path)
        count, changed = _count(state, cmd_hash, call_id, now)
        if changed:
            _save_state(state_path, state)
    finally:
        if lock_fd is not None:
            os.close(lock_fd)

    # Best-effort cleanup of sibling state files (with their locks, and temp
    # files a killed write left behind) older than 24h
    try:
        for pattern in ("claude-retry-budget-*.json", "claude-retry-budget-*.lock",
                        "claude-retry-budget-*.tmp"):
            for path in glob.glob(os.path.join(STATE_DIR, pattern)):
                try:
                    if now - os.path.getmtime(path) > STATE_TTL_SEC:
                        os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass

    if count >= THRESHOLD_BLOCK:
        preview = norm[:80] + ("\u2026" if len(norm) > 80 else "")
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


def main():
    try:
        _run()
    except Exception:
        # Fail open. sys.exit (the block included) raises SystemExit, which
        # is not an Exception, so it passes straight through.
        sys.exit(0)


if __name__ == "__main__":
    main()
