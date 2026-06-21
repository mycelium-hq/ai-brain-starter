#!/usr/bin/env python3
"""session-lock.py

Sibling-session coordination lock for git repos.

SessionStart mode: resolve the MAIN repo root for the session's cwd (shared
across every worktree of the repo via `git rev-parse --git-common-dir`), read
`<main_root>/.claude/.session-lock.json`, and if a DIFFERENT session touched it
within the last 5 minutes, warn that another session is active in the repo.
Then write / refresh this session's own lock.

Heartbeat mode (Stop event, or any non-SessionStart invocation): bump
`last_activity_at` on this session's lock so an actively-working session keeps
the slot warm and a sibling starting later still sees it as live. Cheap — file
I/O only, no git — via a per-session cached lock path.

WHY
---
Worktree isolation (the per-session worktree pattern) prevents the shared-HEAD
collision structurally, but two sessions can still pick the SAME repo and
clobber each other's in-flight work (the sibling-session parallel-commit
collision class). This lock is the coordination layer: it tells session 2 that
session 1 is live in the repo, BEFORE work starts. The root cause is
coordination, not a purely technical fault — so the fix is a signal, not a block.

Wiring: SessionStart (write + read + warn) AND Stop (heartbeat refresh). Always
exits 0 and emits a continue payload — never blocks session start or stop.

Bypass: SIBLING_SESSION_LOCK_BYPASS=1 (intentional parallel / collaborative work).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

BYPASS_ENV = "SIBLING_SESSION_LOCK_BYPASS"
WARN_WINDOW_SEC = 300       # warn if another session was active within 5 min
IDLE_EXPIRE_SEC = 1800      # lock considered stale after 30 min idle (documented)
CACHE_TTL_SEC = 604_800     # prune per-session cache pointers older than 7 days
GIT_TIMEOUT_SEC = 6
CACHE_DIR = os.path.expanduser("~/.claude/.cache/session-lock")
CONTINUE = '{"continue":true,"suppressOutput":true}'


def _emit(obj):
    sys.stdout.write(json.dumps(obj))


def _emit_continue():
    sys.stdout.write(CONTINUE)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        return None


def _atomic_write_json(path, obj):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _git_common_dir(cwd):
    """Absolute path to the shared git dir, or '' if cwd is not a git repo."""
    for args in (
        ["rev-parse", "--path-format=absolute", "--git-common-dir"],  # git >= 2.31
        ["rev-parse", "--git-common-dir"],
    ):
        try:
            r = subprocess.run(
                ["git", "-C", cwd] + args,
                capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return ""
        if r.returncode == 0 and r.stdout.strip():
            out = r.stdout.strip()
            if not os.path.isabs(out):
                out = os.path.normpath(os.path.join(cwd, out))
            return out
    return ""


def _main_root(cwd):
    """Main checkout root shared by all worktrees of the repo, or '' if not a repo."""
    common = _git_common_dir(cwd)
    if not common:
        return ""
    common = common.rstrip("/")
    # common is typically <main_root>/.git ; for a bare repo it is the repo dir.
    if os.path.basename(common) == ".git":
        return os.path.dirname(common)
    return common


def _cache_path(session_id):
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "unknown"
    return os.path.join(CACHE_DIR, f"{safe}.path")


def _prune_cache():
    """Delete per-session cache pointers older than CACHE_TTL_SEC (bounded growth)."""
    try:
        now = time.time()
        for name in os.listdir(CACHE_DIR):
            p = os.path.join(CACHE_DIR, name)
            try:
                if os.path.isfile(p) and (now - os.path.getmtime(p)) > CACHE_TTL_SEC:
                    os.remove(p)
            except OSError:
                continue
    except (FileNotFoundError, OSError):
        return


def _refresh(session_id):
    """Heartbeat: bump last_activity_at on our own lock. Cheap, no git."""
    if not session_id:
        return
    try:
        with open(_cache_path(session_id), "r", encoding="utf-8") as f:
            lock_path = f.read().strip()
    except OSError:
        return
    if not lock_path:
        return
    lock = _read_json(lock_path)
    if not lock or lock.get("session_id") != session_id:
        return
    lock["last_activity_at"] = time.time()
    _atomic_write_json(lock_path, lock)


def _session_start(payload):
    session_id = payload.get("session_id") or "unknown"
    cwd = (payload.get("cwd")
           or os.environ.get("CLAUDE_PROJECT_DIR")
           or os.environ.get("CLAUDE_CWD")
           or os.getcwd())
    main_root = _main_root(cwd)
    if not main_root:
        _emit_continue()
        return

    lock_path = os.path.join(main_root, ".claude", ".session-lock.json")
    now = time.time()
    existing = _read_json(lock_path)

    warn = None
    if (existing
            and existing.get("session_id") != session_id
            and isinstance(existing.get("last_activity_at"), (int, float))
            and (now - existing["last_activity_at"]) < WARN_WINDOW_SEC):
        active_min = int((now - existing["last_activity_at"]) // 60)
        started_at = existing.get("started_at")
        started_str = ""
        if isinstance(started_at, (int, float)):
            started_str = f" (started {int((now - started_at) // 60)} min ago)"
        warn = (
            "[session-lock] Another Claude session appears active in this repo:\n"
            f"  repo:          {main_root}\n"
            f"  other session: {existing.get('session_id')}\n"
            f"  last active:   {active_min} min ago{started_str}\n"
            "Two sessions on one repo risk CONCURRENT-SESSION-HEAD-DRIFT + "
            "sibling-session parallel-commit collisions. Coordinate, use a "
            "separate repo, or wait for the other session to finish.\n"
            f"Bypass: {BYPASS_ENV}=1 (intentional parallel / collaborative work)."
        )

    started_at = now
    if existing and existing.get("session_id") == session_id:
        started_at = existing.get("started_at", now)
    _atomic_write_json(lock_path, {
        "session_id": session_id,
        "started_at": started_at,
        "last_activity_at": now,
        "cwd": cwd,
        "pid": os.getpid(),
    })

    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(session_id), "w", encoding="utf-8") as f:
            f.write(lock_path)
    except OSError:
        pass
    _prune_cache()

    if warn:
        _emit({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": warn,
        }})
    else:
        _emit_continue()


def main() -> int:
    if os.environ.get(BYPASS_ENV) == "1":
        _emit_continue()
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _emit_continue()
        return 0

    try:
        if (payload.get("hook_event_name") or "") == "SessionStart":
            _session_start(payload)
        else:
            # Stop / any other invocation = activity heartbeat.
            _refresh(payload.get("session_id") or "")
            _emit_continue()
    except Exception:
        # Never break session start / stop on an internal error.
        _emit_continue()
    return 0


if __name__ == "__main__":
    sys.exit(main())
