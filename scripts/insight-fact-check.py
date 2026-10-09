#!/usr/bin/env python3
"""
Insight fact-checker. Verifies every claim in a draft weekly/monthly insight
traces back to an actual journal entry in the source period.

Usage:
    VAULT_ROOT="/path/to/vault" python3 insight-fact-check.py <draft_path> \
        [--period-start YYYY-MM-DD] [--period-end YYYY-MM-DD]

If period dates are not given, infers from the draft's frontmatter (date_range field).

Exits 0 if every claim verifies. Exits 1 with a report of unverified claims if not.
The insights skill should block the save on exit 1 and prompt Claude to fix.

Configuration:
    VAULT_ROOT env var: absolute path to the vault. Required.
    Set JOURNALS_DIR env var to override the default journals directory name.
    Set JOURNAL_INDEX env var to override the default index path.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

VAULT_ROOT = os.environ.get("VAULT_ROOT")
if not VAULT_ROOT:
    print("ERROR: VAULT_ROOT env var must be set to the vault absolute path", file=sys.stderr)
    sys.exit(2)

VAULT = Path(VAULT_ROOT)
JOURNALS_DIR = os.environ.get("JOURNALS_DIR", "Journals")
JOURNAL_INDEX = os.environ.get("JOURNAL_INDEX", "Meta/journal-index.json")

INDEX = VAULT / JOURNAL_INDEX
JOURNALS = VAULT / JOURNALS_DIR

CLAIM_TRIGGERS = [
    r"you said\s+",
    r"you wrote\s+",
    r"you mentioned\s+",
    r"you told\s+\w+\s+",
    r"you described\s+",
    r"you called\s+",
    r"you noted\s+",
    r"you journaled\s+",
]

MIN_QUOTE_LEN = 15
MAX_QUOTE_LEN = 220

QUOTE_RX = re.compile(
    r'(?:"([^"\n]{%d,%d}?)"|\u201c([^\u201d\n]{%d,%d}?)\u201d|\u2018([^\u2019\n]{%d,%d}?)\u2019)'
    % (MIN_QUOTE_LEN, MAX_QUOTE_LEN, MIN_QUOTE_LEN, MAX_QUOTE_LEN, MIN_QUOTE_LEN, MAX_QUOTE_LEN)
)


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_period_entries(start: str, end: str) -> list:
    if not INDEX.exists():
        print(f"ERROR: journal index missing at {INDEX}", file=sys.stderr)
        print("Run build-journal-index.py first.", file=sys.stderr)
        sys.exit(2)
    idx = json.loads(INDEX.read_text())
    entries = []
    for e in idx.get("entries", []):
        d = e.get("date", "")
        if start <= d <= end:
            entries.append(e)
    return entries


_FILE_INDEX = None


def _build_file_index():
    global _FILE_INDEX
    if _FILE_INDEX is not None:
        return _FILE_INDEX
    idx = {}
    if JOURNALS.exists():
        for p in JOURNALS.rglob("*.md"):
            idx[p.name] = p
    _FILE_INDEX = idx
    return idx


def read_entry_text(entry: dict) -> str:
    raw = entry["file"]
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p.read_text(errors="ignore")
    candidate = VAULT / raw
    if candidate.exists():
        return candidate.read_text(errors="ignore")
    resolved = _build_file_index().get(p.name)
    if resolved and resolved.exists():
        return resolved.read_text(errors="ignore")
    return ""


def extract_quotes(draft: str) -> list:
    quotes = []
    for m in QUOTE_RX.finditer(draft):
        for g in m.groups():
            if g and len(g.strip()) >= MIN_QUOTE_LEN:
                quotes.append(g.strip())
    return quotes


def extract_claim_spans(draft: str) -> list:
    spans = []
    pattern = re.compile(
        r"(?:%s)([^.!?\n]{20,200})" % "|".join(CLAIM_TRIGGERS),
        re.IGNORECASE,
    )
    for m in pattern.finditer(draft):
        span = m.group(1).strip().strip('"\u201c\u201d\u2018\u2019')
        if span:
            spans.append(span)
    return spans


def verify(claim: str, haystack: str) -> bool:
    h = normalize(haystack)
    c = normalize(claim)
    if c in h:
        return True
    words = c.split()
    if len(words) < 6:
        return False
    window_size = max(5, len(words) // 2)
    for i in range(len(words) - window_size + 1):
        window = " ".join(words[i : i + window_size])
        if window in h:
            return True
    return False


def parse_frontmatter_date_range(draft: str):
    m = re.search(
        r"^date_range:\s*(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})",
        draft,
        re.MULTILINE,
    )
    if m:
        return m.group(1), m.group(2)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", help="Path to draft insight markdown file")
    ap.add_argument("--period-start", help="YYYY-MM-DD")
    ap.add_argument("--period-end", help="YYYY-MM-DD")
    ap.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = ap.parse_args()

    draft_path = Path(args.draft)
    if not draft_path.exists():
        print(f"ERROR: draft not found: {draft_path}", file=sys.stderr)
        return 2
    draft = draft_path.read_text()

    if args.period_start and args.period_end:
        start, end = args.period_start, args.period_end
    else:
        fm = parse_frontmatter_date_range(draft)
        if not fm:
            print(
                "ERROR: no --period-start/--period-end and no date_range in frontmatter",
                file=sys.stderr,
            )
            return 2
        start, end = fm

    entries = load_period_entries(start, end)
    if not entries:
        print(f"ERROR: no journal entries found in {start}..{end}", file=sys.stderr)
        return 2

    haystack = "\n".join(read_entry_text(e) for e in entries)

    quotes = extract_quotes(draft)
    claim_spans = extract_claim_spans(draft)

    unverified_quotes = [q for q in quotes if not verify(q, haystack)]
    unverified_claims = [c for c in claim_spans if not verify(c, haystack)]

    total = len(quotes) + len(claim_spans)
    bad = len(unverified_quotes) + len(unverified_claims)

    if args.json:
        print(
            json.dumps(
                {
                    "period": [start, end],
                    "entries_checked": len(entries),
                    "quotes_total": len(quotes),
                    "claims_total": len(claim_spans),
                    "unverified_quotes": unverified_quotes,
                    "unverified_claims": unverified_claims,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Fact-check: {draft_path.name}")
        print(f"Period: {start} to {end} ({len(entries)} entries)")
        print(f"Checked: {len(quotes)} quotes, {len(claim_spans)} claim spans")
        if bad == 0:
            print("VERIFIED: every claim traces to a journal entry.")
        else:
            print(f"UNVERIFIED: {bad}/{total} claims have no journal source.")
            if unverified_quotes:
                print("\nUnverified quotes (not in any journal entry):")
                for q in unverified_quotes:
                    print(f'  - "{q}"')
            if unverified_claims:
                print("\nUnverified claims (after you said / mentioned / wrote):")
                for c in unverified_claims:
                    print(f"  - {c}")
            print(
                "\nAction: either find the source entry, rewrite the claim to "
                "match actual entry text, or remove it. No fabrication."
            )

    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
