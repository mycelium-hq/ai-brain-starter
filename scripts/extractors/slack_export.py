#!/usr/bin/env python3
"""
extractors/slack_export.py — structured metadata for the per-channel
cumulative Slack export written by the slack MCP's `read_channel` tool.

Type: `slack-export` (hyphenated; dispatcher normalizes to `slack_export`).

Distinct from `type: external-input` + `source: slack` (which the
ingest-slack skill writes per-day at `External Inputs/Slack/<channel>/<date>.md`).
This format is per-channel cumulative at `🤖 AI Chats/Slack/<workspace>/<channel>.md`,
overwritten on every MCP read_channel call.

File shape (from slack_mcp/_shared/markdown.py:channel_to_markdown):
    ---
    workspace: <alias>
    channel: <name>
    channel_id: <C...>
    exported: <YYYY-MM-DD>
    type: slack-export
    ---
    # #<name> — <YYYY-MM-DD>

    ## <user_name> — <when>
    <!-- ts: <ts> | iso: <iso> -->

    <message text>

Field prefix `slack_export_*` distinguishes from the external_input
extractor's `slack_*` fields. Cross-source queries can join on
`whatsapp_contact_name` / `imessage_contact_name` / `slack_export_channel`
or filter by file path.

Zero LLM. All fields regex / count / passthrough / arithmetic.
"""
import datetime as _dt
import os
import re
from collections import Counter

from _base import (
    count_words, iso_date_from, wikilinks_in, match_people,
    ExtractionResult,
)


def _my_names_from_env() -> set[str]:
    """Sender names treated as 'me' for the my/their split.

    Reads `MY_NAMES` env var (comma-separated list). Falls back to a
    common literal "You" so vaults that haven't configured the env still
    produce reasonable my/their splits when the source format uses "You"
    (e.g. WhatsApp + iMessage exports). Slack exports always use real
    display names, so without MY_NAMES configured, slack files report
    `slack_export_my_msg_count: 0` and `slack_export_their_msg_count: <total>`.

    To configure: `export MY_NAMES="Your Full Name,Your Display Name"`
    in your shell profile. The vault-metadata-extract script inherits.
    """
    raw = os.environ.get("MY_NAMES", "").strip()
    if not raw:
        return {"You"}
    return {n.strip() for n in raw.split(",") if n.strip()}


MY_NAMES = _my_names_from_env()

AUTO_FIELDS = (
    "slack_export_workspace",
    "slack_export_channel",
    "slack_export_channel_id",
    "slack_export_last_sync_iso",
    "slack_export_dormancy_days",
    "slack_export_message_count",
    "slack_export_unique_senders",
    "slack_export_top_senders",
    "slack_export_my_msg_count",
    "slack_export_their_msg_count",
    "slack_export_my_share_pct",
    "slack_export_attachment_count",
    "slack_export_link_count",
    "slack_export_concepts_extracted",
    "slack_export_people_mentioned",
    "slack_export_decision_signal",
    "word_count",
)

# Slack export message header: "## <Sender Name> — <when>"
# (note: <when> is human-readable like "Jan 5 2026, 3:45 PM" or similar; we
# just count the headers and split on " — " to extract sender)
MSG_HEADER_RE = re.compile(r"^##\s+(.+?)\s+—\s+.+?$", re.MULTILINE)
ATTACHMENT_RE = re.compile(r"^- 📎", re.MULTILINE)
URL_RE = re.compile(r"https?://\S+")
DECISION_KEYWORDS = re.compile(
    r"(?i)\b(exception|incident|pricing|escalation|outage|edge\s*case|refund)\b"
)

# Backwards-compat: callers that still reference the old name keep working.
ADELAIDA_NAMES = MY_NAMES


def _workspace_from_path(filepath):
    """Path: 🤖 AI Chats/Slack/<workspace>/<channel>.md → workspace."""
    parts = filepath.split(os.sep)
    for i, p in enumerate(parts):
        if p == "🤖 AI Chats" and i + 2 < len(parts) and parts[i + 1] == "Slack":
            return parts[i + 2] if not parts[i + 2].endswith(".md") else None
    return None


def _dormancy(iso):
    if not iso:
        return None
    try:
        d = _dt.date.fromisoformat(iso)
        delta = (_dt.date.today() - d).days
        return delta if delta >= 0 else 0
    except Exception:
        return None


def _msg_counts(body):
    """Returns (total, mine, theirs, sender_counter) by scanning ## headers."""
    senders = []
    for m in MSG_HEADER_RE.finditer(body):
        senders.append(m.group(1).strip())
    sender_counts = Counter(senders)
    total = sum(sender_counts.values())
    mine = sum(c for n, c in sender_counts.items() if n in MY_NAMES)
    theirs = total - mine
    return total, mine, theirs, sender_counts


def extract(filepath, body, fm, context):
    crm_names = context.get("crm_names", set())

    workspace = (fm.get("workspace") or "").strip() or _workspace_from_path(filepath)
    channel = (fm.get("channel") or "").strip() or None
    channel_id = (fm.get("channel_id") or "").strip() or None
    last_sync = iso_date_from(fm.get("exported"))

    total, mine, theirs, sender_counts = _msg_counts(body)
    unique_senders = len(sender_counts)
    top_senders = [
        f"{name} ({cnt})" for name, cnt in sender_counts.most_common(5)
    ]
    my_share = round(100.0 * mine / total, 1) if total else None

    fields = {
        "slack_export_workspace": workspace,
        "slack_export_channel": channel,
        "slack_export_channel_id": channel_id,
        "slack_export_last_sync_iso": last_sync,
        "slack_export_dormancy_days": _dormancy(last_sync),
        "slack_export_message_count": total,
        "slack_export_unique_senders": unique_senders,
        "slack_export_top_senders": top_senders,
        "slack_export_my_msg_count": mine,
        "slack_export_their_msg_count": theirs,
        "slack_export_my_share_pct": my_share,
        "slack_export_attachment_count": len(ATTACHMENT_RE.findall(body)),
        "slack_export_link_count": len(URL_RE.findall(body)),
        "slack_export_concepts_extracted": wikilinks_in(body)[:25],
        "slack_export_people_mentioned": match_people(body, crm_names, cap=20),
        "slack_export_decision_signal": bool(DECISION_KEYWORDS.search(body)),
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
