#!/usr/bin/env python3
"""
extractors/concept.py — structured metadata for concept notes.
Type: `concept`.

concept_mention_count + concept_last_mentioned_iso require a vault-wide backlink
scan. Cached per-run. Dormant flag = last mention >180 days ago.
"""
import glob
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from _base import (
    VAULT, SKIP_PARTS, iso_date_from, extract_section, wikilinks_in,
    ExtractionResult,
)

# extractors/ -> scripts/ -> repo root -> hooks/_lib. Reach the ONE audited
# safe_read primitive rather than a local reader: the recursive vault-wide
# glob below must survive a cloud placeholder / stalled mount / FIFO, and
# scripts/check-cloud-safe-file-walkers.py refuses to trust anything else.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "hooks"))
from _lib.safe_read import safe_read_text  # noqa: E402

AUTO_FIELDS = (
    "concept_domain", "concept_related", "concept_first_seen_iso",
    "concept_mention_count", "concept_last_mentioned_iso", "concept_dormant",
)

DORMANT_THRESHOLD_DAYS = 180

# Per-run cache: concept_name → [(date_iso, file_rel_path), ...]
_BACKLINK_INDEX = None


def _build_backlink_index():
    """One-shot scan: every wikilink in every non-infra markdown file."""
    global _BACKLINK_INDEX
    if _BACKLINK_INDEX is not None:
        return _BACKLINK_INDEX
    _BACKLINK_INDEX = {}
    wikilink_re = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")

    for fp in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
        parts = set(fp.split(os.sep))
        if parts & SKIP_PARTS:
            continue
        result = safe_read_text(fp, timeout=5.0, max_bytes=1_000_000, errors="replace")
        if not result.ok:
            continue
        content = result.text

        file_date = None
        if content.startswith("---"):
            end = content.find("\n---", 3)
            if end != -1:
                try:
                    fm = yaml.safe_load(content[3:end]) or {}
                except Exception:
                    fm = {}
                raw_date_iso = fm.get("date_iso")
                if hasattr(raw_date_iso, "isoformat"):
                    raw_date_iso = raw_date_iso.isoformat()
                file_date = (
                    raw_date_iso
                    or iso_date_from(fm.get("creationDate"))
                )
        if not file_date:
            try:
                mtime = os.path.getmtime(fp)
                file_date = date.fromtimestamp(mtime).isoformat()
            except Exception:
                continue

        for m in set(wikilink_re.findall(content)):
            basename = os.path.basename(m.strip())
            if not basename:
                continue
            _BACKLINK_INDEX.setdefault(basename, []).append(file_date)
    return _BACKLINK_INDEX


def _domain_from_path(fp):
    """Infer concept domain from path emoji folder."""
    rel = fp.replace(VAULT, "").lstrip(os.sep)
    segments = rel.split(os.sep)
    mapping = {
        "📝 Notes": "notes", "🌱 Curiosities": "curiosities",
        "🏫 School": "school", "📚 Books": "books", "🧠 Psychology": "psychology",
        "💼 Business": "business",
        # Spanish counterparts of the six folders above. Folder creation in
        # phases/phase-02-03-plugins-folders.md is English-only — but
        # phase-01-welcome.md separately tells the setup interview to
        # translate folder names "where idiomatic" on a non-English vault,
        # naming 📚 Libros/ and 📝 Notas/ as its own examples — so a user may
        # end up with these folders even though no phase hardcodes all six.
        # Either way, an English-only mapping returns None for every note in
        # them — so `concept_domain` comes out empty for the whole vault,
        # silently, and every downstream grouping by domain sees one
        # undifferentiated blob.
        "📝 Notas": "notes", "🌱 Curiosidades": "curiosities",
        "🏫 Escuela": "school", "📚 Libros": "books",
        "🧠 Psicología": "psychology", "💼 Negocios": "business",
    }
    for seg in segments:
        if seg in mapping:
            return mapping[seg]
    return None


def extract(filepath, body, fm, context):
    name = os.path.splitext(os.path.basename(filepath))[0]
    backlinks = _build_backlink_index()
    appearances = backlinks.get(name, [])

    last_iso = max(appearances) if appearances else None
    first_iso = min(appearances) if appearances else None

    dormant = False
    if last_iso:
        try:
            last_d = datetime.fromisoformat(last_iso).date()
            dormant = (date.today() - last_d) > timedelta(days=DORMANT_THRESHOLD_DAYS)
        except Exception:
            dormant = False

    # Related: wikilinks in ## Related / ## Connected / ## See Also
    related = []
    for header in (r"^##\s+Related", r"^##\s+Connected", r"^##\s+See Also"):
        section = extract_section(body, header)
        if section:
            for lnk in wikilinks_in(section):
                if lnk and lnk not in related:
                    related.append(lnk)
            break

    fields = {
        "concept_domain": _domain_from_path(filepath),
        "concept_related": related[:15],
        "concept_first_seen_iso": first_iso,
        "concept_mention_count": len(appearances),
        "concept_last_mentioned_iso": last_iso,
        "concept_dormant": dormant,
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
