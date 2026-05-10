#!/usr/bin/env python3
"""
extractors/article.py — structured metadata for saved articles / essays.
Type: `article`.
"""
from __future__ import annotations

import re

from _base import (
    extract_section, count_words, iso_date_from, wikilinks_in,
    ExtractionResult,
)

AUTO_FIELDS = (
    "article_author", "article_source_url", "article_read_iso",
    "article_key_claims", "article_concepts_extracted", "word_count",
)

URL_RE = re.compile(r"https?://[^\s\)\]]+")
AUTHOR_RE = re.compile(r"(?im)^(?:by|author)[:\s]+([^\n]{2,80})")


def _url(body, fm):
    if fm.get("source") and str(fm["source"]).startswith("http"):
        return str(fm["source"]).strip()
    if fm.get("url"):
        return str(fm["url"]).strip()
    m = URL_RE.search(body[:3000])
    return m.group(0) if m else None


def _author(body, fm):
    if fm.get("author"):
        return str(fm["author"]).strip()
    m = AUTHOR_RE.search(body[:1500])
    if m:
        return m.group(1).strip().rstrip(".")
    return None


def _key_claims(body, cap=7):
    """First bullet list under ## Key Claims or ## Claims. Fallback: first - bullets in body."""
    for header in (r"^##\s+Key Claims", r"^##\s+Claims", r"^##\s+Takeaways"):
        section = extract_section(body, header)
        if section:
            claims = [ln.strip()[2:].strip() for ln in section.split("\n")
                      if ln.strip().startswith("- ")]
            return [c for c in claims if c][:cap]
    return []


def _concepts(body):
    """Wikilinks from ## Concepts section, fallback: all wikilinks in body top 2K chars."""
    for header in (r"^##\s+Concepts", r"^##\s+Themes"):
        section = extract_section(body, header)
        if section:
            out = []
            for lnk in wikilinks_in(section):
                if lnk and lnk not in out:
                    out.append(lnk)
            if out:
                return out[:15]
    out = []
    for lnk in wikilinks_in(body[:2500]):
        if lnk and lnk not in out:
            out.append(lnk)
    return out[:15]


def extract(filepath, body, fm, context):
    fields = {
        "article_author": _author(body, fm),
        "article_source_url": _url(body, fm),
        "article_read_iso": iso_date_from(fm.get("creationDate")),
        "article_key_claims": _key_claims(body),
        "article_concepts_extracted": _concepts(body),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
