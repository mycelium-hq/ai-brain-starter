#!/usr/bin/env python3
"""
extractors/book.py — structured metadata for book notes.
Type: `book`. Verbatim only, no LLM.
"""
from __future__ import annotations

import re

from _base import (
    extract_section, match_people, count_words, iso_date_from,
    wikilinks_in, WIKILINK_RE, strip_wikilinks, ExtractionResult,
)

AUTO_FIELDS = (
    "book_author", "book_themes", "book_quotes_verbatim", "book_rating_1_5",
    "book_finished_iso", "book_mentioned_people", "book_page_count", "word_count",
)

AUTHOR_RE = re.compile(r"(?i)(?:^|\n)(?:by|author)[:\s]+([A-Z][A-Za-z.\- ]{2,50}?)(?:[\.\n,]|$)")
RATING_RE = re.compile(r"(?i)(?:rating|rated)[:\s]+([1-5])(?:/5|\s*stars?)?")
STAR_RE = re.compile(r"(⭐){1,5}")
PAGES_RE = re.compile(r"(?i)pages?[:\s]+(\d{1,4})")
FINISHED_RE = re.compile(r"(?i)finished[:\s]+(\d{4}-\d{2}-\d{2})")
BLOCKQUOTE_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)


def _rating(body):
    m = RATING_RE.search(body)
    if m:
        return int(m.group(1))
    m = STAR_RE.search(body)
    if m:
        return len(m.group(0)) // len("⭐")
    return None


def _author(body):
    m = AUTHOR_RE.search(body[:1500])  # only scan top of note
    if m:
        return m.group(1).strip().rstrip(".")
    return None


def _quotes(body, max_quotes=5, max_len=200):
    """First N blockquote lines, verbatim, capped length."""
    quotes = []
    for m in BLOCKQUOTE_RE.finditer(body):
        q = m.group(1).strip()
        if len(q) < 15:
            continue
        q = strip_wikilinks(q)[:max_len]
        if q not in quotes:
            quotes.append(q)
        if len(quotes) >= max_quotes:
            break
    return quotes


def _themes(body):
    """Wikilinks from ## Themes / ## Topics / ## Concepts section."""
    for header in (r"^##\s+Themes", r"^##\s+Topics", r"^##\s+Concepts"):
        section = extract_section(body, header)
        if section:
            seen = []
            for lnk in wikilinks_in(section):
                if lnk and lnk not in seen:
                    seen.append(lnk)
            return seen[:20]
    return []


def extract(filepath, body, fm, context):
    fields = {
        "book_author": _author(body) or fm.get("author"),
        "book_themes": _themes(body),
        "book_quotes_verbatim": _quotes(body),
        "book_rating_1_5": _rating(body) or fm.get("rating"),
        "book_finished_iso": iso_date_from(fm.get("finished")) or (
            FINISHED_RE.search(body).group(1) if FINISHED_RE.search(body) else None
        ),
        "book_mentioned_people": match_people(body, context["crm_names"]),
        "book_page_count": int(PAGES_RE.search(body).group(1)) if PAGES_RE.search(body) else None,
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
