#!/usr/bin/env python3
"""The SessionStart restart witness must stamp ONLY on source == "startup".

_lib/session_startup_stamp.record() is gate 3 on scripts/ai-brain-auto-update.py's
deferred hook deploy (MYC-4704 follow-up). The updater refuses to merge a staged
upstream pull until a genuine new process is witnessed AFTER the pull was staged.
If this stamped on the wrong event the updater would activate unreviewed upstream
code mid-conversation -- the exact defect the deferral exists to close -- so
"which source values stamp" IS the security contract.

MEASURED payload this is written against (Claude Code 2.1.246/2.1.258,
2026-09-16, probe SessionStart hook under a sandboxed HOME):

    {"session_id":"...","transcript_path":"...","cwd":"...",
     "scratchpad_dir":"...","hook_event_name":"SessionStart","source":"startup"}

Covered:
  1. source=startup            -> startup stamp written; seen source_present=true
  2. resume/compact/clear/fork -> seen written, startup stamp NOT written
  3. NEGATIVE CONTROL for (2): a pre-existing stamp is not ADVANCED by a
     non-startup event. Asserting only "no file" passes vacuously on a fresh
     dir even if the code stamped unconditionally.
  4. absent `source` -> seen records source_present=false. That is what lets the
     updater tell an old harness from a machine that never restarts; without it
     the deploy would wedge forever instead of falling back.
  5. malformed payloads (None, list, str) -> no raise, nothing stamped
  6. unwritable state dir -> no raise
  7. ACTIVATION: hooks/surface-deployed-hooks-behind.py -- the SessionStart hook
     this is folded into -- actually CALLS it. Without this the module is dead
     code that every other test here would still pass (bug class
     ARTIFACT-WITHOUT-ACTIVATION); the fold is the only thing wiring it, since
     it has no hooks.json entry of its own by design.
  8. CONTRACT: the two filenames match scripts/ai-brain-auto-update.py's. They
     are duplicated, not imported (the updater must keep working via its
     standalone .sh delegator), so nothing but this test connects them, and a
     rename would silently downgrade the updater to the weaker gate forever.

Run: python3 hooks/test_session_startup_stamp.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))
from _lib.session_startup_stamp import (  # noqa: E402
    record, SEEN_NAME, STARTUP_NAME,
)

HOST = HOOKS / "surface-deployed-hooks-behind.py"
UPDATER = HOOKS.parent / "scripts" / "ai-brain-auto-update.py"


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main() -> int:
    failures: list[str] = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Every state dir this test creates, recorded as it is made.
        # The stray-tempfile check below walks THESE, not the tree: a
        # recursive rglob that reaches a read is exactly what
        # tests/integration/test_cloud_safe_file_walkers.sh forbids,
        # because such a walk blocks forever on a cloud-sync placeholder
        # (Google Drive / iCloud). A test knows the directories it made;
        # it has no reason to go looking.
        used: list[Path] = []

        def newdir(name: str) -> Path:
            d = root / name
            d.mkdir()
            used.append(d)
            return d

        # ---- 1. startup stamps -------------------------------------------
        d = newdir("startup")
        record({"session_id": "s1", "hook_event_name": "SessionStart",
                "source": "startup"}, d)
        stamp, seen = read_json(d / STARTUP_NAME), read_json(d / SEEN_NAME)
        check(isinstance(stamp, dict) and isinstance(stamp.get("at"), (int, float)),
              "source=startup wrote no startup stamp carrying `at` -- gate 3 "
              "could never clear and no deploy would ever activate")
        check(isinstance(seen, dict) and seen.get("source_present") is True,
              "source=startup did not record source_present=true -- the updater "
              "would treat the witness as unavailable and silently fall back")

        # ---- 2 + 3. non-startup never stamps, never ADVANCES --------------
        for src in ("resume", "compact", "clear", "fork"):
            d = newdir(f"src-{src}")
            planted = 1000.0
            (d / STARTUP_NAME).write_text(
                json.dumps({"schema": 1, "at": planted, "session_id": "old"}),
                encoding="utf-8")
            record({"session_id": "s2", "source": src}, d)
            after = read_json(d / STARTUP_NAME)
            check(isinstance(after, dict) and after.get("at") == planted,
                  f"source={src} ADVANCED the startup stamp -- a non-startup "
                  f"SessionStart must not count as a restart; compaction "
                  f"advancing this is exactly the hole gate 3 closes")
            check(read_json(d / SEEN_NAME) is not None,
                  f"source={src} wrote no seen file")

        d = newdir("compact-fresh")
        record({"source": "compact"}, d)
        check(not (d / STARTUP_NAME).exists(),
              "source=compact created a startup stamp on a fresh install")

        # ---- 4. absent `source` ------------------------------------------
        d = newdir("nosource")
        record({"session_id": "s3", "hook_event_name": "SessionStart"}, d)
        seen = read_json(d / SEEN_NAME)
        check(isinstance(seen, dict) and seen.get("source_present") is False,
              "an absent `source` did not record source_present=false -- the "
              "updater could not tell an old harness from a machine that never "
              "restarts, and would wedge the deploy forever")
        check(not (d / STARTUP_NAME).exists(),
              "an absent `source` still wrote a startup stamp -- an old harness "
              "would look permanently 'just restarted'")

        # ---- 5. malformed payloads ---------------------------------------
        for label, bad in (("None", None), ("list", ["startup"]),
                           ("str", "startup"), ("nested", {"source": {"x": 1}})):
            d = newdir(f"bad-{label}")
            try:
                record(bad, d)  # type: ignore[arg-type]
            except Exception as exc:
                check(False, f"payload {label} raised {exc!r} -- a SessionStart "
                             f"hook that crashes breaks every session start")
            check(not (d / STARTUP_NAME).exists(),
                  f"payload {label} wrote a startup stamp")

        # ---- 6. unwritable state dir -------------------------------------
        d = newdir("ro"); os.chmod(d, 0o500)
        try:
            record({"source": "startup"}, d)
        except Exception as exc:
            check(False, f"unwritable state dir raised {exc!r}")
        finally:
            os.chmod(d, 0o700)

        strays = [e.name for d in used for e in d.iterdir()
                  if ".tmp" in e.name]
        check(not strays, f"left temp files behind: {strays[:3]}")

        # ---- 7. ACTIVATION: the host hook actually calls it ---------------
        if HOST.is_file():
            hd = newdir("host")
            home = root / "host-home"; (home / ".claude").mkdir(parents=True)
            env = dict(os.environ)
            env["ABS_UPDATE_STATE_DIR"] = str(hd)
            # USERPROFILE alongside HOME: on Windows Path.home() reads
            # USERPROFILE, so redirecting HOME alone leaves this test
            # writing stamp files into the operator's REAL ~/.claude.
            # scripts/ci.sh gates exactly this (HOME-only sandbox).
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            try:
                res = subprocess.run(
                    [sys.executable, str(HOST)],
                    input=json.dumps({"session_id": "host-1",
                                      "hook_event_name": "SessionStart",
                                      "source": "startup"}),
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", env=env, timeout=120)
                check(res.returncode == 0,
                      f"host hook exited {res.returncode}: {res.stderr[:200]}")
                check((hd / STARTUP_NAME).exists(),
                      "surface-deployed-hooks-behind.py did NOT write the "
                      "startup stamp -- the witness is dead code, since the "
                      "fold into that hook is the only thing that wires it")
            except subprocess.TimeoutExpired:
                check(False, "host hook timed out")
        else:
            check(False, f"host hook missing at {HOST}")

    # ---- 8. filename contract with the updater ---------------------------
    if UPDATER.is_file():
        spec = importlib.util.spec_from_file_location("_abs_auto_update", UPDATER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        check(getattr(mod, "SEEN_NAME", None) == SEEN_NAME,
              f"updater SEEN_NAME={getattr(mod, 'SEEN_NAME', None)!r} != "
              f"{SEEN_NAME!r} -- the witness writes a file nobody reads and the "
              f"gate silently degrades to two factors")
        check(getattr(mod, "STARTUP_NAME", None) == STARTUP_NAME,
              f"updater STARTUP_NAME={getattr(mod, 'STARTUP_NAME', None)!r} != "
              f"{STARTUP_NAME!r} -- same silent degradation")
    else:
        check(False, f"updater missing at {UPDATER} -- cannot verify the "
                     f"filename contract, the only link between writer and reader")

    if failures:
        print("FAILED - session startup witness:")
        for f in failures:
            print("  x " + f)
        return 1
    print("OK - the witness stamps only on source=startup, never advances on "
          "resume/compact/clear/fork, reports an absent `source` so the updater "
          "falls back, survives malformed payloads and an unwritable state dir, "
          "is actually invoked by its host SessionStart hook, and its filenames "
          "match the updater's")
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
