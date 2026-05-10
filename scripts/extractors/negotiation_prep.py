#!/usr/bin/env python3
"""
extractors/negotiation_prep.py — structured metadata for negotiation prep docs.
Type: `negotiation-prep` (frontmatter uses hyphen; dispatcher lowercases).

Note: Python module names can't have hyphens, so the module is named with
an underscore but the `type:` field in frontmatter uses `negotiation-prep`.
The dispatcher matches by lowercasing + normalizing.
"""
from __future__ import annotations

import re

from _base import (
    extract_section, count_words, iso_date_from, ExtractionResult,
)

AUTO_FIELDS = (
    "neg_counterpart", "neg_meeting_iso", "neg_batna_verbatim",
    "neg_concessions", "neg_goals", "word_count",
)


def _counterpart(body, fm):
    if fm.get("counterpart"):
        return str(fm["counterpart"]).strip()
    if fm.get("with"):
        return str(fm["with"]).strip()
    m = re.search(r"(?im)^(?:with|counterpart)[:\s]+(.+?)$", body[:600])
    return m.group(1).strip() if m else None


def _batna(body):
    m = re.search(r"(?im)^BATNA[:\s]+(.+?)$", body)
    if m:
        return m.group(1).strip()[:240]
    section = extract_section(body, r"^##\s+BATNA")
    if section:
        for ln in section.split("\n"):
            s = ln.strip()
            if s and not s.startswith("#"):
                return s[:240]
    return None


def _bullets_under(body, header):
    section = extract_section(body, header)
    if not section:
        return []
    items = []
    for ln in section.split("\n"):
        s = ln.strip()
        if s.startswith(("- ", "* ")):
            items.append(s[2:].strip()[:200])
    return items[:10]


def extract(filepath, body, fm, context):
    fields = {
        "neg_counterpart": _counterpart(body, fm),
        "neg_meeting_iso": iso_date_from(fm.get("meeting")) or iso_date_from(fm.get("date")),
        "neg_batna_verbatim": _batna(body),
        "neg_concessions": _bullets_under(body, r"^##\s+Concessions"),
        "neg_goals": _bullets_under(body, r"^##\s+Goals"),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
