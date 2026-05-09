#!/usr/bin/env python3
"""
extractors/whatsapp_chat.py — structured metadata for WhatsApp chat exports
written by the bridge wrapper at ~/.local/bin/whatsapp-export-vault.sh.

Type: `whatsapp-chat` (hyphenated in source; dispatcher normalizes to
`whatsapp_chat` for module lookup).

Each chat file shape:
    ---
    type: whatsapp-chat
    contact: "<display name>"
    phone: "<E.164>"
    jid: "<wa-jid>"                   # optional, group chats end with @g.us
    chat_type: "direct" | "group"     # missing on older exports
    message_count: <int>
    first_message: <YYYY-MM-DD>
    last_message: <YYYY-MM-DD>
    last_sync: <YYYY-MM-DD>
    ---
    # WhatsApp: <contact>

    ## YYYY-MM-DD
    **HH:MM AM/PM** <Sender>: <text>       # outgoing sender == "You"
    **HH:MM AM/PM** <Sender>: [Voice note] <transcript>
    **HH:MM AM/PM** <Sender>: [Reaction: 😂]
    **HH:MM AM/PM** <Sender>: [Sticker]
    **HH:MM AM/PM** <Sender>: [Location]

Zero LLM. All fields are regex / count / passthrough / arithmetic.
"""
import datetime as _dt
import re

from _base import (
    count_words, iso_date_from, wikilinks_in, match_people,
    ExtractionResult,
)

AUTO_FIELDS = (
    "whatsapp_chat_kind",
    "whatsapp_contact_name",
    "whatsapp_message_count",
    "whatsapp_my_msg_count",
    "whatsapp_their_msg_count",
    "whatsapp_first_iso",
    "whatsapp_last_iso",
    "whatsapp_days_active",
    "whatsapp_dormancy_days",
    "whatsapp_density_per_day",
    "whatsapp_voice_note_count",
    "whatsapp_voice_note_transcribed_count",
    "whatsapp_reaction_count",
    "whatsapp_concepts_extracted",
    "whatsapp_people_mentioned",
    "whatsapp_decision_signal",
    "word_count",
)

# **HH:MM AM/PM** Sender: rest
MSG_LINE_RE = re.compile(
    r"^\*\*(\d{1,2}:\d{2}(?:\s*[AP]M)?)\*\*\s+([^:]+):\s*(.*)$",
    re.MULTILINE,
)
# ## YYYY-MM-DD day header
DAY_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
# Voice notes (with or without transcript)
VOICE_NOTE_RE = re.compile(r"\[Voice note\]")
# Voice note followed by transcript on the SAME line. \s matches \n, so the
# original `\s+\S` over-counted by matching the next message line. Pin to
# horizontal whitespace + non-newline content.
VOICE_NOTE_TRANSCRIBED_RE = re.compile(r"\[Voice note\][ \t]+[^\s\n]")
# Reaction marker
REACTION_RE = re.compile(r"\[Reaction:")
# Decision-stub trigger words (mirrors the bridge auto-stub rule in CLAUDE.md)
DECISION_KEYWORDS = re.compile(
    r"(?i)\b(exception|incident|pricing|escalation|outage|edge\s*case|refund)\b"
)


def _chat_kind(fm):
    raw = (fm.get("chat_type") or "").strip().lower()
    if raw in ("direct", "group"):
        return raw
    jid = str(fm.get("jid") or "")
    if "@g.us" in jid:
        return "group"
    return "direct"


def _msg_counts(body):
    """(total, mine, theirs) from **HH:MM** Sender: lines."""
    total = mine = theirs = 0
    for m in MSG_LINE_RE.finditer(body):
        total += 1
        sender = m.group(2).strip()
        if sender == "You":
            mine += 1
        else:
            theirs += 1
    return total, mine, theirs


def _days_active(body):
    return len(set(DAY_HEADER_RE.findall(body)))


def _dormancy(last_iso):
    if not last_iso:
        return None
    try:
        last = _dt.date.fromisoformat(last_iso)
        delta = (_dt.date.today() - last).days
        return delta if delta >= 0 else 0
    except Exception:
        return None


def _density(msg_count, days_active):
    if not msg_count or not days_active:
        return None
    return round(msg_count / days_active, 2)


def _safe_int(v, default=0):
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return default


def extract(filepath, body, fm, context):
    crm_names = context.get("crm_names", set())

    first_iso = iso_date_from(fm.get("first_message"))
    last_iso = iso_date_from(fm.get("last_message"))

    scan_total, mine, theirs = _msg_counts(body)
    fm_msg_count = _safe_int(fm.get("message_count"), default=scan_total)
    # Bridge frontmatter is authoritative when present; otherwise trust the scan.
    message_count = fm_msg_count if fm_msg_count > 0 else scan_total

    days = _days_active(body)
    voice_total = len(VOICE_NOTE_RE.findall(body))
    voice_transcribed = len(VOICE_NOTE_TRANSCRIBED_RE.findall(body))
    reactions = len(REACTION_RE.findall(body))

    fields = {
        "whatsapp_chat_kind": _chat_kind(fm),
        "whatsapp_contact_name": fm.get("contact") or None,
        "whatsapp_message_count": message_count,
        "whatsapp_my_msg_count": mine,
        "whatsapp_their_msg_count": theirs,
        "whatsapp_first_iso": first_iso,
        "whatsapp_last_iso": last_iso,
        "whatsapp_days_active": days,
        "whatsapp_dormancy_days": _dormancy(last_iso),
        "whatsapp_density_per_day": _density(message_count, days),
        "whatsapp_voice_note_count": voice_total,
        "whatsapp_voice_note_transcribed_count": voice_transcribed,
        "whatsapp_reaction_count": reactions,
        "whatsapp_concepts_extracted": wikilinks_in(body)[:25],
        "whatsapp_people_mentioned": match_people(body, crm_names, cap=20),
        "whatsapp_decision_signal": bool(DECISION_KEYWORDS.search(body)),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
