#!/usr/bin/env python3
"""
extractors/asset.py — structured metadata for brand/creative assets.
Type: `asset`.
"""
import re

from _base import (
    count_words, iso_date_from, ExtractionResult,
)

AUTO_FIELDS = (
    "asset_kind", "asset_last_updated_iso", "asset_status", "word_count",
)

KIND_KEYWORDS = {
    "logo": ["logo"],
    "brand_kit": ["brand kit", "brand guide"],
    "template": ["template"],
    "image": ["image", "photo", "png", "jpg"],
    "deck": ["deck", "slide"],
    "copy": ["copy", "tagline"],
}


def _kind(filepath, body, fm):
    if fm.get("asset_kind"):
        return str(fm["asset_kind"]).strip()
    haystack = (filepath + " " + body[:500]).lower()
    for kind, keywords in KIND_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return kind
    return None


def extract(filepath, body, fm, context):
    fields = {
        "asset_kind": _kind(filepath, body, fm),
        "asset_last_updated_iso": iso_date_from(fm.get("last_updated")) or iso_date_from(fm.get("updated")),
        "asset_status": fm.get("status"),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
