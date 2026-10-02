#!/usr/bin/env python3
"""
Regression tests for scripts/aggregate-decisions.py's date and title fallbacks.

The Decision Log index read `decision_date` only and took the first heading
as the title. Session-close writes many decisions with just `creationDate`,
and with a What/Why template whose first heading is "## What" (or "## Qué"
in Spanish). On one real 102-decision vault, 16 entries indexed as
`????-??-??` and 12 of them were all titled "Qué".

Undated was not only cosmetic: split_inline_vs_archive() keeps an undated
decision inline forever, so those entries could never rotate to the archive.

The first block goes through build_toc() and split_inline_vs_archive(), which
existed before the fix, and all three of its checks FAIL against the previous
aggregate-decisions.py (verified by running this file against it). The later
blocks pin the individual fallbacks.

Plain script, no pytest (the CI job runs scripts/test_*.py directly on 3.9).
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("aggregate_decisions", HERE / "aggregate-decisions.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: object = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  -> {detail!r}"))
    if not cond:
        FAILURES.append(name)


def _write(d: Path, name: str, text: str) -> Path:
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def _toc_line(d: Path, p: Path) -> str:
    toc = ad.build_toc([p], 6)
    return next(l for l in toc.split("\n") if l.startswith("- `"))


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)

        print("Behaviour through the pre-existing entry points")
        q = _write(d, "2026-09-09T22-47-que-heading.md",
                   "---\ncreationDate: 2026-09-09\n---\n\n## Qué\n\n"
                   "La reunión semanal pasa al jueves. Segunda frase.\n")
        line = _toc_line(d, q)
        check("TOC: a creationDate-only decision gets its date", "`2026-09-09`" in line, line)
        check("TOC: the title is the decision, not the 'Qué' label",
              "— La reunión semanal pasa al jueves" in line, line)
        old = (dt.date.today() - dt.timedelta(days=400)).isoformat()
        p9 = _write(d, f"{old}T09-00-closed-old.md",
                    f"---\ncreationDate: {old}\noutcome: shipped and worked\n---\n\n## What\n\nOld one.\n")
        inline, archive = ad.split_inline_vs_archive([p9], 6)
        check("rotation: a closed, creationDate-only decision older than the window is archived",
              archive == [p9] and inline == [], (inline, archive))
        if FAILURES:
            # The helpers below don't exist before the fix; stop on the
            # behavioural failures instead of a noisy AttributeError.
            print(f"\nFAILED ({len(FAILURES)}): " + ", ".join(FAILURES))
            return 1

        print("Date fallbacks")
        p = _write(d, "2026-09-21T15-14-ten-seats.md",
                   "---\ncreationDate: 2026-09-21 15:14\ntype: decision\n---\n\n"
                   "**What:** the workshop runs with 10 seats, not 8.\n")
        check("creationDate stands in for a missing decision_date",
              ad.decision_date(ad.parse_frontmatter(p.read_text(encoding="utf-8")), p) == "2026-09-21")

        p2 = _write(d, "2026-08-03T10-00-no-dates.md",
                    "---\ntype: decision\n---\n\n# Some decision\n")
        check("the filename date is the last resort",
              ad.decision_date(ad.parse_frontmatter(p2.read_text(encoding="utf-8")), p2) == "2026-08-03")

        p3 = _write(d, "2026-01-01T00-00-explicit.md",
                    "---\ncreationDate: 2026-02-02\ndecision_date: 2026-03-03\n---\n\n# X\n")
        check("an explicit decision_date still wins",
              ad.decision_date(ad.parse_frontmatter(p3.read_text(encoding="utf-8")), p3) == "2026-03-03")

        check("the TOC no longer prints ????-??-?? for a creationDate-only file",
              "????" not in _toc_line(d, p), _toc_line(d, p))

        print("Title fallbacks")
        p4 = _write(d, "2026-09-09T22-47-que-template.md",
                    "---\ncreationDate: 2026-09-09\n---\n\n## Qué\n\n"
                    "En el informe, **las cifras se redondean a miles** aunque "
                    "el anexo guarde el detalle. Segunda frase.\n\n## Por qué\n\nPorque sí.\n\n"
                    "## Cómo se aplica\n\nAsí.\n")
        title = ad.decision_title(ad.strip_frontmatter(p4.read_text(encoding="utf-8")), p4)
        check("a '## Qué' heading is not used as the title", title != "Qué", title)
        check("a later section heading is not used either", title != "Cómo se aplica", title)
        check("the first sentence of the What section is, without markdown",
              title == "En el informe, las cifras se redondean a miles aunque el anexo guarde el detalle",
              title)

        p5 = _write(d, "2026-08-03T15-57-migration.md",
                    "---\ndecision_date: 2026-08-03\n---\n\n"
                    "**What was decided:** how to migrate the [[Context Pack|exported pack]].\n\n"
                    "## Context\n\nLong story.\n")
        title = ad.decision_title(ad.strip_frontmatter(p5.read_text(encoding="utf-8")), p5)
        check("inline '**What was decided:**' label, wikilink alias kept",
              title == "how to migrate the exported pack", title)

        long_what = "word " * 40
        p6 = _write(d, "2026-09-01T00-00-long.md", f"---\n---\n\n## What\n\n{long_what}\n")
        title = ad.decision_title(ad.strip_frontmatter(p6.read_text(encoding="utf-8")), p6)
        check("a long What sentence is cut at a word boundary with an ellipsis",
              title.endswith("…") and len(title) <= ad.TITLE_MAX_CHARS + 1, title)

        p7 = _write(d, "2026-09-01T00-00-real-title.md",
                    "---\n---\n\n# Ship the fix on Monday\n\n## What\n\nSomething else.\n")
        check("a real H1 title is still preferred",
              ad.decision_title(ad.strip_frontmatter(p7.read_text(encoding="utf-8")), p7) == "Ship the fix on Monday")

        p8 = _write(d, "2026-08-03T15-57-bare-slug-here.md", "---\n---\n\nNo headings, no What.\n")
        title = ad.decision_title(ad.strip_frontmatter(p8.read_text(encoding="utf-8")), p8)
        check("the slug fallback drops the whole YYYY-MM-DDTHH-MM- prefix",
              title == "bare slug here", title)

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
