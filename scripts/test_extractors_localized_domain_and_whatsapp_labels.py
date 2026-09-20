#!/usr/bin/env python3
"""
Regression tests for the two localized-vault fixes in this PR:

  1. scripts/extractors/concept.py's `_domain_from_path()` recognizes the six
     Spanish folder names (Notas, Curiosidades, Escuela, Libros, Psicologia,
     Negocios) alongside their English counterparts, so `concept_domain`
     stops coming out empty on a vault that uses them.
  2. scripts/extractors/whatsapp_chat.py's outgoing-sender detection
     recognizes the exporter's own-language self-label ("Yo" on a Spanish
     phone, "Eu" on Portuguese, etc.), so a Spanish export's outgoing
     messages count as SENT instead of inverting into "received".

Both checks are written to fail if their fix is reverted.

Run: python3 scripts/test_extractors_localized_domain_and_whatsapp_labels.py
"""

from __future__ import annotations  # PEP 604 annotations; gate pins Python 3.9

import importlib
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXTRACTORS = REPO / "scripts" / "extractors"
sys.path.insert(0, str(EXTRACTORS))

# Both extractors import _base, which imports PyYAML -- not guaranteed on a
# contributor's machine (ci.sh's PyYAML bootstrap is CI-only; see
# tests/integration/test_extractors_localized_vault.sh, which SKIPs the same
# way rather than hard-failing on an absent dependency the extractors
# themselves already required before this PR).
try:
    import concept  # noqa: E402
    import whatsapp_chat  # noqa: E402
except ImportError as exc:
    print(f"SKIP: {exc} (pip install pyyaml); extractor assertions did not run.")
    sys.exit(0)

FAILURES = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def main():
    print("\n== _domain_from_path(): Spanish folder names ==")
    spanish_cases = [
        ("/vault/📝 Notas/idea.md", "notes"),
        ("/vault/🌱 Curiosidades/tema.md", "curiosities"),
        ("/vault/🏫 Escuela/clase.md", "school"),
        ("/vault/📚 Libros/resumen.md", "books"),
        ("/vault/🧠 Psicología/reflexion.md", "psychology"),
        ("/vault/💼 Negocios/idea.md", "business"),
    ]
    for path, expected in spanish_cases:
        got = concept._domain_from_path(path)
        check(f"{path.split('/')[2]} -> {expected!r}", got == expected, got)

    print("\n== _domain_from_path(): English names still work (no regression) ==")
    english_cases = [
        ("/vault/📝 Notes/idea.md", "notes"),
        ("/vault/🌱 Curiosities/idea.md", "curiosities"),
        ("/vault/🏫 School/idea.md", "school"),
        ("/vault/📚 Books/idea.md", "books"),
        ("/vault/🧠 Psychology/idea.md", "psychology"),
        ("/vault/💼 Business/idea.md", "business"),
    ]
    for path, expected in english_cases:
        got = concept._domain_from_path(path)
        check(f"{path.split('/')[2]} -> {expected!r}", got == expected, got)

    print("\n== _domain_from_path(): unrelated folder still yields no domain ==")
    got = concept._domain_from_path("/vault/🏠 Home/note.md")
    check("unmapped folder returns None, not a guess", got is None, got)

    print("\n== WhatsApp outgoing-sender label set: default (no env override) ==")
    body_es = (
        "## 2026-09-01\n"
        "**10:00 AM** Yo: ya llegue\n"
        "**10:05 AM** Maria: perfecto, nos vemos\n"
        "**10:07 AM** Yo: dale\n"
    )
    total, mine, theirs = whatsapp_chat._msg_counts(body_es)
    check("total messages counted", total == 3, total)
    check("'Yo' (Spanish self-label) counts as mine, not theirs", mine == 2, mine)
    check("the other party still counts as theirs", theirs == 1, theirs)

    body_pt = (
        "## 2026-09-01\n"
        "**10:00 AM** Eu: cheguei\n"
        "**10:05 AM** Joao: combinado\n"
    )
    _total_pt, mine_pt, theirs_pt = whatsapp_chat._msg_counts(body_pt)
    check("'Eu' (Portuguese self-label) counts as mine", mine_pt == 1, mine_pt)
    check("Portuguese contact still counts as theirs", theirs_pt == 1, theirs_pt)

    body_en = (
        "## 2026-09-01\n"
        "**10:00 AM** You: on my way\n"
        "**10:05 AM** Alex: see you soon\n"
    )
    _total_en, mine_en, theirs_en = whatsapp_chat._msg_counts(body_en)
    check("English 'You' still counts as mine (no regression)", mine_en == 1, mine_en)

    print("\n== WhatsApp outgoing-sender label: WHATSAPP_SELF_LABEL override ==")
    # SELF_LABELS is computed once at import time from the env var, so proving
    # the override branch means re-importing with it set, then restoring the
    # module to its normal (unset) state afterward so nothing else in this
    # process observes a stale override.
    prior = os.environ.get("WHATSAPP_SELF_LABEL")
    try:
        os.environ["WHATSAPP_SELF_LABEL"] = "Moi-meme"
        importlib.reload(whatsapp_chat)
        body_custom = (
            "## 2026-09-01\n"
            "**10:00 AM** Moi-meme: j'arrive\n"
            "**10:05 AM** Claire: a tout de suite\n"
            # The default label "Moi" must NOT also match once a custom label
            # is pinned -- the override REPLACES the list, it doesn't extend it.
            "**10:06 AM** Moi: message from someone actually named Moi\n"
        )
        _total_c, mine_c, theirs_c = whatsapp_chat._msg_counts(body_custom)
        check("WHATSAPP_SELF_LABEL override recognized", mine_c == 1, mine_c)
        check("override replaces the default list, not extends it",
              theirs_c == 2, theirs_c)
    finally:
        if prior is None:
            os.environ.pop("WHATSAPP_SELF_LABEL", None)
        else:
            os.environ["WHATSAPP_SELF_LABEL"] = prior
        importlib.reload(whatsapp_chat)

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
