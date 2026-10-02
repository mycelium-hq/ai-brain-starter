#!/usr/bin/env python3
"""Public-template-purity detection — the STRUCTURAL isolation plane (MYC-1765).

Companion to `.github/workflows/personal-pii-scrub.yml`. That workflow blocks
personal NAME tokens + vault paths from public source. This module blocks the
OTHER leak class: POPULATED typed-category content that carries no name and so
slips a name-scrub entirely — a real floor entry, a real deal / counterparty /
amount, a real tenant/entity id sealed into a public-bound skill template.

Two-layer property (CLAUDE.md "two isolation planes"; MYC-1733 Jackie veto):
this module is STRUCTURAL. It detects the SHAPE of populated personal data — a
typed frontmatter field whose value is *real* rather than a placeholder —
WITHOUT embedding any person's name, deal, or floor vocabulary. It ships in the
public substrate so every client's data is protected the same way; the
name-specific scrub stays in the private layer (personal-pii-scrub.yml). The
two planes are non-overlapping: names → that workflow; populated shapes → here.

Used by (single source of truth — adding a detector here covers both surfaces):
- `scripts/check-template-purity.py`        — CLI / CI / pre-push gate
- `hooks/block-populated-public-skill.py`   — PreToolUse write-time guard

Python 3.9 compatible (hooks run via the system /usr/bin/python3).

Threat model + limitations: this plane defends against ACCIDENTAL commits of real
personal data into public templates, not a crafted bypass. It parses markdown
`key: value` frontmatter/body lines (incl. YAML list items). Known v1 gaps,
covered by defense-in-depth (personal-pii-scrub.yml name-scrub + human review):
inline-JSON-embedded values (`{"floor": "Courage"}`), >8-space deep nesting, and
a value deliberately prefixed with a placeholder wrapper (`<x>Courage`). Widen
the parser when a real leak shape demands it; do not pre-harden against crafted
evasion at the cost of false positives that self-DoS public pushes.

Self-test: `python3 hooks/_lib/template_purity.py --selftest` (exit 0 = green).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    """One populated typed-category leak found in a scanned text.

    `rule` names the detector; `field` is the schema key (or "entity_id" for the
    standalone id detector); `excerpt` is a short, safe slice for the report;
    `line` is 1-based.
    """

    rule: str
    field: str
    excerpt: str
    line: int


# Typed frontmatter/body keys whose POPULATED value is per-person private data.
# These are SCHEMA field names (every client's journal has a `floor:`; every
# tenant record has an `entity_id:`), NOT any individual's data — so listing them
# here embeds no one's private content. A populated value of one of these in a
# public-bound template IS the leak this plane exists to stop.
TYPED_FIELDS = frozenset({
    # personal-scope journal schema (daily-journal / rise / coaching / insights)
    "floor", "floor_level", "floor_name",
    # deal / sales / investor schema (sales-pipeline / investor-draft / finance)
    "counterparty", "deal", "deal_name", "investor", "investors",
    "amount", "valuation", "arr", "mrr", "check_size",
    # governance / legal schema
    "board", "board_members", "advisor", "advisors",
    # runtime tenancy schema (the sealed-corpus identity keys)
    "entity_id", "tid", "tenant_id", "personal_owner_user_id",
    # advisory-panel schema
    "panel", "advisory_panel", "panelists",
})

# A value is a PLACEHOLDER (template-pure) if empty or one of these literal
# tokens (exact match or leading token), case-insensitive.
_PLACEHOLDER_TOKENS = (
    "example", "placeholder", "todo", "fixme", "tbd", "xxx", "fill in",
    "fill-in", "fill_in", "n/a", "na", "none", "null", "sample", "redacted",
    "your value here", "your floor", "your reflection here", "lorem ipsum",
    "foo", "bar", "baz",
)

# Floor-family schema slot-descriptors. In a `floor:` field these are
# documentation of the SHAPE ("the primary floor", "the secondary floor"), never
# a real floor name (Courage / Peace / Willingness / ...). Scoped to floor fields
# ONLY: a real `counterparty: Primary Health Inc` must still flag. Generic English
# slot words — embeds no personal floor vocabulary (two-layer principle holds).
_FLOOR_FIELDS = frozenset({"floor", "floor_level", "floor_name"})
_FLOOR_META_LABELS = ("primary", "secondary", "tertiary")

# Structural placeholder shapes: <angle>, {{mustache}}, {brace}, [bracket]
# wrappers; $X / $<amount> / $0 money placeholders; tnt_EXAMPLE-style ids; the
# bare `Low|Middle|High` enum that documents the floor_level field itself.
_PLACEHOLDER_RE = re.compile(
    r"""^\s*(?:
        <[^>]*>                                   # <placeholder>
      | \{\{[^}]*\}\}                             # {{mustache}}
      | \{[^}]*\}                                 # {brace}
      | \[[^\]]*\]                                # [bracket]
      | \$<[^>]*>                                 # $<amount>
      | \$x+                                      # $X / $XX
      | \$n+(?:[,.]?n{2,3})*                       # $N / $NNN / $N,NNN
      | \$0+(?:[.,]0+)?                            # $0 / $0.00
      | \$_+                                       # $___
      | _+                                        # ___
      | -{2,}                                      # ---
      | \.{3,}                                     # ...
      | (?:tnt|usr|tid)_(?:example|x+|placeholder|id|abc+|0+)  # id placeholders
      | low\s*\|\s*middle\s*\|\s*high              # the floor_level enum doc
    )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

# A real tenant/entity/user id token, wherever it appears (frontmatter OR body
# prose). `tnt_a1b2c3` leaks even under a non-schema key or in a sentence.
_ENTITY_ID_RE = re.compile(r"\b(?:tnt|usr|tid)_[A-Za-z0-9]{4,}\b")
_ENTITY_ID_PLACEHOLDER_RE = re.compile(
    r"^(?:tnt|usr|tid)_(?:example|x+|placeholder|id|abc+|0+|nnn+)$", re.IGNORECASE)

# `key: value`, with an optional leading YAML list marker so list-item typed
# fields (`  - floor: Courage`) are caught, not just top-level keys.
_FIELD_RE = re.compile(r"^\s{0,8}(?:-\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")


def _strip_inline_comment(value: str) -> str:
    """Drop a YAML-style inline ` # ...` comment. A documented schema line
    (`floor: Primary  # single floor name`) classifies on the bare value, so the
    comment text never makes a value look real — but a real value with a comment
    (`floor: Courage  # felt brave`) still classifies on `Courage` and flags."""
    idx = value.find(" #")
    return value[:idx].rstrip() if idx != -1 else value


def is_placeholder(value: str, field: str = "") -> bool:
    """True if `value` is empty or a template placeholder (not real data).

    `field` (a lowercased schema key) enables field-scoped placeholder rules:
    floor-family slot-descriptors count as placeholders only under a floor field.
    """
    v = _strip_inline_comment(value).strip().strip("\"'").strip()
    if not v:
        return True
    if _PLACEHOLDER_RE.match(v):
        return True
    if v[0] in "<{[":  # any wrapped placeholder, even with trailing prose
        return True
    low = v.lower()
    for tok in _PLACEHOLDER_TOKENS:
        if low == tok or low.startswith(tok + " ") or low.startswith(tok + "-"):
            return True
    if field in _FLOOR_FIELDS:
        for tok in _FLOOR_META_LABELS:
            if low == tok or low.startswith(tok + " ") or low.startswith(tok + "/"):
                return True
    return False


def _entity_id_is_placeholder(token: str) -> bool:
    return bool(_ENTITY_ID_PLACEHOLDER_RE.match(token))


def scan_text(text: str) -> list[Violation]:
    """Return every template-purity violation in `text`. Empty list = pure."""
    out: list[Violation] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = _FIELD_RE.match(line)
        if m:
            key, value = m.group(1).lower(), m.group(2)
            if key in TYPED_FIELDS and not is_placeholder(value, key):
                out.append(Violation(
                    rule="populated-typed-field", field=key,
                    excerpt=("%s: %s" % (key, value))[:120], line=i))
                continue  # one finding per line; skip the id-anywhere pass
        for mm in _ENTITY_ID_RE.finditer(line):
            tok = mm.group(0)
            if not _entity_id_is_placeholder(tok):
                out.append(Violation(
                    rule="real-entity-id", field="entity_id",
                    excerpt=tok, line=i))
    return out


def scan_file(path: str) -> list[Violation]:
    """Scan a file's text. Unreadable file → a fail-closed sentinel violation."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return scan_text(f.read())
    except (OSError, UnicodeDecodeError) as e:
        return [Violation(rule="unreadable", field="-",
                          excerpt="cannot read (%s)" % e.__class__.__name__, line=0)]


# ── self-test (gates regressions; mirrors _lib/secret_patterns.py discipline) ──
# Each case: (label, text, expect_violation). A populated shape MUST flag; a
# placeholder shape MUST NOT. This is the negative-control corpus in code form.
_SELFTEST_CASES = (
    # POPULATED — must flag
    ("floor populated", "floor: Courage", True),
    ("floor_level populated", "floor_level: High", True),
    ("counterparty populated", "counterparty: Northwind Logistics LLC", True),
    ("amount populated", "amount: $36,000", True),
    ("valuation populated", "valuation: $1,200,000", True),
    ("entity_id populated (frontmatter)", "entity_id: tnt_a1b2c3d4", True),
    ("tenant id in prose", "the tenant tnt_9f8e7d6c signed today", True),
    ("investor populated", "investor: Acme Ventures", True),
    ("panel populated", "panel: a named real advisor", True),
    # PLACEHOLDER / template — must NOT flag
    ("floor angle ph", "floor: <floor-name>", False),
    ("floor_level enum doc", "floor_level: <Low|Middle|High>", False),
    ("floor_level bare enum", "floor_level: Low|Middle|High", False),
    ("amount dollar-angle ph", "amount: $<amount>", False),
    ("amount $X ph", "amount: $X", False),
    ("amount zero ph", "amount: $0", False),
    ("counterparty angle ph", "counterparty: <counterparty-name>", False),
    ("entity_id angle ph", "entity_id: <tid>", False),
    ("entity_id example ph", "entity_id: tnt_EXAMPLE", False),
    ("entity_id xxx ph", "entity_id: tnt_xxxx", False),
    ("empty value", "floor:", False),
    ("EXAMPLE token", "counterparty: EXAMPLE", False),
    ("TODO token", "amount: TODO", False),
    ("floor schema-doc slot-label", "floor: Primary  # single floor name (or [Primary, Secondary])", False),
    ("floor real WITH comment still flags", "floor: Courage  # felt brave today", True),
    ("counterparty starting Primary still flags", "counterparty: Primary Health Inc", True),
    ("yaml list-item typed field flags", "  - floor: Courage", True),
    ("yaml list-item placeholder passes", "  - floor: <floor-name>", False),
    ("non-typed key ignored", "stage: signed", False),
    ("non-typed key with $ ignored", "price: $1,500", False),  # pricing is public
    ("prose dollar not gated", "Plans start at $1,200,000 for enterprise.", False),
    ("brace mustache ph", "investor: {{investor_name}}", False),
)


def _selftest() -> int:
    failures = []
    for label, text, expect in _SELFTEST_CASES:
        got = bool(scan_text(text))
        if got != expect:
            failures.append("  [%s] %r expected violation=%s got=%s"
                            % (label, text, expect, got))
    if failures:
        print("template_purity self-test FAILED (%d):" % len(failures))
        print("\n".join(failures))
        return 1
    print("template_purity self-test OK (%d cases)" % len(_SELFTEST_CASES))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    # bare invocation scans files named on argv (convenience)
    rc = 0
    for arg in sys.argv[1:]:
        vs = scan_file(arg)
        for v in vs:
            print("%s:%d  %s  %s" % (arg, v.line, v.rule, v.excerpt))
            rc = 1
    sys.exit(rc)
