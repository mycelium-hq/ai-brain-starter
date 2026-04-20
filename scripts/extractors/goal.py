#!/usr/bin/env python3
"""
extractors/goal.py — structured metadata for goal / OKR / vision docs.
Type: `goal`, also `okr`, `vision`.
"""
import os
import re

from _base import (
    extract_section, count_words, iso_date_from, wikilinks_in,
    ExtractionResult,
)

AUTO_FIELDS = (
    "goal_horizon", "goal_status", "goal_deadline_iso",
    "goal_sub_goals", "goal_blockers", "word_count",
)

HORIZON_MAP = {
    "day": "day", "daily": "day",
    "week": "week", "weekly": "week",
    "month": "month", "monthly": "month",
    "quarter": "quarter", "quarterly": "quarter",
    "year": "year", "yearly": "year", "annual": "year",
    "decade": "decade",
    "lifetime": "lifetime",
}

STATUS_MAP = {
    "open": "open", "new": "open",
    "in progress": "in-progress", "in-progress": "in-progress", "active": "in-progress",
    "done": "done", "complete": "done", "completed": "done", "achieved": "done",
    "archived": "archived", "abandoned": "archived", "dropped": "archived",
}


def _horizon(filepath, body, fm):
    if fm.get("horizon"):
        h = str(fm["horizon"]).lower().strip()
        if h in HORIZON_MAP:
            return HORIZON_MAP[h]
    lowered = (os.path.basename(filepath) + " " + body[:500]).lower()
    for key, val in HORIZON_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", lowered):
            return val
    return None


def _status(fm, body):
    if fm.get("status"):
        k = str(fm["status"]).lower().strip()
        if k in STATUS_MAP:
            return STATUS_MAP[k]
    return None


def _sub_goals(body):
    section = extract_section(body, r"^##\s+Sub-?goals") or extract_section(body, r"^##\s+Milestones")
    if section:
        out = []
        for lnk in wikilinks_in(section):
            if lnk and lnk not in out:
                out.append(lnk)
        return out[:15]
    return []


def _blockers(body):
    section = extract_section(body, r"^##\s+Blockers")
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
        "goal_horizon": _horizon(filepath, body, fm),
        "goal_status": _status(fm, body),
        "goal_deadline_iso": iso_date_from(fm.get("deadline")) or iso_date_from(fm.get("due")),
        "goal_sub_goals": _sub_goals(body),
        "goal_blockers": _blockers(body),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
