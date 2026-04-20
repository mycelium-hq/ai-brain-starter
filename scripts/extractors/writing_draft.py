#!/usr/bin/env python3
"""
extractors/writing_draft.py — structured metadata for Writing/ drafts.
Type: `writing_draft`, also `draft`.
"""
import os

from _base import (
    VAULT, extract_section, count_words, iso_date_from,
    wikilinks_in, ExtractionResult,
)

AUTO_FIELDS = (
    "draft_status", "draft_publication", "draft_published_iso",
    "draft_word_count", "draft_themes", "draft_chapter_of",
)

STATUS_VALUES = {"draft", "edit", "editing", "ready", "published", "shipped", "archived"}


def _publication(filepath):
    rel = filepath.replace(VAULT, "").lstrip(os.sep).lower()
    if "substack" in rel:
        return "substack"
    if "high-rise" in rel or "high rise" in rel:
        return "high-rise"
    if "after the shock" in rel or "after-the-shock" in rel:
        return "after-the-shock"
    return None


def _chapter_of(filepath):
    rel = filepath.replace(VAULT, "").lstrip(os.sep)
    segments = rel.split(os.sep)
    # Look for a book-level folder inside Writing/
    if segments and segments[0].startswith("✍️ Writing"):
        if len(segments) >= 3:
            return segments[1]
    return None


def _status(fm, body):
    s = fm.get("status")
    if s:
        s = str(s).lower().strip()
        if s in STATUS_VALUES:
            return s
    return None


def _themes(body):
    for header in (r"^##\s+Themes", r"^##\s+Concepts"):
        section = extract_section(body, header)
        if section:
            out = []
            for lnk in wikilinks_in(section):
                if lnk and lnk not in out:
                    out.append(lnk)
            if out:
                return out[:15]
    return []


def extract(filepath, body, fm, context):
    fields = {
        "draft_status": _status(fm, body),
        "draft_publication": _publication(filepath),
        "draft_published_iso": iso_date_from(fm.get("published")) or iso_date_from(fm.get("publishedAt")),
        "draft_word_count": count_words(body),
        "draft_themes": _themes(body),
        "draft_chapter_of": _chapter_of(filepath),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
