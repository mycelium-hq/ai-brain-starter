#!/usr/bin/env python3
"""mark-session-startup.py — SessionStart hook. Records that a GENUINELY NEW
Claude Code process began, so scripts/ai-brain-auto-update.py can gate a
deferred hook deploy on a REAL restart instead of an elapsed-time proxy.

WHY THIS EXISTS (MYC-4704 follow-up). ai-brain-auto-update.py stages an
upstream pull and refuses to merge it until a LATER invocation proves the
session changed -- because merging rewrites the very checkout most of this
skill's hook commands in settings.json read directly, so merging inline means
new, unreviewed code runs on the next hook event seconds later. Its first
implementation proved "the session changed" with two weak signals: a differing
`session_id`, plus >= ABS_UPDATE_MIN_DEPLOY_DELAY_SECONDS of elapsed time. It
documented, honestly, that neither proves a restart: a long-running session
that auto-compacts past the delay could still activate mid-conversation.

This hook supplies the signal that was missing. MEASURED on this harness
(Claude Code 2.1.246/2.1.258, 2026-09-16) by registering a probe SessionStart
hook under a sandboxed HOME and reading the bytes it received on stdin:

    {"session_id":"...","transcript_path":"...","cwd":"...",
     "scratchpad_dir":"...","hook_event_name":"SessionStart",
     "source":"startup"}

`source` IS carried in the payload. Its documented values are startup /
resume / clear / compact / fork; only `startup` (a fresh process) is treated
here as a restart. `fork` is deliberately NOT trusted: a fork inherits the
parent conversation, so it is not the "a human could have intervened"
boundary this gate is about.

The same probe measured that SessionStart `matcher` is honored and FILTERS:
a block with "matcher": "compact" did not fire on a startup, while an
unmatched block and a "matcher": "startup" block both did, byte-identically.
So this hook is wired with "matcher": "startup" (it costs one invocation per
genuine start, not one per session-segment -- ADR-0004/0005 footprint), AND
re-checks `source` from the payload itself. Belt and braces: a harness that
ignored an unknown matcher and fired this on a compaction would still be
caught by the payload check, because only an explicit source == "startup"
writes the startup stamp.

TWO FILES, deliberately separate, each written by a single writer so neither
needs a read-modify-write (which would race between two sessions starting at
once):

  .ai-brain-starter-sessionstart-seen   written on EVERY invocation. Its
      existence answers "is this signal wired and firing on this install at
      all?", and `source_present` answers "does this harness actually carry
      the field?". A harness too old to emit `source` therefore reports
      itself, rather than silently looking like "no restart has happened yet".

  .ai-brain-starter-session-startup     written ONLY on an explicit
      source == "startup". Carries the wall-clock time of that start, which
      is what the updater compares against the time it staged the pull.

FAIL-SAFE DIRECTION. Every failure here (no stdin, unparseable JSON, absent
`source`, unwritable state dir) results in the startup stamp NOT advancing.
The updater treats a missing/older stamp as "no restart yet" and, when the
signal is unavailable entirely, falls back to the pre-existing elapsed-time
gate -- so a broken or absent stamp can only ever DELAY a deploy, never
activate one early. There is no input to this hook that makes the updater
less careful than it was before this file existed.

Always exits 0 and prints one valid hook JSON object: a SessionStart hook
that blocked or crashed would break every session start on the install.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# The harness owns this payload; a cap only bounds a pathological stdin.
_MAX_STDIN = 1 << 20

SEEN_NAME = ".ai-brain-starter-sessionstart-seen"
STARTUP_NAME = ".ai-brain-starter-session-startup"

# The one value that means "a new OS process began". See the docstring for why
# `fork` is excluded despite also being a new process.
STARTUP_SOURCE = "startup"


def _state_dir() -> Path:
    """Resolved EXACTLY as scripts/ai-brain-auto-update.py resolves it. These
    two files are a contract between the two; if this resolution ever drifts
    from that one, the updater reads a stamp nobody writes and silently falls
    back to the weaker gate forever."""
    return Path(os.environ.get("ABS_UPDATE_STATE_DIR") or (Path.home() / ".claude"))


def _silent() -> None:
    sys.stdout.write('{"continue": true, "suppressOutput": true}')
    sys.exit(0)


def _read_payload() -> dict:
    """Best-effort dict from the hook's stdin JSON; {} if unavailable.

    Reads RAW BYTES and decodes UTF-8 explicitly -- text-mode sys.stdin
    decodes with the locale codepage (cp1252 on a default Windows console),
    the same read-side bug already fixed in hooks/detect-closing-signal.py
    (#314/#483) and mirrored in ai-brain-auto-update.py's _read_session_id.
    """
    try:
        buf = getattr(sys.stdin, "buffer", None)
        raw = (buf.read(_MAX_STDIN).decode("utf-8", errors="replace")
               if buf is not None else sys.stdin.read(_MAX_STDIN))
        if not raw.strip():
            return {}
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict) -> None:
    """Atomic-ish write: a partially-written stamp read by a concurrent
    updater must never parse as a VALID but wrong record. Never raises --
    a stamp failure must not break the session it is only observing."""
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


def run() -> None:
    payload = _read_payload()
    source = payload.get("source")
    source = source if isinstance(source, str) else None
    session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
    now = time.time()
    state = _state_dir()

    # Written unconditionally: proves the signal is wired AND whether this
    # harness carries `source` at all.
    _write_json(state / SEEN_NAME, {
        "schema": 1,
        "at": now,
        "source": source or "",
        "source_present": source is not None,
        "session_id": session_id,
    })

    # Written ONLY on an explicit fresh start. Any other value (resume,
    # compact, clear, fork) or an absent field leaves the previous stamp in
    # place, which reads downstream as "no restart since the pull was staged".
    if source == STARTUP_SOURCE:
        _write_json(state / STARTUP_NAME, {
            "schema": 1,
            "at": now,
            "session_id": session_id,
        })

    _silent()


def main() -> None:
    try:
        run()
    except SystemExit:
        raise
    except Exception:
        _silent()


if __name__ == "__main__":
    # ai-brain-starter#313 cp1252 class: a default Windows console encodes
    # stdout as cp1252 and dies on the first non-ASCII byte. This hook's own
    # output is ASCII JSON, but the guard is cheap and the file is a template
    # that gets edited downstream.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    main()
