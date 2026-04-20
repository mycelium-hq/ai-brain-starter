#!/usr/bin/env python3
"""
extractors/daily_log.py — structured metadata for Roam-style daily logs.
Type: `daily_log`, also `daily-log`, `log`.
"""
import os
import re

from _base import (
    count_words, iso_date_from, ExtractionResult,
)

AUTO_FIELDS = (
    "log_date_iso", "log_tasks_logged", "log_tasks_done",
    "log_linked_journal", "word_count",
)

FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _date_from_filename(filepath):
    basename = os.path.basename(filepath)
    m = FILENAME_DATE_RE.search(basename)
    return m.group(1) if m else None


def extract(filepath, body, fm, context):
    date_iso = (
        iso_date_from(fm.get("creationDate"))
        or _date_from_filename(filepath)
    )
    # Count task checkboxes
    tasks_total = len(re.findall(r"(?m)^\s*-\s*\[[ xX]\]", body))
    tasks_done = len(re.findall(r"(?m)^\s*-\s*\[[xX]\]", body))

    # Linked journal: look for [[YYYY-MM-DD]]-shaped wikilink matching same date
    linked = None
    if date_iso:
        if f"[[{date_iso}]]" in body or f"[[Journal {date_iso}]]" in body:
            linked = date_iso

    fields = {
        "log_date_iso": date_iso,
        "log_tasks_logged": tasks_total,
        "log_tasks_done": tasks_done,
        "log_linked_journal": linked,
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
