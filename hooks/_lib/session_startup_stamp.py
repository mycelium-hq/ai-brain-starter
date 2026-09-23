"""Record that a GENUINELY NEW Claude Code process began.

Read by scripts/ai-brain-auto-update.py as gate 3 on its deferred hook deploy
(MYC-4704 follow-up). That updater stages an upstream pull and refuses to merge
it until a new session is proven, because merging rewrites the very checkout
most of this skill's hook commands invoke directly. Its first two gates -- a
differing session_id and an elapsed-time minimum -- could not tell a genuine
restart from a long session that auto-compacted past the delay. This supplies
the signal that can.

MEASURED payload (Claude Code 2.1.246/2.1.258, 2026-09-16, probe SessionStart
hook under a sandboxed HOME):

    {"session_id":"...","transcript_path":"...","cwd":"...",
     "scratchpad_dir":"...","hook_event_name":"SessionStart",
     "source":"startup"}

`source` is carried in the payload. Documented values: startup / resume /
clear / compact / fork. ONLY `startup` counts as a restart here. `fork` is
excluded deliberately: it is a new process, but it inherits the parent
conversation, so it is not the "a human could have intervened" boundary the
deploy gate is about.

WHY THIS IS A _lib MODULE AND NOT ITS OWN HOOK. It was first written as a
standalone SessionStart hook with "matcher": "startup". That is the cheapest
possible trigger, but it still adds one entry to the SessionStart fan-out, and
footprint-budgets.json's own rationale for the previous raise ends with a
standing instruction: "this raise consumes the last of the SessionStart
headroom ... the next SessionStart addition should optimize the fan-out
(Stage 2: precise triggers / async / dispatcher) rather than raise again."
So it is folded into hooks/surface-deployed-hooks-behind.py, which already
reads this exact payload, already covers the update/deploy domain, and whose
own comment states the precedent: "Three fail-open checks under one 'update
check' surface ... Same hook, so SessionStart fan-out stays flat (MYC-2348)."
This is the fourth. Fan-out is unchanged at 19.

FAIL-SAFE DIRECTION. Every failure here -- no payload, absent `source`, an
unwritable state dir -- leaves the startup stamp un-advanced. The updater reads
a missing or older stamp as "no restart yet", and when the witness is
unavailable entirely it falls back to its pre-existing two-factor gate. So a
broken stamp can only ever DELAY a deploy, never trigger one early. Nothing
this module can do makes the updater less careful than it was without it.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

SEEN_NAME = ".ai-brain-starter-sessionstart-seen"
STARTUP_NAME = ".ai-brain-starter-session-startup"

# The one value that means "a new OS process began". See the module docstring
# for why `fork` is excluded despite also being a new process.
STARTUP_SOURCE = "startup"


def state_dir() -> Path:
    """Resolved EXACTLY as scripts/ai-brain-auto-update.py resolves it. These
    files are a contract between the two; if this drifts from that, the updater
    reads a stamp nobody writes and silently degrades to the weaker gate
    forever. hooks/test_session_startup_stamp.py pins them together."""
    return Path(os.environ.get("ABS_UPDATE_STATE_DIR") or (Path.home() / ".claude"))


def _write_json(path: Path, payload: dict) -> None:
    """Atomic-ish write: a half-written stamp read by a concurrent updater must
    never parse as VALID but wrong. Never raises."""
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def record(payload: dict, state: Path | None = None) -> None:
    """Record a SessionStart. Writes TWO single-writer files, so neither needs a
    read-modify-write (which would race between sessions starting at once):

      SEEN_NAME     every invocation. Its existence proves the witness is wired
                    and firing; `source_present` proves this harness carries the
                    field at all. Without that second fact an older Claude Code
                    would be indistinguishable from a machine that never
                    restarts, and the deploy would wedge forever instead of
                    falling back.
      STARTUP_NAME  only on an explicit source == "startup". Any other value, or
                    an absent field, leaves the previous stamp untouched -- which
                    reads downstream as "no restart since the pull was staged".

    Never raises: the caller is a SessionStart hook, and one that crashed would
    break every session start on the install.
    """
    try:
        if not isinstance(payload, dict):
            payload = {}
        src = payload.get("source")
        src = src if isinstance(src, str) else None
        session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
        now = time.time()
        target = state if state is not None else state_dir()

        _write_json(target / SEEN_NAME, {
            "schema": 1,
            "at": now,
            "source": src or "",
            "source_present": src is not None,
            "session_id": session_id,
        })
        if src == STARTUP_SOURCE:
            _write_json(target / STARTUP_NAME, {
                "schema": 1,
                "at": now,
                "session_id": session_id,
            })
    except Exception:
        pass
