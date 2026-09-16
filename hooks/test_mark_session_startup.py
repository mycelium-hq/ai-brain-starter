#!/usr/bin/env python3
"""mark-session-startup must stamp a restart ONLY on source == "startup".

This hook is the third gate on scripts/ai-brain-auto-update.py's deferred hook
deploy (MYC-4704 follow-up). The updater refuses to merge a staged upstream
pull until a genuine new process has been witnessed AFTER the pull was staged.
If this hook stamped on the wrong event, the updater would activate unreviewed
upstream code mid-conversation -- the exact defect the deferral exists to
close -- so "which source values stamp" is the whole security contract.

MEASURED payload shape this is written against (Claude Code 2.1.246/2.1.258,
2026-09-16, probe SessionStart hook under a sandboxed HOME):

    {"session_id":"...","transcript_path":"...","cwd":"...",
     "scratchpad_dir":"...","hook_event_name":"SessionStart",
     "source":"startup"}

Covered:
  1. source=startup                  -> startup stamp written, seen written
  2. resume/compact/clear/fork       -> seen written, startup stamp NOT written
  3. NEGATIVE CONTROL for (2): a pre-existing startup stamp is not ADVANCED by
     a non-startup event. Asserting only "no file" would pass vacuously on a
     fresh dir even if the hook stamped unconditionally.
  4. absent `source` (an older harness) -> seen records source_present=false,
     which is what makes the updater fall back instead of wedging forever
  5. empty / non-JSON stdin          -> exit 0, valid JSON, nothing stamped
  6. unwritable state dir            -> exit 0, valid JSON (a SessionStart hook
     that crashed would break every session start on the install)
  7. CONTRACT: the two stamp filenames here are byte-identical to the ones
     scripts/ai-brain-auto-update.py reads. They are duplicated, not imported
     (the updater must keep working via its standalone .sh delegator), so
     nothing but a test connects them -- and a rename would not fail loudly,
     it would silently downgrade the updater to the weaker two-factor gate
     forever.

Run: python3 hooks/test_mark_session_startup.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "mark-session-startup.py"
UPDATER = Path(__file__).resolve().parent.parent / "scripts" / "ai-brain-auto-update.py"

SEEN = ".ai-brain-starter-sessionstart-seen"
STARTUP = ".ai-brain-starter-session-startup"


def run_hook(state: Path, payload, **env_overrides) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["ABS_UPDATE_STATE_DIR"] = str(state)
    env.update(env_overrides)
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK)], input=data,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=30)


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

    def emits_valid_json(res, label):
        check(res.returncode == 0, f"{label}: exit {res.returncode}, expected 0")
        try:
            json.loads(res.stdout)
        except ValueError:
            check(False, f"{label}: stdout is not valid JSON: {res.stdout!r}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # ---- 1. startup stamps -------------------------------------------
        st = root / "startup"; st.mkdir()
        res = run_hook(st, {"session_id": "s1", "hook_event_name": "SessionStart",
                            "source": "startup"})
        emits_valid_json(res, "source=startup")
        stamp = read_json(st / STARTUP)
        seen = read_json(st / SEEN)
        check(isinstance(stamp, dict) and isinstance(stamp.get("at"), (int, float)),
              "source=startup did not write a startup stamp carrying `at` -- "
              "gate 3 can never clear, so no deploy would ever activate")
        check(isinstance(seen, dict) and seen.get("source_present") is True,
              "source=startup did not record source_present=true in the seen "
              "file -- the updater would treat the witness as unavailable and "
              "silently fall back to the weaker two-factor gate")

        # ---- 2 + 3. non-startup sources never stamp, and never ADVANCE ----
        for src in ("resume", "compact", "clear", "fork"):
            d = root / f"src-{src}"; d.mkdir()
            planted = 1000.0
            (d / STARTUP).write_text(json.dumps({"schema": 1, "at": planted,
                                                 "session_id": "old"}),
                                     encoding="utf-8")
            res = run_hook(d, {"session_id": "s2", "hook_event_name": "SessionStart",
                               "source": src})
            emits_valid_json(res, f"source={src}")
            after = read_json(d / STARTUP)
            check(isinstance(after, dict) and after.get("at") == planted,
                  f"source={src} ADVANCED the startup stamp "
                  f"({after.get('at') if isinstance(after, dict) else after!r} "
                  f"!= planted {planted}). A non-startup SessionStart must not "
                  f"count as a restart -- compaction advancing this is exactly "
                  f"the hole gate 3 exists to close")
            check(read_json(d / SEEN) is not None,
                  f"source={src} did not write the seen file")

        # fresh-dir form of the same assertion (no plant to inherit)
        d = root / "compact-fresh"; d.mkdir()
        run_hook(d, {"session_id": "s2", "source": "compact"})
        check(not (d / STARTUP).exists(),
              "source=compact created a startup stamp on a fresh install")

        # ---- 4. absent `source` (older harness) --------------------------
        d = root / "nosource"; d.mkdir()
        res = run_hook(d, {"session_id": "s3", "hook_event_name": "SessionStart"})
        emits_valid_json(res, "no source key")
        seen = read_json(d / SEEN)
        check(isinstance(seen, dict) and seen.get("source_present") is False,
              "an absent `source` did not record source_present=false -- the "
              "updater could not distinguish an old harness from a machine "
              "that never restarts, and would wedge the deploy forever")
        check(not (d / STARTUP).exists(),
              "an absent `source` still wrote a startup stamp -- an older "
              "harness would be treated as permanently 'just restarted'")

        # ---- 5. empty / non-JSON stdin -----------------------------------
        for label, payload in (("empty stdin", ""), ("non-JSON stdin", "not json")):
            d = root / label.replace(" ", "-"); d.mkdir()
            res = run_hook(d, payload)
            emits_valid_json(res, label)
            check(not (d / STARTUP).exists(),
                  f"{label} wrote a startup stamp")

        # ---- 6. unwritable state dir -------------------------------------
        d = root / "ro"; d.mkdir()
        target = d / "locked"
        target.mkdir()
        os.chmod(target, 0o500)
        try:
            res = run_hook(target, {"session_id": "s4", "source": "startup"})
            emits_valid_json(res, "unwritable state dir")
        finally:
            os.chmod(target, 0o700)

        # no stray temp files anywhere
        strays = [str(p) for p in root.rglob("*.tmp*")]
        check(not strays, f"left temp files behind: {strays[:3]}")

    # ---- 7. filename contract with the updater ---------------------------
    if UPDATER.is_file():
        spec = importlib.util.spec_from_file_location("_abs_auto_update", UPDATER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        check(getattr(mod, "SEEN_NAME", None) == SEEN,
              f"updater SEEN_NAME={getattr(mod, 'SEEN_NAME', None)!r} != "
              f"{SEEN!r} -- the witness writes a file nobody reads, and the "
              f"deploy gate silently degrades to two factors")
        check(getattr(mod, "STARTUP_NAME", None) == STARTUP,
              f"updater STARTUP_NAME={getattr(mod, 'STARTUP_NAME', None)!r} != "
              f"{STARTUP!r} -- same silent degradation")
        hook_src = HOOK.read_text(encoding="utf-8")
        check(f'SEEN_NAME = "{SEEN}"' in hook_src
              and f'STARTUP_NAME = "{STARTUP}"' in hook_src,
              "the hook's own constants drifted from the names this test pins")
    else:
        check(False, f"updater not found at {UPDATER} -- cannot verify the "
                     f"filename contract, which is the only thing connecting "
                     f"the witness to its reader")

    if failures:
        print("FAILED - mark-session-startup:")
        for f in failures:
            print("  x " + f)
        return 1
    print("OK - mark-session-startup stamps only on source=startup, never "
          "advances on resume/compact/clear/fork, reports an absent `source` "
          "so the updater can fall back, survives bad stdin and an unwritable "
          "state dir, and its stamp filenames match the updater's")
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
