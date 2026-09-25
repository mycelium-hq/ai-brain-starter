#!/usr/bin/env python3
"""
extractors/person.py — structured metadata for CRM entries.
Type: `person`.

Cross-vault fields: mention count + last-journal-iso are computed by scanning
all journals for backlinks to this person. Expensive per-file, cached per-run.
"""
import glob
import os
import re
import sys
import yaml

from _base import (
    VAULT, iso_date_from, count_words, ExtractionResult,
)
from _floors import floor_num_from_fm
from _lib.safe_read import safe_read_text


AUTO_FIELDS = (
    "person_relationship_type", "person_company", "person_is_public_figure",
    "person_last_journal_iso", "person_journal_mention_count",
    "person_floor_cooccurrence", "person_priority", "person_next_step",
    "word_count",
)

# Relationship-type strings that mark a CRM entry as a public figure / author
# rather than a personal contact. These get person_is_public_figure: true and
# are excluded from friend-group insights (drag people / lucky charm).
PUBLIC_FIGURE_RELATIONSHIP_HINTS = {
    "author", "author/thinker", "thinker", "writer", "public figure",
    "celebrity", "influencer", "podcaster", "researcher", "speaker",
    "teacher", "public intellectual", "academic",
}

# Journals folder: self-locating, the same candidate list (and order) that
# scripts/build-journal-index.py uses for /weekly and /monthly. The setup
# interview creates a LOCALIZED folder on a non-English install ("📓 Diarios"
# on Spanish, "📓 Diário" on Portuguese), and a hardcoded "📓 Journals" here
# scanned a path that did not exist — silently: every person got
# person_journal_mention_count = 0 and an empty person_floor_cooccurrence,
# which in turn switched off the lucky-charm / drag-people / stale-relationship
# sections of the insight engine for the whole vault. Pick the first candidate
# that exists; fall back to the English default so the glob below still yields
# nothing (rather than crashing) on a vault with no journal folder at all.
_JOURNAL_CANDIDATES = (
    "📓 Journals", "Journals",       # en (Phase 3 default)
    "📔 Journal", "Journal",
    "📓 Diarios", "Diarios",         # es (what Phase 1 tells the installer to create)
    "📓 Diario", "Diario",           # es, singular variant
    "📓 Diário", "Diário",           # pt
)
# JOURNALS_FOLDER: an operator whose journal folder is named outside the
# candidate list can point at it directly, without editing code. Kept from
# the branch that fixed this alongside the candidate list.
JOURNALS_ROOT = os.environ.get("JOURNALS_FOLDER") or next(
    (os.path.join(VAULT, c) for c in _JOURNAL_CANDIDATES
     if os.path.isdir(os.path.join(VAULT, c))),
    os.path.join(VAULT, _JOURNAL_CANDIDATES[0]),
)

# This glob walks a VAULT, and a vault commonly lives in a cloud-synced folder
# (Drive / iCloud / Dropbox). There, an ordinary-looking `.md` can be a
# dataless placeholder or sit on a stalled mount, and a plain `open().read()`
# blocks forever with no timeout — hanging the whole extraction run on one
# file. safe_read_text bounds every read in wall-clock and size.
JOURNAL_READ_TIMEOUT_S = 5.0
# 1 MB, the same cap scripts/relocate-sweep.py uses, and ~4.1x the largest
# journal measured in a real 2,329-journal vault (242,896 B). Note this cap can
# never hand back a CLIPPED journal: safe_read_text does not truncate — a file
# over the cap returns status "too-large" and is skipped whole, so frontmatter
# is either parsed intact or the file is reported as unread, never silently
# half-read.
JOURNAL_MAX_BYTES = 1_000_000

# Per-run cache: person_name → [(journal_iso, floor_num), ...]
_JOURNAL_INDEX = None


def _warn_unread(fp, result):
    """Name a journal we could not read, without ever raising.

    The print is guarded because this module is imported, not run: it does not
    own the `reconfigure(encoding="utf-8")` guard that _dispatcher.py applies at
    its CLI entry (#313). On a cp1252 or C-locale stderr, interpolating a vault
    path — which routinely contains "📓" — raises UnicodeEncodeError, and an
    unguarded warning would turn a skipped file into a crashed run. That is the
    exact inversion this change exists to prevent.
    """
    detail = f" ({result.detail})" if result.detail else ""
    try:
        print(f"WARNING: journal not indexed [{result.status}{detail}]: {fp}",
              file=sys.stderr)
    except Exception:
        try:
            print(f"WARNING: journal not indexed [{result.status}]: "
                  f"{os.fsencode(fp)!r}", file=sys.stderr)
        except Exception:
            pass


def _build_journal_index():
    """Scan every journal once, extract (name_mentioned, date_iso, floor_num)."""
    global _JOURNAL_INDEX
    if _JOURNAL_INDEX is not None:
        return _JOURNAL_INDEX

    _JOURNAL_INDEX = {}
    wikilink_re = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")

    for fp in glob.glob(os.path.join(JOURNALS_ROOT, "**", "*.md"), recursive=True):
        result = safe_read_text(
            fp, timeout=JOURNAL_READ_TIMEOUT_S, max_bytes=JOURNAL_MAX_BYTES,
        )
        if not result.ok:
            # Skipping is still correct — one bad file must not abort a
            # 2,000-journal run, which is what the old bare `except: continue`
            # bought. What it also bought was SILENCE: an unread journal and a
            # journal with no mentions produced the identical result (a person's
            # count silently short by one), and that is the half worth keeping
            # loud. safe_read_text returns its failures as a status rather than
            # raising, so timeout / offline-placeholder / too-large / binary /
            # decode-error all skip exactly as before, now named.
            # "missing" stays quiet: the glob legitimately races a delete.
            if result.status != "missing":
                _warn_unread(fp, result)
            continue
        content = result.text
        if not content.startswith("---"):
            continue
        end = content.find("\n---", 3)
        if end == -1:
            continue
        try:
            fm = yaml.safe_load(content[3:end]) or {}
        except Exception:
            continue

        date_iso = fm.get("date_iso") or iso_date_from(fm.get("creationDate"))
        # PyYAML parses an unquoted `date_iso: 2026-08-12` into datetime.date,
        # while the creationDate fallback yields a str. Mixed types reach max()
        # below and raise TypeError, aborting the whole run. Normalize to str.
        if date_iso is not None and not isinstance(date_iso, str):
            date_iso = date_iso.isoformat() if hasattr(date_iso, "isoformat") else str(date_iso)
        # The journal writes the floor's NAME (`floor: Hope` / `floor: Esperanza`);
        # `floor_num` only exists once the journal extractor has run, and on an
        # older scale if it ran long ago. Translate the name first, then fall
        # back to the stored number — otherwise co-occurrence is empty on every
        # vault whose journals were never extracted, and the insight sections
        # built on it never fire.
        floor_num = floor_num_from_fm(fm)
        if not date_iso:
            continue

        body = content[end + 4:]
        # Find every wikilink in the body, Title-Cased
        seen_in_this_file = set()
        for m in wikilink_re.findall(body):
            basename = os.path.basename(m.strip())
            if not basename or not basename[0].isupper():
                continue
            if basename in seen_in_this_file:
                continue
            seen_in_this_file.add(basename)
            _JOURNAL_INDEX.setdefault(basename, []).append((date_iso, floor_num))
    return _JOURNAL_INDEX


def _priority(fm):
    p = fm.get("priority")
    if not p:
        return None
    p = str(p).lower().strip()
    return p if p in ("high", "mid", "medium", "low") else None


def _coerce_text(value):
    """Frontmatter fields are author-written: the same key shows up as a string,
    a YAML list, or a number across vaults. Flatten to one lowercase string so
    callers never have to care which shape arrived."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_coerce_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(_coerce_text(v) for v in value.values())
    return str(value).lower().strip()


def _is_public_figure(fm):
    """True if relationship type or notes flag this as author/thinker/public figure."""
    rel = _coerce_text(fm.get("relationship"))
    if rel in PUBLIC_FIGURE_RELATIONSHIP_HINTS:
        return True
    # Also check if any hint word appears within a longer descriptor
    for hint in PUBLIC_FIGURE_RELATIONSHIP_HINTS:
        if hint in rel:
            return True
    return False


def extract(filepath, body, fm, context):
    person_name = os.path.splitext(os.path.basename(filepath))[0]
    journal_idx = _build_journal_index()
    appearances = journal_idx.get(person_name, [])

    # Last journal mention
    if appearances:
        last_iso = max(a[0] for a in appearances)
    else:
        last_iso = None

    # Floor co-occurrence (ordered, most common first, top 5)
    floor_counts = {}
    for (_, fn) in appearances:
        if fn is not None:
            floor_counts[fn] = floor_counts.get(fn, 0) + 1
    top_floors = [str(f) for f, _ in sorted(floor_counts.items(), key=lambda x: -x[1])[:5]]

    fields = {
        "person_relationship_type": fm.get("relationship"),
        "person_company": fm.get("company"),
        "person_is_public_figure": _is_public_figure(fm),
        "person_last_journal_iso": last_iso,
        "person_journal_mention_count": len(appearances),
        "person_floor_cooccurrence": top_floors,
        "person_priority": _priority(fm),
        "person_next_step": fm.get("next_step"),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
