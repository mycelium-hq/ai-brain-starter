#!/usr/bin/env python3
"""
Regression test for the order of sessions in scripts/aggregate-sessions.py.

gather_session_files() sorted by the raw file name. A session file whose name
does not start with the standard YYYY-MM-DDTHH-MM stamp (a hand-named
`notes-2026-04-20.md`, or the compact `20260603-1823-slug.md` and
`20260503T2108-slug.md`) sorted ahead of every dated session, so Last
Session.md kept showing the same old sessions while the newer ones never
appeared. Names whose digits are not a real date (`30102026-...`, a ticket
number like `myc-4704-10-30`) must not take the top either: they count as
undated and sort last.

The check FAILS against the previous aggregate-sessions.py (verified by
running this file against it).

Plain script, no pytest (the CI job runs scripts/test_*.py directly on 3.9).
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("aggregate_sessions", HERE / "aggregate-sessions.py")
ag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ag)

SESSION = (
    "---\ncreationDate: 2026-01-01\ntype: session\nworktree: main\n"
    'session_label: "{label}"\n---\n\n# Session\n'
)

# Newest first, the order Last Session.md must use. Two sessions in the same
# minute fall back to the name (descending); names with no real date in them
# come last.
WANT = [
    "2026-10-29T22-03-docs.md",
    "2026-10-29T20-39-main.md",
    "2026-10-29T20-39-main-bbbb2222.md",
    "2026-10-29-handoff.md",
    "20260603-1823-slug-0a1b2c.md",
    "20260603-1823-notes-2026-04-20.md",
    "20260503T2108-slug-9f8e7d.md",
    "2026-05-01T0007-launch.md",
    "notes-test-2026-04-20.md",
    "notes-12345678-undated.md",
    "myc-4704-10-30.md",
    "99999999-foo.md",
    "30102026-reunion.md",
]


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for name in reversed(WANT):
            (d / name).write_text(SESSION.format(label="filled"), encoding="utf-8")
        (d / "2026-10-30T01-00-main.md").write_text(
            SESSION.format(label="update pending"), encoding="utf-8"
        )
        ag.SESSIONS_DIR = d
        got = [p.name for p in ag.gather_session_files()]

    if got != WANT:
        print(f"  FAIL newest session first, whatever the name's shape\n    want {WANT}\n    got  {got}")
        return 1
    print("  ok   newest session first, whatever the name's shape; the unfilled stub stays out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
