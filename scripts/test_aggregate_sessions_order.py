#!/usr/bin/env python3
"""
Regression test for the order of sessions in scripts/aggregate-sessions.py.

gather_session_files() sorted by the raw file name. A session file whose name
does not start with the standard YYYY-MM-DDTHH-MM stamp (a hand-named
`notes-2026-04-20.md`, or the compact `20260603-1823-slug.md` and
`20260503T2108-slug.md`) sorted ahead of every dated session, so Last
Session.md kept showing the same old sessions while the newer ones never
appeared. A name with no date sorts last, and a run of digits inside a slug
is not read as a date.

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
    "---\ncreationDate: {date}\ntype: session\nworktree: main\n"
    'session_label: "{label}"\n---\n\n# Session\n'
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        filled = {
            "2026-10-29T20-39-main.md": "2026-10-29 20:39",
            "2026-10-29T22-03-docs.md": "2026-10-29 22:03",
            "2026-10-29-handoff.md": "2026-10-29",
            "20260603-1823-slug-0a1b2c.md": "2026-06-03 18:23",
            "20260503T2108-slug-9f8e7d.md": "2026-05-03 21:08",
            "2026-05-01T0007-launch.md": "2026-05-01 00:07",
            "notes-test-2026-04-20.md": "2026-04-20",
            "notes-12345678-undated.md": "2026-01-01",
        }
        for name, date in filled.items():
            (d / name).write_text(SESSION.format(date=date, label="filled"), encoding="utf-8")
        (d / "2026-10-30T01-00-main.md").write_text(
            SESSION.format(date="2026-10-30 01:00", label="update pending"), encoding="utf-8"
        )
        ag.SESSIONS_DIR = d
        got = [p.name for p in ag.gather_session_files()]

    want = [
        "2026-10-29T22-03-docs.md",
        "2026-10-29T20-39-main.md",
        "2026-10-29-handoff.md",
        "20260603-1823-slug-0a1b2c.md",
        "20260503T2108-slug-9f8e7d.md",
        "2026-05-01T0007-launch.md",
        "notes-test-2026-04-20.md",
        "notes-12345678-undated.md",
    ]
    if got != want:
        print(f"  FAIL newest session first, whatever the name's shape\n    want {want}\n    got  {got}")
        return 1
    print("  ok   newest session first, whatever the name's shape; the unfilled stub stays out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
