#!/usr/bin/env python3
"""
Regression tests for scripts/graphify_apply_wikilinks.py's six fixes:

Original PR fixes (2026-09-04):
  1. graphify-out/ (generated output) is excluded from every vault walk, so
     the pass never edits GRAPH_REPORT.md / WIKILINK_GAPS.md and never links
     the gap report's own table rows.
  2. apply_wikilink() refuses to write a note's own name into its own body
     (a self-link renders as a link back to the page you're already reading,
     plus a self-loop in the graph).

Adversarial-review fixes on top (2026-09-17), see docs/CHANGELOG.md:
  a. _norm() NFC-normalizes before casefolding, so an NFD-decomposed filename
     (common on macOS/HFS+) still matches an NFC-composed link target in the
     self-link guard instead of silently comparing unequal.
  b. collect_mentions() / find_contexts() / apply_wikilink() all report a
     skipped-as-unreadable file via stderr instead of continuing silently.
  c. find_contexts() (the approval-prompt preview) applies the same
     NFC-normalized self-link guard as apply_wikilink(), so an entity's own
     note can no longer fill every preview slot with self-references.
  d. load_report() reads WIKILINK_GAPS.md with strict decoding (its existing
     "could not read" warning path can only fire on a genuine decode error;
     errors="ignore" would silently drop a bad byte and parse the file as if
     it were clean).

Each check below is written to FAIL if its fix is reverted — verified by
hand: reverting each fix in isolation and re-running this file reproduces
the failure named in that fix's block, before restoring the fix.

Run: python3 scripts/test_graphify_apply_wikilinks_fixes.py
"""

from __future__ import annotations  # PEP 604 annotations; gate pins Python 3.9

import contextlib
import io
import sys
import tempfile
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

import graphify_apply_wikilinks as gw  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def _capture(fn, *args, **kwargs):
    """Run fn, returning (result, stdout_text, stderr_text)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = fn(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


def _binary_unreadable_file(path: Path) -> None:
    """Write a file safe_read_text() rejects with status 'binary' (skip_binary=True
    is the default at every call site, and none override it) -- a NUL byte in the
    first 4096 bytes is a deterministic, platform-independent way to trigger that,
    unlike an actual timeout or cloud placeholder."""
    path.write_bytes(b"Widget mention preceding a null byte.\x00padding after the null byte.\n")


def main():
    # -----------------------------------------------------------------
    # Fix 1 (original) -- graphify-out/ is excluded from every walk.
    # Revert: remove "graphify-out" from SKIP_PARTS.
    # Reverted result: collect_mentions returns 2 mentions (real note +
    # the generated file), not 1.
    # -----------------------------------------------------------------
    print("\n== fix 1: graphify-out/ excluded from vault walks ==")
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td)
        (vault / "Notes").mkdir()
        (vault / "Notes" / "Real.md").write_text(
            "The Widget shipped today after a long review cycle.\n", encoding="utf-8"
        )
        (vault / "graphify-out").mkdir()
        (vault / "graphify-out" / "GRAPH_REPORT.md").write_text(
            "Widget is a god node with many edges in this report.\n", encoding="utf-8"
        )
        mentions = gw.collect_mentions(vault, "Widget", max_per_file=2, max_total=None)
        check("only the real note is walked", len(mentions) == 1, mentions)
        check("generated file never contributes a mention",
              all(stem != "GRAPH_REPORT" for stem, _ in mentions), mentions)

    # -----------------------------------------------------------------
    # Fix 2 (original) -- apply_wikilink() refuses to link a note to itself.
    # Revert: remove the "if _norm(md.stem) == _norm(link_target): ... continue"
    # block from apply_wikilink().
    # Reverted result: modified == 1 (the note links to itself) instead of 0.
    # -----------------------------------------------------------------
    print("\n== fix 2: apply_wikilink() never links a note to itself ==")
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td)
        (vault / "Notes").mkdir()
        (vault / "Notes" / "Widget.md").write_text(
            "This page is about the Widget and how it came to be.\n", encoding="utf-8"
        )
        modified, out, _err = _capture(
            gw.apply_wikilink, vault, "Widget", "Widget", "Widget", True
        )
        check("self-link is skipped, nothing modified", modified == 0, modified)
        check("skip is announced", "(self-link)" in out, out)

    # -----------------------------------------------------------------
    # Fix a -- _norm() NFC-normalizes before casefolding.
    # Revert: change _norm() to "return s.casefold()" (drop the
    # unicodedata.normalize("NFC", s) call).
    # Reverted result: the direct _norm equality check fails, AND the
    # apply_wikilink integration check below inserts a self-link (modified
    # becomes 1) because the NFD filename no longer matches the NFC target.
    # -----------------------------------------------------------------
    print("\n== fix a: _norm() survives an NFD/NFC round-trip ==")
    nfd_jose = unicodedata.normalize("NFD", "José")  # decomposed: e + combining acute
    nfc_jose = unicodedata.normalize("NFC", "José")  # precomposed
    check("NFD and NFC forms differ as raw strings (sanity)", nfd_jose != nfc_jose)
    check("bare casefold does NOT treat them as equal (sanity)",
          nfd_jose.casefold() != nfc_jose.casefold())
    check("_norm treats NFD and NFC forms as equal", gw._norm(nfd_jose) == gw._norm(nfc_jose))

    with tempfile.TemporaryDirectory() as td:
        vault = Path(td)
        (vault / "CRM").mkdir()
        # Filename stored NFD-decomposed (what HFS+ does on disk); the search/link
        # target below is the NFC form a person would actually type.
        (vault / "CRM" / f"{nfd_jose}.md").write_text(
            "José joined the team this quarter after a long search.\n", encoding="utf-8"
        )
        modified, out, _err = _capture(
            gw.apply_wikilink, vault, nfc_jose, nfc_jose, nfc_jose, True
        )
        check("NFD filename recognized as a self-link against an NFC target",
              modified == 0, modified)
        check("self-link skip announced for the accented name", "(self-link)" in out, out)

    # -----------------------------------------------------------------
    # Fix b -- collect_mentions / find_contexts / apply_wikilink report a
    # skipped-as-unreadable file via stderr instead of continuing silently.
    # Revert: neutralize the "if skipped: print(...)" block at a call site
    # (e.g. "if False and skipped:").
    # Reverted result: the data-correctness checks (binary file contributes
    # nothing) still pass -- safe_read_text() already excludes it -- but the
    # stderr announcement checks fail, because that's the whole fix.
    # -----------------------------------------------------------------
    print("\n== fix b: an unreadable file is reported, not silently dropped ==")
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td)
        (vault / "Notes").mkdir()
        (vault / "Notes" / "Good.md").write_text(
            "The Widget launch went smoothly according to every report.\n", encoding="utf-8"
        )
        _binary_unreadable_file(vault / "Notes" / "Bad.md")

        mentions, _out, err = _capture(
            gw.collect_mentions, vault, "Widget", 2, None, False
        )
        check("collect_mentions: only the readable file contributes",
              len(mentions) == 1, mentions)
        check("collect_mentions: skip is announced on stderr",
              "skipped 1 unreadable file" in err and "Bad.md" in err, err)

        contexts, _out, err = _capture(gw.find_contexts, vault, "Widget", 2)
        check("find_contexts: only the readable file contributes",
              len(contexts) == 1, [str(p) for p, _ in contexts])
        check("find_contexts: skip is announced on stderr",
              "skipped 1 unreadable file" in err and "Bad.md" in err, err)

        modified, _out, err = _capture(
            gw.apply_wikilink, vault, "Widget", "Widget", "Widget", True
        )
        check("apply_wikilink: only the readable file is modified", modified == 1, modified)
        check("apply_wikilink: skip is announced on stderr",
              "skipped 1 unreadable file" in err and "Bad.md" in err, err)

    # -----------------------------------------------------------------
    # Fix c -- find_contexts() applies the same self-link guard as
    # apply_wikilink(), and still respects max_results after the
    # return-inside-the-loop -> break/break restructuring.
    # Revert: remove the self-guard block from find_contexts() specifically
    # (leave apply_wikilink()'s own guard untouched).
    # Reverted result: the entity's own note fills a preview slot, so the
    # "external mention only" check below fails.
    # -----------------------------------------------------------------
    print("\n== fix c: find_contexts() excludes the entity's own note ==")
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td)
        (vault / "Notes").mkdir()
        (vault / "Notes" / "Widget.md").write_text(
            "This page describes the Widget in exhaustive detail.\n", encoding="utf-8"
        )
        (vault / "Notes" / "Other.md").write_text(
            "The team shipped the Widget ahead of schedule this time.\n", encoding="utf-8"
        )
        contexts, _out, _err = _capture(gw.find_contexts, vault, "Widget", 2)
        names = [p.stem for p, _ in contexts]
        check("only the external mention is returned", names == ["Other"], names)
        check("the entity's own note never appears as its own context",
              "Widget" not in names, names)

        # max_results is still honored post-restructuring: 3 external mentions,
        # cap of 2, none of them the entity's own note.
        for i in range(3):
            (vault / "Notes" / f"External{i}.md").write_text(
                f"External mention number {i} of the Widget shows up here.\n", encoding="utf-8"
            )
        contexts2, _out, _err = _capture(gw.find_contexts, vault, "Widget", 2)
        check("max_results cap still honored after restructuring",
              len(contexts2) == 2, len(contexts2))

    # -----------------------------------------------------------------
    # Fix d -- load_report() decodes WIKILINK_GAPS.md strictly, so a
    # malformed byte fails loud instead of being silently dropped.
    # Revert: add errors="ignore" to load_report()'s safe_read_text() call
    # (matching the other three call sites).
    # Reverted result: the bad byte is dropped, the row parses as if clean,
    # and load_report() returns a non-empty list instead of [] with a
    # warning.
    # -----------------------------------------------------------------
    print("\n== fix d: load_report() fails loud on a malformed byte ==")
    with tempfile.TemporaryDirectory() as td:
        report_path = Path(td) / "WIKILINK_GAPS.md"
        # 0xFF is not a valid UTF-8 lead or continuation byte in any position.
        # errors="ignore" would drop it and leave a well-formed row behind
        # ("| 1 | Widget | concept | 5 |") -- that's the exact silent-corruption
        # shape this fix closes.
        report_path.write_bytes(
            b"# Wikilink gaps\n"
            b"| # | Label | Type | Degree |\n"
            b"| 1 | Wi\xffdget | concept | 5 |\n"
        )
        terms, out, _err = _capture(gw.load_report, report_path)
        check("strict decode failure yields no terms, not a silently-cleaned row",
              terms == [], terms)
        check("the failure is announced", "could not read" in out, out)

        # Positive control: a clean file with the same shape parses fine, so
        # the check above is exercising the decode path, not a broken parser.
        clean_path = Path(td) / "WIKILINK_GAPS_clean.md"
        clean_path.write_text(
            "# Wikilink gaps\n| # | Label | Type | Degree |\n| 1 | Widget | concept | 5 |\n",
            encoding="utf-8",
        )
        clean_terms, _out, _err = _capture(gw.load_report, clean_path)
        check("positive control: a clean report still parses",
              len(clean_terms) == 1 and clean_terms[0]["label"] == "Widget", clean_terms)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + ", ".join(FAILURES))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    # Windows cp1252-console safety (#313): force UTF-8 so a non-ASCII print can't crash.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
