#!/usr/bin/env python3
"""Two sessions closing in the same minute must never share a session file.

detect-closing-signal pre-resolves and pre-builds the session file the model
fills at close. It named that file `<minute>-<worktree>.md` and REUSED any
non-empty file already at that path. Every session on a plain checkout has
worktree `main`, so two parallel sessions closing in the same minute were both
handed the same path.

Witnessed 2026-10-01: a session sending class recordings and a parallel session
drafting a client proposal were both handed `Sessions/2026-10-01T15-25-main.md`.
The second wrote over the first one's note, and the first session's
explicit-path commit then committed the OTHER session's content under its own
commit message. Nothing on any surface flagged it; it was caught by reading the
commit by hand.

Assertions (all driven through main(), the production caller):
  1. Two sessions closing in the same minute on the same worktree get
     DIFFERENT session files, each named with its session's short id, and a
     trivial close (nothing pre-built) records a per-session path too.
  2. A session's file is not reused by the next session: content the first
     session wrote survives the second session's close, byte for byte.
  3. Two sessions whose ids share the short prefix used in the filename still
     get different files (the tag is cosmetic; ownership is the full id).
  4. Two sessions with NO session id still get different files.
  5. The pre-built file records which session owns it.
  6. The path the model is told to fill is the path the marker records.
  7. NEGATIVE CONTROL - the SAME session closing twice in the same minute
     keeps its own file and its partial content. "Always a fresh file" would
     pass 1-4 and strand the first half of a session's note in an orphan.
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "detect_closing_signal", HOOKS / "detect-closing-signal.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failures = []

FROZEN = datetime(2026, 10, 1, 15, 25, 7)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN


SID_A = "12871536-1111-4111-8111-111111111111"
SID_B = "9f3e0c2d-2222-4222-8222-222222222222"
SID_A_TWIN = "12871536-3333-4333-8333-333333333333"  # same 8-char prefix as A


def close(session_id, vault, user_messages=99):
    """Run main() for a close signal; return (marker payload, injected context)."""
    hook_input = {"prompt": "ok bye", "cwd": str(vault)}
    if session_id is not None:
        hook_input["session_id"] = session_id
    captured = {}
    original = (sys.stdin, mod.write_marker, mod.datetime, mod.count_user_messages)
    mod.count_user_messages = lambda _path: user_messages
    # vault-root-ok: saving the caller's value to RESTORE it after the stub,
    # not resolving a vault root. The hook under test does its own resolution
    # through _lib/vault_root.py; this only keeps the test from leaking env.
    original_vr = os.environ.get("VAULT_ROOT")
    try:
        sys.stdin = io.StringIO(json.dumps(hook_input))
        os.environ["VAULT_ROOT"] = str(vault)
        mod.write_marker = lambda sid, payload: captured.update(payload)
        mod.datetime = FrozenDatetime
        buf = io.StringIO()
        with redirect_stdout(buf):
            mod.main()
    finally:
        sys.stdin, mod.write_marker, mod.datetime, mod.count_user_messages = original
        if original_vr is None:
            os.environ.pop("VAULT_ROOT", None)
        else:
            os.environ["VAULT_ROOT"] = original_vr
    try:
        ctx = json.loads(buf.getvalue()).get("hookSpecificOutput", {}).get("additionalContext", "")
    except (json.JSONDecodeError, AttributeError):
        ctx = ""
    if not captured.get("session_file"):
        # Positive control: every scenario below needs the cascade to have
        # RUN. A passthrough here (no language pack, a crash, a broken
        # harness) is not a verdict on uniqueness, so say so and stop.
        print(f"FAILED - 'ok bye' did not run the close cascade; output: {buf.getvalue()[:300]!r}")
        sys.exit(1)
    return captured, ctx


def fresh_vault(root, name):
    vault = root / name
    (vault / "⚙️ Meta").mkdir(parents=True)
    return vault


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # 1 + 2 + 5 + 6. Two sessions, same minute, same worktree.
    vault = fresh_vault(tmp, "v1")
    marker_a, ctx_a = close(SID_A, vault)
    file_a = Path(marker_a.get("session_file", ""))
    if not file_a.is_file():
        failures.append(f"session A's file was not pre-built: {file_a}")
    a_note = file_a.read_text(encoding="utf-8") + "\nSession A sent the class recordings.\n"
    file_a.write_text(a_note, encoding="utf-8")

    marker_b, ctx_b = close(SID_B, vault)
    file_b = Path(marker_b.get("session_file", ""))
    if file_a == file_b:
        failures.append(
            f"two sessions closing in the same minute were handed the SAME file "
            f"({file_a.name}) - the second one writes over the first (the bug)"
        )
    if file_a.read_text(encoding="utf-8") != a_note:
        failures.append("session B's close changed session A's file")
    if not file_b.is_file():
        failures.append(f"session B's file was not pre-built: {file_b}")
    elif SID_B not in file_b.read_text(encoding="utf-8"):
        failures.append("session B's pre-built file does not record which session owns it")
    if str(file_a) not in ctx_a or str(file_b) not in ctx_b:
        failures.append("the path the model is told to fill is not the path the marker records")
    if SID_A[:8] not in file_a.name or SID_B[:8] not in file_b.name:
        failures.append(
            f"session file names do not say whose they are ({file_a.name}, {file_b.name})"
        )

    # 1b. A trivial close (no pre-build) still records a per-session path.
    vault = fresh_vault(tmp, "v1b")
    trivial_a, _ = close(SID_A, vault, user_messages=2)
    trivial_b, _ = close(SID_B, vault, user_messages=2)
    if trivial_a.get("session_file") == trivial_b.get("session_file"):
        failures.append("two trivial closes in the same minute recorded the same session file")

    # 3. Ids sharing the filename's short prefix still never share a file.
    vault = fresh_vault(tmp, "v3")
    marker_a, _ = close(SID_A, vault)
    marker_twin, _ = close(SID_A_TWIN, vault)
    if marker_a.get("session_file") == marker_twin.get("session_file"):
        failures.append(
            "two sessions whose ids share the short filename prefix were handed "
            "the same file - ownership must be the full id, not the tag"
        )

    # 4. No session id at all: still never a shared file.
    vault = fresh_vault(tmp, "v4")
    marker_x, _ = close(None, vault)
    marker_y, _ = close(None, vault)
    if marker_x.get("session_file") == marker_y.get("session_file"):
        failures.append("two sessions with no session id were handed the same file")

    # 7. NEGATIVE CONTROL - the same session closing twice keeps its own file.
    vault = fresh_vault(tmp, "v7")
    first, _ = close(SID_A, vault)
    own = Path(first.get("session_file", ""))
    partial = own.read_text(encoding="utf-8") + "\nHalf-written note from the first close.\n"
    own.write_text(partial, encoding="utf-8")
    second, _ = close(SID_A, vault)
    if second.get("session_file") != str(own):
        failures.append(
            "the same session closing twice in one minute got a NEW file - its "
            "first half is stranded in an orphan"
        )
    if own.read_text(encoding="utf-8") != partial:
        failures.append("the same session's second close wiped its own partial note")
    sessions = sorted(p.name for p in (vault / "⚙️ Meta" / "Sessions").glob("*.md"))
    if len(sessions) != 1:
        failures.append(f"the same session closing twice left {len(sessions)} files: {sessions}")

if failures:
    print("FAILED - session file must be unique per session:")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)
print("OK - parallel sessions closing in the same minute never share a session file")
