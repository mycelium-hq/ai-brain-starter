#!/usr/bin/env python3
"""
extractors/ai_chat.py — structured metadata for AI conversations.
Type: `ai_chat`, also `chat`, `conversation`.
"""
import os
import re

from _base import (
    extract_section, count_words, iso_date_from, wikilinks_in,
    ExtractionResult,
)

AUTO_FIELDS = (
    "chat_model", "chat_date_iso", "chat_topic", "chat_concepts_touched",
    "chat_insights_captured", "chat_length_approx", "word_count",
)

MODEL_MARKERS = {
    "claude": ["claude", "anthropic"],
    "gpt": ["gpt", "openai", "chatgpt"],
    "gemini": ["gemini", "bard", "google"],
    "perplexity": ["perplexity"],
    "minimax": ["minimax"],
}


def _model(filepath, body, fm):
    if fm.get("model"):
        return str(fm["model"]).lower().strip()
    basename = os.path.basename(filepath).lower()
    head = body[:800].lower()
    for model, markers in MODEL_MARKERS.items():
        if any(m in basename for m in markers) or any(m in head for m in markers):
            return model
    return None


def _topic(filepath, body):
    """Topic from first h1 or filename."""
    m = re.search(r"(?m)^#\s+(.+?)$", body[:800])
    if m:
        return m.group(1).strip().lstrip("[").rstrip("]")
    return os.path.splitext(os.path.basename(filepath))[0]


def _concepts(body, fm):
    """Passthrough fm.concepts (if list) + wikilinks from top of body."""
    out = []
    existing = fm.get("concepts")
    if existing and isinstance(existing, list):
        for c in existing:
            c = str(c).replace("[[", "").replace("]]", "").strip()
            if c and c not in out:
                out.append(c)
    for lnk in wikilinks_in(body[:3000]):
        if lnk and lnk not in out:
            out.append(lnk)
    return out[:25]


def _insights(body, cap=8):
    """Bullets under ## Insights / ## Key Takeaways."""
    for header in (r"^##\s+Insights", r"^##\s+Key Takeaways", r"^##\s+Takeaways"):
        section = extract_section(body, header)
        if section:
            items = [ln.strip()[2:].strip() for ln in section.split("\n")
                     if ln.strip().startswith(("- ", "* "))]
            return [i for i in items if i][:cap]
    return []


def _length_bucket(word_count):
    if word_count < 300:
        return "short"
    if word_count < 1500:
        return "mid"
    return "long"


def extract(filepath, body, fm, context):
    wc = count_words(body)
    fields = {
        "chat_model": _model(filepath, body, fm),
        "chat_date_iso": iso_date_from(fm.get("date")) or iso_date_from(fm.get("creationDate")),
        "chat_topic": _topic(filepath, body),
        "chat_concepts_touched": _concepts(body, fm),
        "chat_insights_captured": _insights(body),
        "chat_length_approx": _length_bucket(wc),
        "word_count": wc,
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
