#!/usr/bin/env python3
"""
ingest.py, WhatsApp-to-vault normalizer for the ingest-whatsapp skill.

Reads a JSON payload on stdin (chat metadata + messages, already pulled
by the LLM via the WhatsApp MCP), writes a vault file at
External Inputs/WhatsApp/<chat-slug>/<YYYY-MM-DD>.md, scans for trigger
keywords, and creates Decision Log stubs at ``⚙️ Meta/Decisions/``.

Stdin shape:
{
  "chat_name": "Family group",
  "chat_jid": "120363025...@g.us",
  "chat_type": "group",
  "days": 7,
  "vault_root": "/abs/path/to/vault",
  "ingested_at_iso": "2026-04-30T19:30:00",
  "messages": [
    {
      "id": "ABCD-1234",
      "timestamp": 1729000000,
      "sender_jid": "5713001234@s.whatsapp.net",
      "sender_name": "Sister",
      "text": "...",
      "media_type": null,
      "reactions": [{"emoji": "❤️", "from": "Sister"}]
    }
  ]
}

PII guardrails:
- The output stays in the operator's local vault. The vault repo is
  local-only by convention. The personal-data scrub gate on the public
  ai-brain-starter repo blocks any push that contains personal tokens.
- Group-chat ingest captures non-consenting senders. Treat the file as
  confidential.

Stdout: human-readable summary.
Exit non-zero on any failure (no silent partial writes).

Stdlib only. Shared helpers come from skills/_shared/connector_utils.py.
The slack-style trigger-scan + decision-stub flow stays inline because
those primitives are not yet promoted into _shared.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# _shared is a sibling directory; add it to sys.path so we can import the
# helpers that already exist for the other ingest-* skills.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from connector_utils import (  # noqa: E402
    date_range_strs,
    fence_text,
    now_iso,
    sha8,
    slugify,
    today_iso,
    yaml_escape,
)


# Trigger-keyword set is identical to ingest-slack so the downstream
# Decision Log treats both connectors uniformly. Diverging would split the
# operator's edge-case-detection mental model.
TRIGGER_KEYWORDS = [
    "exception",
    "incident",
    "pricing",
    "escalation",
    "outage",
    "edge case",
    "one-off",
    "refund",
    "refund request",
    "custom deal",
    "special pricing",
]

_TRIGGER_PATTERN = re.compile(
    r"|".join(re.escape(k) for k in TRIGGER_KEYWORDS),
    flags=re.IGNORECASE,
)


def _ts_to_iso(ts: int | float | str) -> str:
    """WhatsApp MCP returns Unix seconds. Format as 'YYYY-MM-DD HH:MM' local."""
    try:
        seconds = float(ts)
    except (TypeError, ValueError):
        return ""
    return (
        datetime.fromtimestamp(seconds, tz=timezone.utc)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
    )


def _ts_to_unix(ts: int | float | str) -> float:
    try:
        return float(ts)
    except (TypeError, ValueError):
        return 0.0


def _sha8_msg(message_id: str) -> str:
    """The shared sha8 helper uses SHA-1, matching the synth-* skills.
    The slack ingest reaches for SHA-256 for its decision-stub keying. We
    pick SHA-256 here too so the "edge-case stub filename" semantics match
    ingest-slack character-for-character. Caller-side determinism is what
    matters; either hash is fine in isolation.
    """
    return hashlib.sha256((message_id or "").encode("utf-8")).hexdigest()[:8]


def _resolve_chat_slug(chat_name: str, chat_jid: str) -> str:
    """Slug the chat name. Fall back to chat-<sha8(jid)> for empty / non-ASCII
    titles that collapse to nothing.
    """
    candidate = slugify(chat_name or "", fallback="")
    if not candidate:
        # sha8() in connector_utils uses SHA-1; that is fine for this label.
        return f"chat-{sha8(chat_jid or 'anonymous')}"
    return candidate


def _format_reactions(reactions: list) -> str | None:
    """Group reactions by emoji, count and list senders.

    Returns a one-line summary like: '❤️ x2 from Sister, Mom; 👍 x1 from Mom'
    or None if there are no reactions.
    """
    if not reactions:
        return None
    grouped: dict[str, list[str]] = {}
    for r in reactions:
        if not isinstance(r, dict):
            continue
        emoji = r.get("emoji") or ""
        who = r.get("from") or r.get("sender_name") or r.get("sender_jid") or "unknown"
        if not emoji:
            continue
        grouped.setdefault(emoji, []).append(str(who))
    parts = []
    for emoji, names in grouped.items():
        parts.append(f"{emoji} x{len(names)} from {', '.join(names)}")
    if not parts:
        return None
    return "; ".join(parts)


def normalize_messages(payload: dict) -> tuple[str, int, list[tuple[str, str, str, str]], list[str]]:
    """Build the markdown body. Return (body, message_count, edge_case_records, message_ids).

    edge_case_records: list of (message_id, author, matched_keyword, excerpt)
    """
    messages = list(payload.get("messages") or [])
    # Sort ascending so the file reads chronologically (oldest first).
    messages.sort(key=lambda m: _ts_to_unix(m.get("timestamp")))

    body_parts: list[str] = []
    edge_cases: list[tuple[str, str, str, str]] = []
    message_ids: list[str] = []

    for msg in messages:
        msg_id = str(msg.get("id") or "")
        if msg_id:
            message_ids.append(msg_id)

        ts = msg.get("timestamp")
        when = _ts_to_iso(ts)
        author = (
            msg.get("sender_name")
            or msg.get("sender_jid")
            or "unknown"
        )
        text = msg.get("text") or ""
        media_type = msg.get("media_type")
        reactions = msg.get("reactions") or []

        body_parts.append(f"## {when} {author}")
        body_parts.append("")
        if media_type:
            body_parts.append(f"- **Media:** {media_type}")
        reaction_line = _format_reactions(reactions)
        if reaction_line:
            body_parts.append(f"- **Reactions:** {reaction_line}")
        if msg_id:
            body_parts.append(f"- **WhatsApp message ID:** `{msg_id}`")
        if media_type or reaction_line or msg_id:
            body_parts.append("")

        body_parts.append(fence_text(text) if text else "_(empty message)_")
        body_parts.append("")

        # Trigger-keyword scan against the text body. Media-only messages
        # never match because there is no text; that is intentional, edge
        # cases live in conversation, not in attachments.
        if text:
            for match in _TRIGGER_PATTERN.finditer(text):
                kw = match.group(0).lower()
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                excerpt = text[start:end].strip()
                edge_cases.append((msg_id, author, kw, excerpt))

    body = "\n".join(body_parts).rstrip() + "\n"
    return body, len(messages), edge_cases, message_ids


def build_frontmatter(
    payload: dict,
    message_count: int,
    message_ids: list[str],
    target_date: str,
    chat_slug: str,
) -> str:
    chat_name = payload.get("chat_name") or chat_slug
    chat_jid = payload.get("chat_jid") or ""
    chat_type = payload.get("chat_type") or "direct"
    days = int(payload.get("days") or 7)
    ingested_at = payload.get("ingested_at_iso") or now_iso()
    start_date, end_date = date_range_strs(target_date, days)

    lines = [
        "---",
        "type: external-input",
        "source: whatsapp",
        f"chat_name: {yaml_escape(chat_name)}",
        f"chat_jid: {yaml_escape(chat_jid)}",
        f"chat_type: {yaml_escape(chat_type)}",
        f"date_range: {start_date}..{end_date}",
        f"message_count: {message_count}",
        f"ingested_at: {ingested_at}",
        "entity_ids:",
        "  whatsapp:",
    ]
    if chat_jid:
        lines.append(f"    - {yaml_escape(chat_jid)}")
    else:
        lines.append("    []")
    lines.append("---")
    lines.append("")
    lines.append(f"# WhatsApp {chat_type} {chat_name}, {start_date} to {end_date}")
    lines.append("")
    lines.append(
        f"_{message_count} message(s) ingested via /ingest-whatsapp. "
        f"Source chat JID: `{chat_jid}`. Local vault only, do not share externally._"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def write_vault_file(
    payload: dict,
    body: str,
    frontmatter: str,
    target_date: str,
    chat_slug: str,
) -> Path:
    vault_root = Path(payload["vault_root"])
    out_dir = vault_root / "External Inputs" / "WhatsApp" / chat_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date}.md"
    out_path.write_text(frontmatter + body, encoding="utf-8")
    return out_path


def write_decision_stubs(
    payload: dict,
    edge_cases: list[tuple[str, str, str, str]],
    target_date: str,
    source_file: Path,
    chat_slug: str,
) -> list[Path]:
    """One stub per matched message. Multiple keywords in the same message
    collapse into a single stub (keyed by message_id), with all matched
    keywords listed in the matched_keyword field.

    Mirrors the ingest-slack stub shape so the Decision Log aggregator
    treats both connectors uniformly. The only WhatsApp-specific bits are
    the `source: whatsapp` frontmatter value and the absence of an archive
    URL (WhatsApp has no equivalent of the Slack permalink).
    """
    if not edge_cases:
        return []

    vault_root = Path(payload["vault_root"])
    decisions_dir = vault_root / "⚙️ Meta" / "Decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    chat_name = payload.get("chat_name") or chat_slug
    chat_jid = payload.get("chat_jid") or ""

    # Collapse by message_id: same message hit by 2+ keywords becomes 1 stub.
    by_id: dict[str, dict] = {}
    for msg_id, author, kw, excerpt in edge_cases:
        key = msg_id or f"unknown-{sha8(excerpt)}"
        if key not in by_id:
            by_id[key] = {
                "author": author,
                "keywords": [],
                "excerpt": excerpt,
                "msg_id": msg_id,
            }
        if kw not in by_id[key]["keywords"]:
            by_id[key]["keywords"].append(kw)

    stub_paths: list[Path] = []
    for key, info in by_id.items():
        stub_sha = _sha8_msg(key)
        stub_name = f"{target_date}-whatsapp-{chat_slug}-{stub_sha}.md"
        stub_path = decisions_dir / stub_name

        kw_str = ", ".join(info["keywords"])
        relative_source = source_file.relative_to(Path(payload["vault_root"]))
        body_lines = [
            "---",
            f"creationDate: {datetime.now().astimezone().strftime('%Y-%m-%dT%H:%M')}",
            "type: decision",
            f"decision_date: {target_date}",
            "floor: null",
            "stakes: medium",
            "speed: instant",
            "pattern: external-edge-case",
            "outcome: ",
            "decision_type: external-edge-case",
            f"source: whatsapp",
            f"source_file: {yaml_escape(str(relative_source))}",
            f"source_chat_name: {yaml_escape(chat_name)}",
            f"source_chat_jid: {yaml_escape(chat_jid)}",
            f"source_message_id: {yaml_escape(info['msg_id'] or '')}",
            f"matched_keyword: {yaml_escape(kw_str)}",
            "memory_class: episodic",
            "entity_ids:",
            "  whatsapp:",
            f"    - {yaml_escape(chat_jid)}" if chat_jid else "    []",
            "next_step: ",
            "---",
            "",
            f"# {target_date}, WhatsApp {chat_name} edge case ({kw_str})",
            "",
            f"**Author:** {info['author']}",
            f"**Matched keyword(s):** {kw_str}",
            f"**Source chat:** {chat_name} (`{chat_jid}`)",
            f"**Source file:** [[{source_file.stem}]] (`{relative_source}`)",
            "",
            "## Excerpt",
            "",
            "> " + info["excerpt"].replace("\n", "\n> "),
            "",
            "## Decision",
            "",
            "_Fill in: was this an edge case worth a rule? a one-off? a real incident? "
            "Then fill `outcome` and `next_step` in the frontmatter._",
            "",
        ]
        stub_path.write_text("\n".join(body_lines), encoding="utf-8")
        stub_paths.append(stub_path)

    return stub_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "WhatsApp-to-vault normalizer. Reads a WhatsApp payload as JSON on "
            "stdin, writes a single dated vault file plus zero or more Decision "
            "Log stubs."
        ),
    )
    parser.add_argument(
        "--target-date",
        help="Override the target date (YYYY-MM-DD). Defaults to today in local time.",
    )
    parser.add_argument(
        "--vault-root",
        help="Override the vault root from the payload. Useful for tests.",
    )
    args = parser.parse_args()

    try:
        raw = sys.stdin.read()
    except Exception as e:
        print(f"ERROR: failed to read stdin: {e}", file=sys.stderr)
        return 2

    if not raw.strip():
        print("ERROR: empty stdin. Pipe a JSON payload from the orchestrator.", file=sys.stderr)
        return 2

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON on stdin: {e}", file=sys.stderr)
        return 2

    if args.vault_root:
        payload["vault_root"] = args.vault_root

    required = ["chat_jid", "vault_root"]
    for k in required:
        if k not in payload or not payload[k]:
            print(f"ERROR: missing required field: {k}", file=sys.stderr)
            return 2

    target_date = args.target_date or payload.get("target_date") or today_iso()
    chat_slug = _resolve_chat_slug(payload.get("chat_name") or "", payload["chat_jid"])

    body, message_count, edge_cases, message_ids = normalize_messages(payload)
    frontmatter = build_frontmatter(payload, message_count, message_ids, target_date, chat_slug)
    out_path = write_vault_file(payload, body, frontmatter, target_date, chat_slug)
    stub_paths = write_decision_stubs(payload, edge_cases, target_date, out_path, chat_slug)

    print(f"Wrote {message_count} message(s) to {out_path}")
    if stub_paths:
        print(f"Detected {len(stub_paths)} edge case(s). Stubs created at:")
        for p in stub_paths:
            print(f"  {p}")
        print("Review each and fill in `outcome` + `next_step`.")
    else:
        print("No edge cases detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
