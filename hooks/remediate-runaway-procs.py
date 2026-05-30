#!/usr/bin/env python3
"""Auto-remediation: reap clearly-orphaned runaway processes — SessionStart.

The session-start hooks SURFACE drift (unpushed commits, stashes, orphan
snapshots) but nothing FIXES it. This is the FIX side of that pair, for one
safe, high-value class: orphaned runaway processes.

The documented incident (2026-05-29): 16 orphaned `yes` processes — real parent
dead, reparented to launchd/init (PPID 1) — pinned the CPU for ~20h across a
session. Pure waste, zero recoverable output. This hook reaps that class at
every SessionStart so it can never silently burn a machine again.

NON-DESTRUCTIVE by construction — it kills a process only when it is ALL of:
  * orphaned (PPID == 1): its real parent already died, so nothing is reading
    its output and no shell will ever reap it;
  * an exact match for a known-noop runaway command (default: `yes`), whose
    whole purpose is to emit forever and whose output is never valuable;
  * older than RUNAWAY_MIN_AGE_MIN minutes (default 5) — never touches a
    just-spawned process a live pipe might still be consuming.

It NEVER kills by CPU-share guesswork, never touches a process with a living
parent, and never touches anything off the allowlist. A genuinely-busy
compiler is not this hook's business — surfacing-only for everything else.

Config:
  RUNAWAY_PROC_NAMES   comma-separated exact comm basenames (default "yes")
  RUNAWAY_MIN_AGE_MIN  minimum elapsed minutes before reaping (default 5)
Bypass: RUNAWAY_REMEDIATE_BYPASS=1

WIRING (SessionStart):
  "SessionStart": [
    {"hooks": [{
      "type": "command",
      "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/remediate-runaway-procs.py 2>/dev/null || echo '{\"continue\":true,\"suppressOutput\":true}'"
    }]}
  ]
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys


def _emit(ctx: str | None) -> int:
    print(
        json.dumps({"continue": True, "additionalContext": ctx})
        if ctx
        else json.dumps({"continue": True, "suppressOutput": True})
    )
    return 0


def _etime_to_min(etime: str) -> float:
    """Parse `ps` etime ([[dd-]hh:]mm:ss) into minutes."""
    etime = etime.strip()
    days = 0
    if "-" in etime:
        d, etime = etime.split("-", 1)
        days = int(d)
    parts = [int(p) for p in etime.split(":")]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    else:
        h, m, s = 0, 0, parts[0]
    return days * 1440 + h * 60 + m + s / 60.0


def main() -> int:
    if os.environ.get("RUNAWAY_REMEDIATE_BYPASS") == "1":
        return _emit(None)

    names = {
        n.strip()
        for n in os.environ.get("RUNAWAY_PROC_NAMES", "yes").split(",")
        if n.strip()
    }
    if not names:
        return _emit(None)
    try:
        min_age = float(os.environ.get("RUNAWAY_MIN_AGE_MIN", "5"))
    except ValueError:
        min_age = 5.0

    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,etime=,comm="],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return _emit(None)
    if out.returncode != 0:
        return _emit(None)

    reaped: list[tuple[int, str, float]] = []
    for line in out.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid_s, ppid_s, etime, comm = parts
        try:
            pid, ppid = int(pid_s), int(ppid_s)
        except ValueError:
            continue
        if ppid != 1 or os.path.basename(comm) not in names:
            continue
        try:
            age = _etime_to_min(etime)
        except (ValueError, IndexError):
            continue
        if age < min_age:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            reaped.append((pid, os.path.basename(comm), age))
        except (ProcessLookupError, PermissionError):
            continue

    if not reaped:
        return _emit(None)

    by_name = {}
    for _, c, _a in reaped:
        by_name[c] = by_name.get(c, 0) + 1
    summary = ", ".join(f"{c}×{n}" for c, n in sorted(by_name.items()))
    oldest_h = max(r[2] for r in reaped) / 60.0
    return _emit(
        f"[auto-remediate] Reaped {len(reaped)} orphaned runaway process(es) "
        f"({summary}; oldest {oldest_h:.1f}h, all PPID=1 — pure CPU waste). "
        f"This is the runaway-process class that pinned the CPU ~20h in the "
        f"2026-05-29 incident; the reap is non-destructive (their output is "
        f"never read). Tune RUNAWAY_PROC_NAMES / RUNAWAY_MIN_AGE_MIN; bypass "
        f"with RUNAWAY_REMEDIATE_BYPASS=1."
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)
