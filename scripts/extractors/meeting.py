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


def _source(body, fm=None):
    """Explicit frontmatter wins; else look for an auto-generator header at the
    very top of the note.

    Scanning 3000 chars of prose for "google meet" / "granola" produced false
    positives: a note that said in its body "no transcript existed" but mentioned
    a Google Meet link for a DIFFERENT meeting was tagged `gemini`. Fabricated
    provenance is worse than none, so markers are only honored in the header
    region where a generated transcript actually announces itself.
    """
    # Only a HUMAN-declared `source:` counts. Never read back `meeting_source`:
    # it is an AUTO_FIELD this function writes, so trusting it would make a bad
    # value permanent — every re-run would re-confirm the first wrong guess.
    declared = str((fm or {}).get("source") or "").strip().lower()
    if declared in SOURCE_MARKERS:
        return declared
    lowered = body[:400].lower()
    for src, markers in SOURCE_MARKERS.items():
        if src == "manual":
            continue
        if any(m in lowered for m in markers):
            return src
    return "manual"


def _declared_attendees(fm):
    """Attendees named in frontmatter beat names scraped from the body.

    `match_people` returns every CRM name appearing in the note, which conflates
    "was in the meeting" with "was mentioned in the meeting" — a person discussed
    in their absence was being recorded as present.
    """
    raw = (fm or {}).get("attendees") or (fm or {}).get("asistentes")
    if not raw:
        return None
    if isinstance(raw, str):
        raw = [p for p in re.split(r",(?![^\[]*\]\])", raw) if p.strip()]
    out = []
    for item in raw:
        name = re.sub(r"^\W*\[\[|\]\]\W*$", "", str(item).strip().strip("\"'")).strip()
        name = name.split("|")[0].strip()
        if name:
            out.append(name)
    return out or None


def extract(filepath, body, fm, context):
    fields = {
        "meeting_attendees": _declared_attendees(fm) or match_people(body[:3000], context["crm_names"]),
        "meeting_date_iso": iso_date_from(fm.get("date")) or iso_date_from(fm.get("creationDate")),
        "meeting_decisions": _bullets(body, [r"^##\s+Decisions", r"^##\s+Decisiones"]),
        "meeting_action_items": _bullets(body, [
            r"^##\s+Action Items", r"^##\s+Action\s+items",
            r"^##\s+To-?dos?", r"^##\s+Next Steps",
            r"^##\s+Tareas",
        ]),
        "meeting_blockers": _bullets(body, [r"^##\s+Blockers", r"^##\s+Bloqueos"]),
        "meeting_source": _source(body, fm),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
