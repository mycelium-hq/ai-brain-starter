#!/usr/bin/env python3
"""
extractors/journal.py — structured metadata for daily journals.

Type: `journal`
Emits: smart_excerpt, concepts_extracted, people_mentioned, word_count,
       floor_num, date_iso.
"""
import os
import re

from _base import (
    extract_first_prose_sentence, extract_section, match_people,
    count_words, iso_date_from, wikilinks_in, ExtractionResult,
)

# Auto-written fields, in render order. First one is the idempotency marker.
AUTO_FIELDS = (
    "smart_excerpt", "concepts_extracted", "people_mentioned",
    "word_count", "floor_num", "date_iso",
)

# Hawkins Map of Consciousness (Shame=1 → Enlightenment=17)
FLOOR_MAP = {
    "Shame": 1, "Guilt": 2, "Apathy": 3, "Grief": 4, "Fear": 5,
    "Desire": 6, "Anger": 7, "Pride": 8, "Courage": 9, "Hope": 9,
    "Neutrality": 10, "Willingness": 11, "Acceptance": 12, "Reason": 13,
    "Love": 14, "Joy": 15, "Excitement": 15, "Peace": 16, "Enlightenment": 17,
}

SKIP_FILENAME_PATTERNS = (
    "[AI Extract]", "Weekly", "Monthly Summary",
    "Knowledge Graph Report", "knowledge-graph",
)


def _floor_num(fm):
    raw = fm.get("floor")
    if not raw:
        return None
    vals = raw if isinstance(raw, list) else [raw]
    nums = [FLOOR_MAP[str(v)] for v in vals if str(v) in FLOOR_MAP]
    return min(nums) if nums else None


def _concepts(body):
    """Wikilinks from the ## Concepts section (manually curated)."""
    section = extract_section(body, r"^##\s+Concepts")
    if not section:
        return []
    seen = []
    for link in wikilinks_in(section):
        if link and link not in seen:
            seen.append(link)
    return seen[:30]


def extract(filepath, body, fm, context):
    basename = os.path.basename(filepath)
    if any(p in basename for p in SKIP_FILENAME_PATTERNS):
        return None

    excerpt = extract_first_prose_sentence(body)
    if not excerpt:
        return None

    fields = {
        "smart_excerpt": excerpt,
        "concepts_extracted": _concepts(body),
        "people_mentioned": match_people(body, context["crm_names"]),
        "word_count": count_words(body),
        "floor_num": _floor_num(fm),
        "date_iso": iso_date_from(fm.get("creationDate")),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
