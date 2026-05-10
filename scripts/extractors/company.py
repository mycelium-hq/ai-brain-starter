#!/usr/bin/env python3
"""
extractors/company.py — structured metadata for company notes.
Type: `company`.
"""
from __future__ import annotations

import re

from _base import (
    extract_section, count_words, ExtractionResult,
)

AUTO_FIELDS = (
    "company_status", "company_founded_year", "company_exit_year",
    "company_sector", "company_my_role", "word_count",
)

STATUS_MAP = {
    "active": "active", "running": "active", "operating": "active",
    "exit": "exit", "exited": "exit", "acquired": "exit", "sold": "exit",
    "dead": "dead", "shut down": "dead", "closed": "dead", "dissolved": "dead",
    "paused": "paused", "dormant": "paused", "on hold": "paused",
}

ROLE_MAP = {
    "founder": "founder", "co-founder": "cofounder", "cofounder": "cofounder",
    "ceo": "founder", "advisor": "advisor", "investor": "investor",
    "board": "advisor", "operator": "founder",
}

YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _status(body, fm):
    raw = fm.get("status")
    if raw:
        k = str(raw).lower().strip()
        if k in STATUS_MAP:
            return STATUS_MAP[k]
    lowered = body[:2000].lower()
    for key, val in STATUS_MAP.items():
        if re.search(rf"(?:^|[\s.,])(?:status|state)[:\s]+{re.escape(key)}", lowered):
            return val
    return None


def _year(body, label_patterns):
    for pattern in label_patterns:
        m = re.search(pattern, body[:2000], re.IGNORECASE)
        if m:
            y = YEAR_RE.search(m.group(0))
            if y:
                return int(y.group(1))
    return None


def _role(body, fm):
    raw = fm.get("role") or fm.get("my_role")
    if raw:
        k = str(raw).lower().strip()
        if k in ROLE_MAP:
            return ROLE_MAP[k]
    lowered = body[:2000].lower()
    for key, val in ROLE_MAP.items():
        if re.search(rf"(?:my role|role)[:\s]+{re.escape(key)}", lowered):
            return val
    return None


def _sector(body, fm):
    if fm.get("sector"):
        return str(fm["sector"]).strip()
    m = re.search(r"(?im)^sector[:\s]+(.+?)$", body[:2000])
    return m.group(1).strip() if m else None


def extract(filepath, body, fm, context):
    fields = {
        "company_status": _status(body, fm),
        "company_founded_year": _year(body, [r"founded[:\s]+\d{4}", r"started[:\s]+\d{4}"]),
        "company_exit_year": _year(body, [r"exit(?:ed)?[:\s]+\d{4}", r"acquired[:\s]+\d{4}", r"sold[:\s]+\d{4}"]),
        "company_sector": _sector(body, fm),
        "company_my_role": _role(body, fm),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
