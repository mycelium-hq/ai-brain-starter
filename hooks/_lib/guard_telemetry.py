#!/usr/bin/env python3
"""Opt-in guard fire+status logger -> ~/.claude/guard-fires.jsonl  (MYC-285).

The forward path for fleet fire telemetry. Read by
`⚙️ Meta/scripts/guard-fleet-telemetry.py` to compute per-guard fire counts +
the dead-guard / uninstrumented split. Hookify rules are instrumented by
construction (the dispatcher logs every match); STANDALONE hooks are not — this
closes that gap one hook at a time.

ADOPT in a standalone hook by adding ONE line at its fire/decision point:

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # if not already
    from _lib.guard_telemetry import log_fire
    log_fire("my-hook-basename", status="warned")   # blocked / fired / bypassed

status taxonomy (mirrors hookify + pre-push-doubt so heeded-vs-bypassed math
works fleet-wide): "fired" (default) · "warned" · "blocked" · "bypassed".

FAIL-OPEN by construction. A telemetry write must NEVER break a fail-open hook,
so every error is swallowed silently. Use the hook's own basename (sans .py) as
`name` so the report attributes fires to the right guard.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

LOG_PATH = os.environ.get(
    "GUARD_FIRES_LOG", os.path.expanduser("~/.claude/guard-fires.jsonl"))


def log_fire(name, status="fired", **ctx):
    """Append one fire record. Returns True on write, False on any failure.

    ctx values that aren't JSON-serializable are coerced to str so a bad
    extra field can never drop the record.
    """
    try:
        rec = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(),
            "name": str(name),
            "status": str(status),
        }
        for k, v in ctx.items():
            try:
                json.dumps(v)
            except (TypeError, ValueError):
                v = str(v)
            rec[k] = v
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False
