#!/usr/bin/env python3
"""
extractors/meeting.py — structured metadata for meeting notes.
Type: `meeting`.
"""
import re

from _base import (
    extract_section, match_people, count_words, iso_date_from,
    ExtractionResult,
)

AUTO_FIELDS = (
    "meeting_attendees", "meeting_date_iso", "meeting_decisions",
    "meeting_action_items", "meeting_blockers", "meeting_source", "word_count",
)

SOURCE_MARKERS = {
    "gemini": ["gemini", "google meet", "## notes by gemini"],
    "granola": ["granola", "## granola"],
    "manual": [],
}


def _bullets(body, header_patterns, cap=15):
    """First bullet list under any of the given ## headers."""
    for pattern in header_patterns:
        section = extract_section(body, pattern)
        if section:
            items = []
            for line in section.split("\n"):
                s = line.strip()
                if s.startswith(("- ", "* ", "• ")):
                    items.append(s[2:].strip()[:240])
                elif re.match(r"^\d+\.\s", s):
                    items.append(re.sub(r"^\d+\.\s*", "", s)[:240])
            if items:
                return items[:cap]
    return []


def _source(body):
    lowered = body[:3000].lower()
    for src, markers in SOURCE_MARKERS.items():
        if src == "manual":
            continue
        if any(m in lowered for m in markers):
            return src
    return "manual"


def extract(filepath, body, fm, context):
    fields = {
        "meeting_attendees": match_people(body[:3000], context["crm_names"]),
        "meeting_date_iso": iso_date_from(fm.get("date")) or iso_date_from(fm.get("creationDate")),
        "meeting_decisions": _bullets(body, [r"^##\s+Decisions", r"^##\s+Decisiones"]),
        "meeting_action_items": _bullets(body, [
            r"^##\s+Action Items", r"^##\s+Action\s+items",
            r"^##\s+To-?dos?", r"^##\s+Next Steps",
            r"^##\s+Tareas",
        ]),
        "meeting_blockers": _bullets(body, [r"^##\s+Blockers", r"^##\s+Bloqueos"]),
        "meeting_source": _source(body),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
