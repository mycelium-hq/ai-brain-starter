#!/usr/bin/env python3
"""
test_graphify_canonicalize_slash_guard.py — stdlib-only regression tests for
strip_folder_prefix() in graphify_canonicalize.py.

Run: python3 tests/test_graphify_canonicalize_slash_guard.py
No pytest dependency. Exits non-zero on any failure. Touches no real vault.

Why this file exists
--------------------
strip_folder_prefix() keeps whatever follows the last "/" so that a path-form
wikilink ([[Curiosities/Colombia]]) and a bare one ([[Colombia]]) collapse onto
one node. That is right for English vaults, where "/" in a label is a path.

It is wrong the moment the corpus is not in English. Spanish, Portuguese,
French and German write dates as DD/MM/YYYY and rates as "$49/mes", "$400/h":

    "Sesion del 24/08/2026"  ->  "2026"
    "semana 08/09"           ->  "09"
    "$49/mes"                ->  "mes"
    "$400/h"                 ->  "h"

Every dated note in the corpus then canonicalizes onto the SAME node, and the
merge makes them all neighbours of each other. Measured on an 8,858-node
Spanish vault: 12 supernodes absorbing 119 edges that appear in no source
document. "2026" came out as the #7 god node with 31 edges, joining notes with
nothing in common.

That is the part worth a regression test. A junk row in the wikilink-gap report
is cosmetic and a human filters it; a false edge is not, because community
detection and the "surprising connections" report both consume it and neither
has any way to tell it apart from a real one.

The guard: a digit immediately before the "/" means the label is not a path,
plus a small unit-tail set for the "$49/mes" shape. The COLLAPSES cases below
are the behaviour that must survive the fix.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

# The repo ships this script twice. Both are patched; test both so a fix to one
# copy cannot silently leave the other behind.
_COPIES = {
    "skills": _REPO / "skills/graphify/scripts/graphify_canonicalize.py",
    "scripts": _REPO / "scripts/graphify_canonicalize.py",
}


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"gc_{path.parent.name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MODULES = {name: _load(p) for name, p in _COPIES.items() if p.exists()}
assert MODULES, "no copy of graphify_canonicalize.py found"

# label -> must come back UNCHANGED (the "/" is a date or a rate, not a path)
PRESERVES = {
    "Sesion del 24/08/2026": "a Spanish date collapses the whole corpus onto one node",
    "Reunion 28/08/2026 con Raul": "date mid-label",
    "semana 08/09": "day/month with no year",
    "10/09": "bare day/month",
    "$49/mes": "monthly rate",
    "$400/h": "hourly rate",
    "wholesale $48,76/mes": "rate with a decimal comma",
    "20 km/h": "unit over unit",
    "1/2 jornada": "fraction",
}

# label -> expected tail (a real path-form wikilink; behaviour must not change)
COLLAPSES = {
    "Curiosities/Colombia": "Colombia",
    "CRM/Jane Doe": "Jane Doe",
    "Notes/Floors/Love": "Love",
    "folder/sub/Deep Note": "Deep Note",
}

UNTOUCHED = ("Newmont", "Method C-D-A", "https://example.com/path", "")


def test_preserves_dates_and_rates() -> None:
    for name, mod in MODULES.items():
        for label, why in PRESERVES.items():
            got = mod.strip_folder_prefix(label)
            assert got == label, f"[{name}] {label!r} -> {got!r}: {why}"


def test_still_collapses_real_paths() -> None:
    for name, mod in MODULES.items():
        for label, want in COLLAPSES.items():
            got = mod.strip_folder_prefix(label)
            assert got == want, f"[{name}] {label!r} -> {got!r}, expected {want!r}"


def test_leaves_plain_labels_and_urls_alone() -> None:
    for name, mod in MODULES.items():
        for label in UNTOUCHED:
            got = mod.strip_folder_prefix(label)
            assert got == label, f"[{name}] {label!r} -> {got!r}"


def test_distinct_dates_stay_distinct_ids() -> None:
    """The actual failure mode: two unrelated dated notes must not share an id."""
    for name, mod in MODULES.items():
        a = mod.canonical_id("Sesion del 24/08/2026")
        b = mod.canonical_id("Reunion 28/08/2026 con Raul")
        assert a != b, f"[{name}] two unrelated dated labels collapsed onto {a!r}"
        assert a != "c_2026", f"[{name}] date label became the bare-year supernode"


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  [ok]   {t.__name__}")
        except Exception as exc:  # noqa: BLE001 - test harness reports everything
            failed += 1
            print(f"  [FAIL] {t.__name__}: {exc}")
    print("ALL PASS" if not failed else f"{failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
