#!/usr/bin/env python3
"""
extractors/playbook.py — structured metadata for playbook docs.
Type: `playbook`. Usually Pao contractor playbooks (Source/Location/Shape/Channel).
"""
from __future__ import annotations

import re

from _base import (
    extract_section, count_words, ExtractionResult,
)

AUTO_FIELDS = (
    "playbook_owner", "playbook_channel", "playbook_source",
    "playbook_location", "playbook_shape", "word_count",
)

FIELD_RE = {
    "owner": re.compile(r"(?im)^(?:owner|para)[:\s]+(.+?)$"),
    "channel": re.compile(r"(?im)^channel[:\s]+(.+?)$"),
    "source": re.compile(r"(?im)^source[:\s]+(.+?)$"),
    "location": re.compile(r"(?im)^location[:\s]+(.+?)$"),
    "shape": re.compile(r"(?im)^shape[:\s]+(.+?)$"),
}


def _field(body, key, fm):
    if fm.get(key):
        return str(fm[key]).strip()
    m = FIELD_RE[key].search(body[:1500])
    return m.group(1).strip() if m else None


def extract(filepath, body, fm, context):
    fields = {
        "playbook_owner": _field(body, "owner", fm),
        "playbook_channel": _field(body, "channel", fm),
        "playbook_source": _field(body, "source", fm),
        "playbook_location": _field(body, "location", fm),
        "playbook_shape": _field(body, "shape", fm),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
