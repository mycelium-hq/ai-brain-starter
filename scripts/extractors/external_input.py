#!/usr/bin/env python3
"""
extractors/external_input.py — structured metadata for ingested external inputs.

Type: `external-input` (hyphenated; dispatcher normalizes to `external_input`).

Routes by `source:` frontmatter field. Currently implements: slack.
Stubs for: notion, github, gmail, linear, whatsapp_ingest.

Each source has its own field prefix (slack_*, notion_*, etc.) so cross-source
queries work and field names never collide.

File shape (slack example):
    ---
    type: external-input
    source: slack
    channel: <channel-name>
    channel_id: <C064...>
    date_range: <YYYY-MM-DD..YYYY-MM-DD>
    message_count: <int>
    ingested_at: <ISO>
    ---
    # Slack #<channel> — <date> to <date>
    ## YYYY-MM-DD HH:MM <Sender Full Name>
    <message body>

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

# ────────────────────────────────────────────────────────────────────────
# AUTO_FIELDS: union across all source variants. The dispatcher uses this
# for idempotency. Each source's extract() function only writes its own
# subset of fields; missing values are skipped at render time (_base
# render_fields drops None/empty/[]).
# ────────────────────────────────────────────────────────────────────────
AUTO_FIELDS = (
    # Common across all sources
    "external_source",
    "external_dormancy_days",
    "word_count",
    # Slack
    "slack_channel",
    "slack_channel_id",
    "slack_workspace",
    "slack_date_start_iso",
    "slack_date_end_iso",
    "slack_message_count",
    "slack_unique_senders",
    "slack_top_senders",
    "slack_my_msg_count",
    "slack_their_msg_count",
    "slack_my_share_pct",
    "slack_channel_mention_count",
    "slack_link_count",
    "slack_concepts_extracted",
    "slack_people_mentioned",
    "slack_decision_signal",
)

# Sender names treated as "me" for the my/their split. Reads MY_NAMES env
# (comma-separated). Defaults to {"You"} which matches WhatsApp + iMessage
# bridge convention. For Slack: configure MY_NAMES with your real Slack
# display name(s). Without configuration, Slack `_my_msg_count` will be 0.
def _my_names_from_env() -> set[str]:
    raw = os.environ.get("MY_NAMES", "").strip()
    if not raw:
        return {"You"}
    return {n.strip() for n in raw.split(",") if n.strip()}


MY_NAMES = _my_names_from_env()
# Backwards-compat alias for the old name.
ADELAIDA_NAMES = MY_NAMES

# Decision-stub trigger words (mirror the rule in CLAUDE.md and the WA/iMessage extractors)
DECISION_KEYWORDS = re.compile(
    r"(?i)\b(exception|incident|pricing|escalation|outage|edge\s*case|refund)\b"
)

# Slack message header: "## YYYY-MM-DD HH:MM <Sender Name>"
SLACK_MSG_HEADER_RE = re.compile(
    r"^##\s+(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s+(.+?)\s*$",
    re.MULTILINE,
)
# <!channel> mention
SLACK_CHANNEL_MENTION_RE = re.compile(r"<!channel>")
# URL detection
URL_RE = re.compile(r"https?://\S+")


def _dormancy_from_iso(last_iso):
    if not last_iso:
        return None
    try:
        last = _dt.date.fromisoformat(last_iso)
        delta = (_dt.date.today() - last).days
        return delta if delta >= 0 else 0
    except Exception:
        return None


def _safe_int(v, default=0):
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return default


def _parse_date_range(raw):
    """Parse 'YYYY-MM-DD..YYYY-MM-DD' to (start_iso, end_iso) or (None, None)."""
    if not raw:
        return None, None
    s = str(raw).strip()
    parts = s.split("..")
    if len(parts) != 2:
        # single date as both start and end
        only = iso_date_from(s)
        return only, only
    return iso_date_from(parts[0]), iso_date_from(parts[1])


def _slack_workspace_from_path(filepath):
    """Detect workspace from path. Returns None if not embedded.

    Two known layouts:
      - slack ingest files: External Inputs/Slack/<channel>/<date>.md  (NO workspace)
      - slack MCP export:   🤖 AI Chats/Slack/<workspace>/<channel>.md (workspace at index after Slack)

    Only the AI-Chats pattern carries a workspace. The ingest-file pattern does not.
    """
    parts = filepath.split(os.sep)
    for i, p in enumerate(parts):
        if p == "🤖 AI Chats" and i + 2 < len(parts) and parts[i + 1] == "Slack":
            ws = parts[i + 2]
            return ws if not ws.endswith(".md") else None
    return None


def _extract_slack(filepath, body, fm, context):
    crm_names = context.get("crm_names", set())

    channel = (fm.get("channel") or "").strip() or None
    channel_id = (fm.get("channel_id") or "").strip() or None
    workspace = _slack_workspace_from_path(filepath)

    start_iso, end_iso = _parse_date_range(fm.get("date_range"))
    fm_msg_count = _safe_int(fm.get("message_count"), default=0)

    # Scan ## headers for senders
    senders = []
    for m in SLACK_MSG_HEADER_RE.finditer(body):
        senders.append(m.group(3).strip())

    scan_total = len(senders)
    message_count = fm_msg_count if fm_msg_count > 0 else scan_total

    sender_counts = Counter(senders)
    unique_senders = len(sender_counts)
    top_senders = [
        f"{name} ({cnt})" for name, cnt in sender_counts.most_common(5)
    ]

    mine = sum(c for n, c in sender_counts.items() if n in MY_NAMES)
    theirs = scan_total - mine
    my_share = round(100.0 * mine / scan_total, 1) if scan_total else None

    chan_mentions = len(SLACK_CHANNEL_MENTION_RE.findall(body))
    link_count = len(URL_RE.findall(body))

    fields = {
        "external_source": "slack",
        "external_dormancy_days": _dormancy_from_iso(end_iso),
        "word_count": count_words(body),
        "slack_channel": channel,
        "slack_channel_id": channel_id,
        "slack_workspace": workspace,
        "slack_date_start_iso": start_iso,
        "slack_date_end_iso": end_iso,
        "slack_message_count": message_count,
        "slack_unique_senders": unique_senders,
        "slack_top_senders": top_senders,
        "slack_my_msg_count": mine,
        "slack_their_msg_count": theirs,
        "slack_my_share_pct": my_share,
        "slack_channel_mention_count": chan_mentions,
        "slack_link_count": link_count,
        "slack_concepts_extracted": wikilinks_in(body)[:25],
        "slack_people_mentioned": match_people(body, crm_names, cap=20),
        "slack_decision_signal": bool(DECISION_KEYWORDS.search(body)),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)


# Future sources (each returns ExtractionResult or None for now).
def _extract_notion(filepath, body, fm, context):
    return None


def _extract_github(filepath, body, fm, context):
    return None


def _extract_gmail(filepath, body, fm, context):
    return None


def _extract_linear(filepath, body, fm, context):
    return None


def _extract_whatsapp_ingest(filepath, body, fm, context):
    # WhatsApp ingest output. Different shape from the bridge's per-contact
    # files in 🤖 AI Chats/WhatsApp (which use type: whatsapp-chat).
    return None


SOURCE_HANDLERS = {
    "slack": _extract_slack,
    "notion": _extract_notion,
    "github": _extract_github,
    "gmail": _extract_gmail,
    "linear": _extract_linear,
    "whatsapp": _extract_whatsapp_ingest,
}


def extract(filepath, body, fm, context):
    source = (fm.get("source") or "").strip().lower()
    handler = SOURCE_HANDLERS.get(source)
    if handler is None:
        return None
    return handler(filepath, body, fm, context)
