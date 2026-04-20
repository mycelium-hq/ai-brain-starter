#!/usr/bin/env python3
"""
extractors/talk.py — structured metadata for speaking engagements / workshops.
Type: `talk`, also `speaking`, `workshop`.
"""
import re

from _base import (
    extract_section, count_words, iso_date_from, ExtractionResult,
)

AUTO_FIELDS = (
    "talk_venue", "talk_date_iso", "talk_audience_size",
    "talk_recording_url", "talk_stories_used", "talk_feedback_received",
    "word_count",
)

URL_RE = re.compile(r"https?://[^\s\)\]]+")
AUDIENCE_RE = re.compile(r"(?im)^audience[:\s]+(~?\d{1,5})")
VENUE_RE = re.compile(r"(?im)^venue[:\s]+(.+?)$")
BLOCKQUOTE_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)


def _venue(body, fm):
    if fm.get("venue"):
        return str(fm["venue"]).strip()
    m = VENUE_RE.search(body[:800])
    return m.group(1).strip() if m else None


def _audience_size(body, fm):
    if isinstance(fm.get("audience_size"), (int, float)):
        return int(fm["audience_size"])
    m = AUDIENCE_RE.search(body[:800])
    if m:
        return int(m.group(1).lstrip("~"))
    return None


def _stories(body, cap=8):
    section = extract_section(body, r"^##\s+Stories")
    if not section:
        return []
    items = []
    for ln in section.split("\n"):
        s = ln.strip()
        if s.startswith(("- ", "* ")):
            items.append(s[2:].strip()[:180])
    return items[:cap]


def _feedback(body, cap=5):
    out = []
    for m in BLOCKQUOTE_RE.finditer(body):
        q = m.group(1).strip()
        if len(q) > 15:
            out.append(q[:200])
        if len(out) >= cap:
            break
    return out


def extract(filepath, body, fm, context):
    urls = URL_RE.findall(body[:2500])
    fields = {
        "talk_venue": _venue(body, fm),
        "talk_date_iso": iso_date_from(fm.get("date")) or iso_date_from(fm.get("creationDate")),
        "talk_audience_size": _audience_size(body, fm),
        "talk_recording_url": urls[0] if urls else None,
        "talk_stories_used": _stories(body),
        "talk_feedback_received": _feedback(body),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
