#!/usr/bin/env python3
"""
ingest.py, Gmail-to-vault normalizer for the ingest-gmail skill.

Reads a JSON payload on stdin (scope metadata + messages, already pulled
by the LLM via the Google Workspace MCP), writes a vault file at
External Inputs/Gmail/<scope>/<YYYY-MM-DD>.md.

PII guardrails:
- Each message body is truncated to 500 chars before being written. The
  first 500 chars cover the sender, recipient, subject, and a fragment
  of the topic. Truncation is a volume cap, not a redaction.
- The output file should be treated as confidential. Never commit the
  file to a public repo. The personal-data scrub gate on the public
  repository blocks any push that contains personal tokens.

Stdout: human-readable summary.
Exit non-zero on any failure (no silent partial writes).

Stdlib only. Shared helpers come from skills/_shared/connector_utils.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# _shared is a sibling directory; add it to sys.path so we can import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from connector_utils import (
    date_range_strs,
    now_iso,
    sha8,
    slugify,
    to_local_sortkey,
    to_local_str,
    today_iso,
    truncate_body,
    yaml_escape,
)

BODY_TRUNCATE_CHARS = 500
TRUNCATE_MARKER = "\n\n[...truncated]"


def normalize_messages(payload: dict) -> tuple[str, int, list[str]]:
    """Build the markdown body. Return (body, message_count, message_ids)."""
    messages = list(payload.get("messages") or [])
    messages.sort(key=lambda m: to_local_sortkey(m.get("internal_date") or ""))

    body_parts: list[str] = []
    message_ids: list[str] = []

    for msg in messages:
        msg_id = msg.get("id") or ""
        if msg_id:
            message_ids.append(msg_id)
        sender = msg.get("from") or "(unknown sender)"
        when = to_local_str(msg.get("internal_date") or "")
        subject = msg.get("subject") or "(no subject)"
        to_field = msg.get("to") or []
        if isinstance(to_field, str):
            to_str = to_field
        else:
            to_str = ", ".join(to_field)
        cc_field = msg.get("cc") or []
        if isinstance(cc_field, str):
            cc_str = cc_field
        else:
            cc_str = ", ".join(cc_field)
        labels = msg.get("labels") or []
        body_text = msg.get("body_text") or msg.get("snippet") or ""

        body_parts.append(f"## {when} {sender}")
        body_parts.append("")
        body_parts.append(f"- **Subject:** {subject}")
        if to_str:
            body_parts.append(f"- **To:** {to_str}")
        if cc_str:
            body_parts.append(f"- **Cc:** {cc_str}")
        if labels:
            body_parts.append(f"- **Labels:** {', '.join(labels)}")
        if msg_id:
            body_parts.append(f"- **Gmail message ID:** `{msg_id}`")
        body_parts.append("")
        body_parts.append("### Body excerpt (max 500 chars)")
        body_parts.append("")
        body_parts.append(truncate_body(body_text, BODY_TRUNCATE_CHARS, TRUNCATE_MARKER))
        body_parts.append("")

    body = "\n".join(body_parts).rstrip() + "\n"
    return body, len(messages), message_ids


def build_frontmatter(
    payload: dict,
    message_count: int,
    message_ids: list[str],
    target_date: str,
) -> str:
    label_or_query = payload.get("label_or_query") or ""
    scope_kind = payload.get("scope_kind", "label")
    days = int(payload.get("days") or 7)
    ingested_at = payload.get("ingested_at_iso") or now_iso()
    start_date, end_date = date_range_strs(target_date, days)

    lines = [
        "---",
        "type: external-input",
        "source: gmail",
        f"label_or_query: {yaml_escape(label_or_query)}",
        f"scope_kind: {scope_kind}",
        f"date_range: {start_date}..{end_date}",
        f"message_count: {message_count}",
        f"ingested_at: {ingested_at}",
        "entity_ids:",
        "  gmail:",
    ]
    if message_ids:
        for mid in message_ids:
            lines.append(f"    - {yaml_escape(mid)}")
    else:
        lines.append("    []")
    lines.append("---")
    lines.append("")
    lines.append(f"# Gmail {scope_kind} {label_or_query}, {start_date} to {end_date}")
    lines.append("")
    lines.append(
        f"_{message_count} message(s) ingested via /ingest-gmail. Bodies truncated to "
        f"{BODY_TRUNCATE_CHARS} chars to limit bulk PII._"
    )
    lines.append("")
    return "\n".join(lines)


def resolve_scope_slug(payload: dict) -> str:
    """Pick the directory under External Inputs/Gmail/.

    Priority: explicit `scope_slug` from the orchestrator, then a slugified
    label name, then a query-<sha8> for free-text queries.
    """
    explicit = payload.get("scope_slug")
    if explicit:
        return slugify(explicit)
    label_or_query = payload.get("label_or_query") or "unknown"
    if payload.get("scope_kind") == "query":
        return f"query-{sha8(label_or_query)}"
    return slugify(label_or_query)


def write_vault_file(
    payload: dict,
    body: str,
    frontmatter: str,
    target_date: str,
    scope_slug: str,
) -> Path:
    vault_root = Path(payload["vault_root"])
    out_dir = vault_root / "External Inputs" / "Gmail" / scope_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date}.md"
    out_path.write_text(frontmatter + body, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Gmail-to-vault normalizer. Reads a Gmail payload as JSON on stdin, "
            "writes a single dated vault file. Truncates each body to 500 chars."
        ),
    )
    parser.add_argument(
        "--target-date",
        help="Override the target date (YYYY-MM-DD). Defaults to today in local time.",
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

    required = ["label_or_query", "vault_root"]
    for k in required:
        if k not in payload:
            print(f"ERROR: missing required field: {k}", file=sys.stderr)
            return 2

    target_date = args.target_date or payload.get("target_date") or today_iso()

    body, message_count, message_ids = normalize_messages(payload)
    frontmatter = build_frontmatter(payload, message_count, message_ids, target_date)
    scope_slug = resolve_scope_slug(payload)
    out_path = write_vault_file(payload, body, frontmatter, target_date, scope_slug)

    print(f"Wrote {message_count} message(s) to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
