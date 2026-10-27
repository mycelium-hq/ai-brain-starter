#!/usr/bin/env python3
"""
extractors/person.py — structured metadata for CRM entries.
Type: `person`.

Cross-vault fields: mention count + last-journal-iso are computed by scanning
all journals for backlinks to this person, and for their name or `aliases:`
written in plain text. Expensive per-file, cached per-run.
"""
import os
import re
import sys
import yaml

from _base import (
    VAULT, CRM_ROOT, iso_date_from, count_words, ExtractionResult,
    is_inside_vault, iter_vault_markdown, parse_frontmatter,
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
# that exists; fall back to the English default so the walk below still yields
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

# This walk covers a VAULT, and a vault commonly lives in a cloud-synced folder
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

# Per-run cache of every journal the index read:
# [(journal_iso, floor_num, body, links), ...], where links lists each [[link]]
# in the body as (start, end, lowercased target file name).
# The wikilink pass only sees links to the exact file name. People are often
# written without one ("lunch with Maya"), or linked by an alias ([[Maya]]), and
# a person mentioned that way read as 0 mentions, so the "going cold" and
# co-occurrence findings fired on people seen every week. The plain-text pass
# below reads the same bodies for the name and `aliases:`.
_JOURNAL_BODIES = None
_LINK_SPAN_RE = re.compile(r"\[\[([^\]|#]*)[^\]]*\]\]")

# Per-run cache: lowercased name or alias → the CRM notes that claim it.
_TERM_OWNERS = None

# Per-run cache: lowercased file name of every note in the vault.
_NOTE_NAMES = None

# PERSON_PLAIN_TEXT_MENTIONS=0 turns the plain-text pass off: wikilinks only.
PLAIN_TEXT_MENTIONS = os.environ.get("PERSON_PLAIN_TEXT_MENTIONS", "1") != "0"

# Shorter names or aliases ("Al", "Jo") match too much ordinary text.
MIN_TERM_LEN = 3

# The next word after a match, skipping the lowercase particles that sit inside
# names ("Ana de la Fuente", "Maya van Dijk").
_NEXT_WORD_RE = re.compile(
    r"(?:[ \t]+(?:de|del|da|das|do|dos|di|du|la|las|los|le|van|von|der|den))*[ \t]+(\w)"
)
_PREV_WORD_RE = re.compile(r"(\w[\w'’-]*)[ \t]+$")
# What can sit right before the first word of a sentence or a line, where a
# capital is grammar rather than part of a name. Commas, quotes and parentheses
# are left out on purpose: "(Mary Ann)" and "Later, Mary Ann" must not count
# for an "Ann".
_SENTENCE_EDGE = frozenset(".!?…:;\n-*•>#")


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


def _warn(message):
    """Print a warning to stderr without ever raising: this module is imported, not run."""
    try:
        print(message, file=sys.stderr)
    except Exception:
        pass


def _build_journal_index():
    """Scan every journal once, extract (name_mentioned, date_iso, floor_num)."""
    global _JOURNAL_INDEX, _JOURNAL_BODIES
    if _JOURNAL_INDEX is not None:
        return _JOURNAL_INDEX

    _JOURNAL_INDEX = {}
    _JOURNAL_BODIES = []
    wikilink_re = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")

    if os.path.isdir(JOURNALS_ROOT) and not is_inside_vault(JOURNALS_ROOT):
        # JOURNALS_FOLDER, or a journal folder that is itself a link, pointing out
        # of the vault. Nothing in it is read, so say so rather than let every
        # person read as "no mentions".
        _warn(f"WARNING: journal folder resolves outside the vault, not indexed: {JOURNALS_ROOT}")

    for fp in iter_vault_markdown(JOURNALS_ROOT):
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
            # "missing" stays quiet: the walk legitimately races a delete.
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
        links = [(m.start(), m.end(), os.path.basename(m.group(1).strip()).lower())
                 for m in _LINK_SPAN_RE.finditer(body)]
        _JOURNAL_BODIES.append((date_iso, floor_num, body, links))
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


def _aliases(fm):
    """The note's `aliases:` (Obsidian's key; `alias:` is the older spelling) as
    a list of strings, whether the YAML gave a list or a single string."""
    out = []
    for key in ("aliases", "alias"):
        val = fm.get(key)
        if val is None:
            continue
        vals = val if isinstance(val, (list, tuple, set)) else [val]
        out.extend(str(v).strip() for v in vals if v is not None)
    return [a for a in out if a]


def _term_owners():
    """Lowercased name or alias → the CRM notes that claim it, by file name or in
    `aliases:`. Read once per run, with the same in-vault walk and bounded read
    as the journals."""
    global _TERM_OWNERS
    if _TERM_OWNERS is not None:
        return _TERM_OWNERS
    _TERM_OWNERS = {}
    for fp in iter_vault_markdown(CRM_ROOT):
        note = os.path.splitext(os.path.basename(fp))[0]
        _TERM_OWNERS.setdefault(note.lower(), set()).add(note)
        result = safe_read_text(
            fp, timeout=JOURNAL_READ_TIMEOUT_S, max_bytes=JOURNAL_MAX_BYTES,
        )
        if not result.ok:
            continue  # its own extraction reports it; the file name still counts
        fm, _, _ = parse_frontmatter(result.text)
        if not isinstance(fm, dict):
            continue
        for alias in _aliases(fm):
            _TERM_OWNERS.setdefault(alias.lower(), set()).add(note)
    return _TERM_OWNERS


def _note_names():
    """Lowercased file names of every note in the vault, to tell a link to an
    existing note from an unresolved one. One walk per run, no file reads."""
    global _NOTE_NAMES
    if _NOTE_NAMES is None:
        _NOTE_NAMES = {os.path.splitext(os.path.basename(fp))[0].lower()
                       for fp in iter_vault_markdown(VAULT)}
    return _NOTE_NAMES


def _part_of_longer_name(body, start, end):
    """True when body[start:end] reads as part of a longer capitalized name,
    so "Mary Ann", "Ann Lee" and "Ann de la Cruz" do not count for an "Ann".

    A capitalized next word, after any lowercase particles, marks a longer name.
    So does a capitalized previous word, unless it opens a sentence or a line
    ("Today Ann called"), where the capital is grammar. That exception cannot
    tell "Today Ann" from "Mary Ann" at the start of a sentence, so the second
    still counts there.
    """
    m = _NEXT_WORD_RE.match(body, end)
    if m and m.group(1).isupper():
        return True
    pre = body[max(0, start - 80):start]
    m = _PREV_WORD_RE.search(pre)
    if not m or not m.group(1)[0].isupper():
        return False
    before = pre[:m.start()].rstrip(" \t")
    return bool(before) and before[-1] not in _SENTENCE_EDGE


def _plain_text_appearances(person_name, fm):
    """Journals that name the person in plain text: [(journal_iso, floor_num), ...].

    Looks for the note's file name and each alias, case-sensitive, as whole
    words. A term another CRM note also claims ("Sam" for two people) is skipped:
    plain text cannot say which one is meant, and they still count through
    wikilinks. A match inside a [[link]] counts when the link points at one of
    the person's own names ([[Maya]] for an alias Maya), and never when it
    points at another existing note ([[Maya Lin|Maya]] is about Maya Lin). In
    an unresolved link, and in plain text, a capitalized alias or a one-word
    file name must not sit inside a longer name (see _part_of_longer_name). A
    lowercase alias ("my sister") is taken as written, and so is a file name of
    two or more words: it is the full name, and a capitalized word after it is
    more likely a second surname than someone else.
    """
    owners = _term_owners()
    own = {t.lower() for t in [person_name] + _aliases(fm)}
    pats = []
    for term in [person_name] + _aliases(fm):
        if len(term) < MIN_TERM_LEN or any(term == t for t, _, _ in pats):
            continue
        if owners.get(term.lower(), set()) - {person_name}:
            continue
        guard = term[0].isupper() and (term != person_name or " " not in term)
        pats.append((term, re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)"), guard))

    def counts(body, links, m, guard):
        for start, end, target in links:
            if start <= m.start() < end:
                if target in own:
                    return True
                if target in _note_names():
                    return False
                break  # an unresolved link reads like plain text
        return not (guard and _part_of_longer_name(body, m.start(), m.end()))

    out = []
    for date_iso, floor_num, body, links in _JOURNAL_BODIES or ():
        for term, pat, guard in pats:
            if term not in body:
                continue
            if any(counts(body, links, m, guard) for m in pat.finditer(body)):
                out.append((date_iso, floor_num))
                break
    return out


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
    appearances = list(journal_idx.get(person_name, []))

    # A journal that names the person without a [[link]] counts too. A day
    # already counted through a link is not counted again.
    if PLAIN_TEXT_MENTIONS:
        seen_dates = {a[0] for a in appearances}
        for date_iso, floor_num in _plain_text_appearances(person_name, fm):
            if date_iso not in seen_dates:
                seen_dates.add(date_iso)
                appearances.append((date_iso, floor_num))

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
