#!/usr/bin/env python3
"""
extractors/business.py — structured metadata for business docs.
Type: `business`. Investor memos, pitch decks (as notes), sales docs, updates.
"""
import os
import re

from _base import (
    extract_section, match_people, count_words, iso_date_from,
    wikilinks_in, ExtractionResult,
)

AUTO_FIELDS = (
    "biz_doc_kind", "biz_audience", "biz_last_sent_iso", "biz_version",
    "biz_key_numbers", "biz_recipients", "word_count",
)

KIND_KEYWORDS = {
    "deck": ["deck", "slides", "pitch deck"],
    "memo": ["memo"],
    "email": ["email", "outreach"],
    "contract": ["contract", "agreement", "loi", "sow"],
    "pitch": ["pitch", "one-pager"],
    "update": ["update", "investor update", "monthly update"],
    "packages": ["package", "pricing"],
    "research": ["market intelligence", "research"],
    "strategy_doc": ["strategy"],
}

SENT_RE = re.compile(r"(?i)sent[:\s]+(\d{4}-\d{2}-\d{2})")
VERSION_RE_FILE = re.compile(r"(?i)(?:^|[\s\-_])v(\d+(?:\.\d+)?)")
VERSION_RE_BODY = re.compile(r"(?i)version[:\s]+v?(\d+(?:\.\d+)?)")
MONEY_RE = re.compile(r"\$[\d,]+(?:\.\d+)?[KMB]?")
PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?%")


def _kind(filepath, body):
    # Include full path so folder context ("📋 Strategy/") is part of the match.
    haystack = (filepath + " " + body[:500]).lower()
    for kind, keywords in KIND_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return kind
    return None


def _audience(body, fm):
    if fm.get("audience"):
        return str(fm["audience"]).strip()
    # Look for "Audience: X" on a line
    m = re.search(r"(?im)^audience[:\s]+(.+?)$", body[:800])
    if m:
        return m.group(1).strip()
    return None


def _version(filepath, body):
    for regex in (VERSION_RE_BODY,):
        m = regex.search(body[:1000])
        if m:
            return f"v{m.group(1)}"
    m = VERSION_RE_FILE.search(os.path.basename(filepath))
    if m:
        return f"v{m.group(1)}"
    return None


def _key_numbers(body, cap=12):
    numbers = []
    for m in MONEY_RE.finditer(body[:3000]):
        v = m.group(0)
        if v not in numbers:
            numbers.append(v)
    for m in PERCENT_RE.finditer(body[:3000]):
        v = m.group(0)
        if v not in numbers:
            numbers.append(v)
    return numbers[:cap]


def extract(filepath, body, fm, context):
    sent_match = SENT_RE.search(body[:2000])
    last_sent = None
    if sent_match:
        last_sent = sent_match.group(1)
    elif fm.get("sent"):
        last_sent = iso_date_from(fm.get("sent"))

    fields = {
        "biz_doc_kind": _kind(filepath, body),
        "biz_audience": _audience(body, fm),
        "biz_last_sent_iso": last_sent,
        "biz_version": _version(filepath, body),
        "biz_key_numbers": _key_numbers(body),
        "biz_recipients": match_people(body, context["crm_names"]),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
