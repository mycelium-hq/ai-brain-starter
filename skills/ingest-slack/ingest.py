#!/usr/bin/env python3
"""
ingest.py — Slack-to-vault normalizer for the ingest-slack skill.

Reads a JSON payload on stdin (channel metadata + messages + threads,
already pulled by the LLM via the Slack MCP), writes a vault file at
External Inputs/Slack/<channel>/<YYYY-MM-DD>.md, scans for trigger
keywords, and creates Decision Log stubs at ⚙️ Meta/Decisions/.

Stdin shape:
{
  "channel_name": "general",
  "channel_id": "C064CG22UUU",
  "days": 7,
  "vault_root": "/abs/path/to/vault",
  "ingested_at_iso": "2026-04-30T19:30:00",
  "messages": [
    {
      "ts": "1234567890.123456",
      "author": "Display Name",
      "user_id": "U...",
      "text": "...",
      "thread_url": "https://workspace.slack.com/archives/...",
      "thread": [
        {"ts": "...", "author": "...", "text": "..."}
      ]
    }
  ]
}

Stdout: human-readable summary.
Exit non-zero on any failure (no silent partial writes).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

# Pre-compile a single case-insensitive regex that matches any trigger.
# Word boundaries on the long forms keep "refund" from also matching inside
# "refunded" if we wanted that, but Slack threads use both forms naturally,
# so we keep the substring match. Edge case is two words; handle that explicitly.
_TRIGGER_PATTERN = re.compile(
    r"|".join(re.escape(k) for k in TRIGGER_KEYWORDS),
    flags=re.IGNORECASE,
)


def _ts_to_iso(ts: str) -> str:
    """Slack ts is a unix-seconds string with a fractional part."""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _ts_to_date(ts: str) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def _sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def _yaml_escape(value: str) -> str:
    """Escape a string for safe YAML scalar inclusion."""
    if any(c in value for c in [':', '#', '\n', '"', "'", '[', ']', '{', '}']):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return value


def _fence_text(text: str) -> str:
    """Slack messages can contain markdown that breaks our outer markdown.
    Strip backslashes that escape markdown chars (Slack autoescapes), keep
    everything else verbatim. Indent triple backticks to break fences.
    """
    if not text:
        return "_(empty message)_"
    cleaned = text.replace("```", "` ` `")
    return cleaned


def normalize_messages(payload: dict) -> tuple[str, int, list[tuple[str, str, str, str]]]:
    """Build the markdown body. Return (body, message_count, edge_case_records).

    edge_case_records: list of (message_ts, author, matched_keyword, excerpt)
    """
    messages = sorted(payload.get("messages", []), key=lambda m: float(m["ts"]))
    body_parts = []
    edge_cases: list[tuple[str, str, str, str]] = []

    for msg in messages:
        ts = msg["ts"]
        author = msg.get("author") or msg.get("user_id") or "unknown"
        text = msg.get("text", "")
        when = _ts_to_iso(ts)
        body_parts.append(f"## {when} {author}")
        body_parts.append("")
        body_parts.append(_fence_text(text))
        body_parts.append("")

        # Scan parent message
        for match in _TRIGGER_PATTERN.finditer(text):
            kw = match.group(0).lower()
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            excerpt = text[start:end].strip()
            edge_cases.append((ts, author, kw, excerpt))

        # Thread replies (skip the first one if it duplicates parent)
        thread = msg.get("thread", []) or []
        for reply in thread:
            r_ts = reply.get("ts", "")
            if r_ts == ts:
                continue
            r_author = reply.get("author") or reply.get("user_id") or "unknown"
            r_text = reply.get("text", "")
            r_when = _ts_to_iso(r_ts) if r_ts else when
            body_parts.append(f"### {r_when} {r_author}")
            body_parts.append("")
            body_parts.append(_fence_text(r_text))
            body_parts.append("")

            for match in _TRIGGER_PATTERN.finditer(r_text):
                kw = match.group(0).lower()
                start = max(0, match.start() - 100)
                end = min(len(r_text), match.end() + 100)
                excerpt = r_text[start:end].strip()
                edge_cases.append((r_ts, r_author, kw, excerpt))

    body = "\n".join(body_parts).rstrip() + "\n"
    return body, len(messages), edge_cases


def build_frontmatter(payload: dict, message_count: int, target_date: str) -> str:
    channel = payload["channel_name"]
    channel_id = payload["channel_id"]
    days = payload.get("days", 7)
    ingested_at = payload.get("ingested_at_iso", datetime.now().astimezone().isoformat(timespec="seconds"))
    end_date = target_date
    if days > 1:
        start_date = (datetime.fromisoformat(target_date) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    else:
        start_date = target_date
    return (
        "---\n"
        f"type: external-input\n"
        f"source: slack\n"
        f"channel: {_yaml_escape(channel)}\n"
        f"channel_id: {channel_id}\n"
        f"date_range: {start_date}..{end_date}\n"
        f"message_count: {message_count}\n"
        f"ingested_at: {ingested_at}\n"
        "---\n\n"
        f"# Slack #{channel} — {start_date} to {end_date}\n\n"
        f"_{message_count} message(s) ingested via /ingest-slack. Source channel ID: `{channel_id}`._\n\n"
    )


def write_vault_file(payload: dict, body: str, message_count: int, target_date: str) -> Path:
    vault_root = Path(payload["vault_root"])
    channel = payload["channel_name"]
    out_dir = vault_root / "External Inputs" / "Slack" / channel
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date}.md"
    frontmatter = build_frontmatter(payload, message_count, target_date)
    out_path.write_text(frontmatter + body, encoding="utf-8")
    return out_path


def write_decision_stubs(
    payload: dict,
    edge_cases: list[tuple[str, str, str, str]],
    target_date: str,
    source_file: Path,
) -> list[Path]:
    """One stub per matched message. Multiple keywords in the same message
    collapse into a single stub (keyed by message_ts), with all matched
    keywords listed in the matched_keyword field.
    """
    if not edge_cases:
        return []

    vault_root = Path(payload["vault_root"])
    decisions_dir = vault_root / "⚙️ Meta" / "Decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    channel = payload["channel_name"]
    channel_id = payload["channel_id"]

    # Collapse by message_ts: same message hit by 2+ keywords becomes 1 stub
    by_ts: dict[str, dict] = {}
    for ts, author, kw, excerpt in edge_cases:
        if ts not in by_ts:
            by_ts[ts] = {
                "author": author,
                "keywords": [],
                "excerpt": excerpt,
            }
        if kw not in by_ts[ts]["keywords"]:
            by_ts[ts]["keywords"].append(kw)

    stub_paths: list[Path] = []
    for ts, info in by_ts.items():
        sha = _sha8(ts)
        stub_name = f"{target_date}-slack-{channel}-{sha}.md"
        stub_path = decisions_dir / stub_name

        # Slack archive URL: /archives/<channel_id>/p<ts-with-no-dot>
        ts_no_dot = ts.replace(".", "")
        thread_url = f"https://slack.com/archives/{channel_id}/p{ts_no_dot}"

        kw_str = ", ".join(info["keywords"])
        body_lines = [
            "---",
            f"creationDate: {datetime.now().astimezone().strftime('%Y-%m-%dT%H:%M')}",
            f"type: decision",
            f"decision_date: {target_date}",
            f"floor: null",
            f"stakes: medium",
            f"speed: instant",
            f"pattern: external-edge-case",
            f"outcome: ",
            f"decision_type: external-edge-case",
            f"source_file: {_yaml_escape(str(source_file.relative_to(Path(payload['vault_root']))))}",
            f"source_thread_url: {thread_url}",
            f"source_message_ts: {ts}",
            f"matched_keyword: {_yaml_escape(kw_str)}",
            f"next_step: ",
            "---",
            "",
            f"# {target_date} — Slack #{channel} edge case ({kw_str})",
            "",
            f"**Author:** {info['author']}",
            f"**Matched keyword(s):** {kw_str}",
            f"**Source thread:** {thread_url}",
            f"**Source file:** [[{source_file.stem}]] (`{source_file.relative_to(Path(payload['vault_root']))}`)",
            "",
            "## Excerpt",
            "",
            "> " + info["excerpt"].replace("\n", "\n> "),
            "",
            "## Decision",
            "",
            "_Fill in: was this an edge case worth a rule? a one-off? a real incident? Then fill `outcome` and `next_step` in the frontmatter._",
            "",
        ]
        stub_path.write_text("\n".join(body_lines), encoding="utf-8")
        stub_paths.append(stub_path)

    return stub_paths


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON on stdin: {e}", file=sys.stderr)
        return 2

    required = ["channel_name", "channel_id", "vault_root"]
    for k in required:
        if k not in payload:
            print(f"ERROR: missing required field: {k}", file=sys.stderr)
            return 2

    target_date = payload.get("target_date") or datetime.now().astimezone().strftime("%Y-%m-%d")

    body, message_count, edge_cases = normalize_messages(payload)

    out_path = write_vault_file(payload, body, message_count, target_date)

    stub_paths = write_decision_stubs(payload, edge_cases, target_date, out_path)

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
