#!/usr/bin/env python3
"""
extractors/strategy.py — structured metadata for strategy docs.
Type: `strategy`.
"""
import re

from _base import (
    count_words, iso_date_from, ExtractionResult,
)

AUTO_FIELDS = (
    "strategy_counterpart", "strategy_stakes", "strategy_deadline_iso",
    "strategy_decisions_open", "word_count",
)

STAKES_MAP = {"high": "high", "mid": "mid", "medium": "mid", "low": "low"}


def _counterpart(body, fm):
    if fm.get("counterpart"):
        return str(fm["counterpart"]).strip()
    if fm.get("with"):
        return str(fm["with"]).strip()
    # Look for "With: X" in top of body
    m = re.search(r"(?im)^with[:\s]+(.+?)$", body[:600])
    if m:
        return m.group(1).strip()
    return None


def _stakes(fm):
    s = fm.get("stakes")
    if not s:
        return None
    return STAKES_MAP.get(str(s).lower().strip())


def _open_decisions(body):
    """Count of lines matching 'Decision:' or ending in '?' under ## Decisions."""
    from _base import extract_section
    section = extract_section(body, r"^##\s+Decisions")
    if not section:
        return 0
    count = 0
    for ln in section.split("\n"):
        s = ln.strip()
        if re.match(r"^(?:-\s*)?decision[:\s]", s, re.I):
            count += 1
        elif s.endswith("?"):
            count += 1
    return count


def extract(filepath, body, fm, context):
    fields = {
        "strategy_counterpart": _counterpart(body, fm),
        "strategy_stakes": _stakes(fm),
        "strategy_deadline_iso": iso_date_from(fm.get("deadline")) or iso_date_from(fm.get("due")),
        "strategy_decisions_open": _open_decisions(body),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
