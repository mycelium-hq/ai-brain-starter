#!/usr/bin/env python3
"""
extractors/travel.py — structured metadata for travel entries.
Type: `travel`, also `trip`, `place`.
"""
from __future__ import annotations

import re

from _base import (
    match_people, count_words, iso_date_from, wikilinks_in,
    ExtractionResult,
)

AUTO_FIELDS = (
    "travel_place", "travel_visit_iso", "travel_rating_1_5",
    "travel_vibe_tags", "travel_would_return", "travel_companions",
    "word_count",
)

RATING_RE = re.compile(r"(?i)(?:rating|rated)[:\s]+([1-5])(?:/5)?")
STAR_RE = re.compile(r"(⭐){1,5}")
WOULD_RETURN_RE = re.compile(r"(?i)would return[:\s]+(yes|no|maybe|true|false)")
PLACE_RE = re.compile(r"(?im)^(?:place|location|city)[:\s]+(.+?)$")


def _rating(body):
    m = RATING_RE.search(body[:1500])
    if m:
        return int(m.group(1))
    m = STAR_RE.search(body[:1500])
    if m:
        return len(m.group(0)) // len("⭐")
    return None


def _would_return(body):
    m = WOULD_RETURN_RE.search(body[:1500])
    if not m:
        return None
    v = m.group(1).lower()
    if v in ("yes", "true"):
        return True
    if v in ("no", "false"):
        return False
    return None


def _place(filepath, body, fm):
    if fm.get("place"):
        return str(fm["place"]).strip()
    m = PLACE_RE.search(body[:600])
    if m:
        return m.group(1).strip()
    import os
    return os.path.splitext(os.path.basename(filepath))[0]


def _vibe_tags(body):
    from _base import extract_section
    section = extract_section(body, r"^##\s+Vibe") or extract_section(body, r"^##\s+Tags")
    if section:
        out = []
        for lnk in wikilinks_in(section):
            if lnk and lnk not in out:
                out.append(lnk)
        return out[:10]
    return []


def extract(filepath, body, fm, context):
    fields = {
        "travel_place": _place(filepath, body, fm),
        "travel_visit_iso": iso_date_from(fm.get("visited")) or iso_date_from(fm.get("creationDate")),
        "travel_rating_1_5": _rating(body) or fm.get("rating"),
        "travel_vibe_tags": _vibe_tags(body),
        "travel_would_return": _would_return(body),
        "travel_companions": match_people(body, context["crm_names"], cap=10),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
