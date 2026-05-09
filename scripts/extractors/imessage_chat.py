#!/usr/bin/env python3
"""
extractors/imessage_chat.py — structured metadata for iMessage chat exports
written by the bridge wrapper at ~/.local/bin/imessage-export-vault.sh.

Type: `imessage-chat` (hyphenated in source; dispatcher normalizes to
`imessage_chat` for module lookup).

Each chat file shape:
    ---
    chat_guids: [...]
    chat_rowids: [...]
    contact: <display name>
    emails: <single str OR list>
    phones: [...]
    kind: direct | group
    service: iMessage | SMS | Mixed | RCS
    message_count: <int>
    first_message: '<YYYY-MM-DD>'
    last_message: '<YYYY-MM-DD>'
    last_message_ts: <unix>
    last_sync: '<YYYY-MM-DD>'
    type: imessage-chat
    ---
    ## YYYY-MM-DD
    **HH:MM AM/PM** <Sender>: <text>          # outgoing sender == "You"
    **HH:MM AM/PM** <Sender>: [Voice note] <transcript>
      [attachment expired: <filename>]
      [file: [[Attachments/...]]]
    > <Sender>: <quoted text>                  # reply-quote line

Field naming intentionally mirrors whatsapp_chat (s/whatsapp_/imessage_/) so
cross-channel Dataview queries work. Adds three iMessage-specific fields:
imessage_service, imessage_attachment_count, imessage_attachment_expired_count,
imessage_reply_quote_count. Zero LLM. All fields regex / count / passthrough.
"""
import datetime as _dt
import re

from _base import (
    count_words, iso_date_from, wikilinks_in, match_people,
    ExtractionResult,
)

AUTO_FIELDS = (
    "imessage_chat_kind",
    "imessage_contact_name",
    "imessage_service",
    "imessage_message_count",
    "imessage_my_msg_count",
    "imessage_their_msg_count",
    "imessage_first_iso",
    "imessage_last_iso",
    "imessage_days_active",
    "imessage_dormancy_days",
    "imessage_density_per_day",
    "imessage_voice_note_count",
    "imessage_voice_note_transcribed_count",
    "imessage_attachment_count",
    "imessage_attachment_expired_count",
    "imessage_reply_quote_count",
    "imessage_concepts_extracted",
    "imessage_people_mentioned",
    "imessage_decision_signal",
    "word_count",
)

# **HH:MM AM/PM** Sender: rest
MSG_LINE_RE = re.compile(
    r"^\*\*(\d{1,2}:\d{2}(?:\s*[AP]M)?)\*\*\s+([^:]+):\s*(.*)$",
    re.MULTILINE,
)
DAY_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
VOICE_NOTE_RE = re.compile(r"\[Voice note\]")
VOICE_NOTE_TRANSCRIBED_RE = re.compile(r"\[Voice note\][ \t]+[^\s\n]")
# Resolved attachment: "[file: [[Attachments/...]]]"
ATTACHMENT_RE = re.compile(r"\[file:\s*\[\[Attachments/")
# Expired attachment: "[attachment expired: <filename>]"
ATTACHMENT_EXPIRED_RE = re.compile(r"\[attachment expired:")
# Reply-quote line: "> Sender: text"
REPLY_QUOTE_RE = re.compile(r"^>\s+[A-Za-z][^:\n]{0,80}:", re.MULTILINE)
# Decision-stub trigger words (mirror the WhatsApp + bridge auto-stub rule)
DECISION_KEYWORDS = re.compile(
    r"(?i)\b(exception|incident|pricing|escalation|outage|edge\s*case|refund)\b"
)

VALID_SERVICES = {"imessage", "sms", "mixed", "rcs"}


def _chat_kind(fm):
    raw = (fm.get("kind") or fm.get("chat_type") or "").strip().lower()
    if raw in ("direct", "group"):
        return raw
    # group iMessage chats have multiple chat_guids OR a chat_id starting with "chat"
    guids = fm.get("chat_guids")
    if isinstance(guids, list):
        for g in guids:
            if isinstance(g, str) and g.startswith("chat") and ";chat" in g:
                return "group"
    return "direct"


def _service(fm):
    raw = (fm.get("service") or "").strip()
    if not raw:
        return None
    low = raw.lower()
    return raw if low in VALID_SERVICES else raw  # passthrough; preserves casing


def _msg_counts(body):
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
    message_count = fm_msg_count if fm_msg_count > 0 else scan_total

    days = _days_active(body)
    voice_total = len(VOICE_NOTE_RE.findall(body))
    voice_transcribed = len(VOICE_NOTE_TRANSCRIBED_RE.findall(body))
    attachments_resolved = len(ATTACHMENT_RE.findall(body))
    attachments_expired = len(ATTACHMENT_EXPIRED_RE.findall(body))
    reply_quotes = len(REPLY_QUOTE_RE.findall(body))

    fields = {
        "imessage_chat_kind": _chat_kind(fm),
        "imessage_contact_name": fm.get("contact") or None,
        "imessage_service": _service(fm),
        "imessage_message_count": message_count,
        "imessage_my_msg_count": mine,
        "imessage_their_msg_count": theirs,
        "imessage_first_iso": first_iso,
        "imessage_last_iso": last_iso,
        "imessage_days_active": days,
        "imessage_dormancy_days": _dormancy(last_iso),
        "imessage_density_per_day": _density(message_count, days),
        "imessage_voice_note_count": voice_total,
        "imessage_voice_note_transcribed_count": voice_transcribed,
        "imessage_attachment_count": attachments_resolved,
        "imessage_attachment_expired_count": attachments_expired,
        "imessage_reply_quote_count": reply_quotes,
        "imessage_concepts_extracted": wikilinks_in(body)[:25],
        "imessage_people_mentioned": match_people(body, crm_names, cap=20),
        "imessage_decision_signal": bool(DECISION_KEYWORDS.search(body)),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
