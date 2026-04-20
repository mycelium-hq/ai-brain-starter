#!/usr/bin/env python3
"""
extractors/reference.py — structured metadata for reference cheat-sheets.
Type: `reference`.
"""
from _base import (
    count_words, iso_date_from, wikilinks_in, ExtractionResult,
)

AUTO_FIELDS = (
    "reference_topic", "reference_last_updated_iso",
    "reference_related", "word_count",
)


def extract(filepath, body, fm, context):
    import os
    topic = fm.get("topic") or os.path.splitext(os.path.basename(filepath))[0]

    related = []
    for lnk in wikilinks_in(body[:3000]):
        if lnk and lnk not in related:
            related.append(lnk)

    fields = {
        "reference_topic": topic,
        "reference_last_updated_iso": (
            iso_date_from(fm.get("last_updated"))
            or iso_date_from(fm.get("creationDate"))
        ),
        "reference_related": related[:15],
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
