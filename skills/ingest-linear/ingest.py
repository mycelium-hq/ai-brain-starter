#!/usr/bin/env python3
"""
ingest.py, Linear-to-vault normalizer for the ingest-linear skill.

Reads a JSON payload on stdin (scope metadata + issues + comments +
history, already pulled by the LLM via the Linear MCP), writes a vault
file at External Inputs/Linear/<scope>/<YYYY-MM-DD>.md.

Stdout: human-readable summary.
Exit non-zero on any failure (no silent partial writes).

Stdlib only. Shared helpers come from skills/_shared/connector_utils.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# _shared is a sibling directory; add it to sys.path so we can import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from connector_utils import (
    date_range_strs,
    fence_text,
    now_iso,
    parse_iso,
    to_local_str,
    today_iso,
    yaml_escape,
)


def normalize_issues(payload: dict) -> tuple[str, int, int, int, list[str]]:
    """Build the markdown body. Return (body, issue_count, comment_count,
    history_count, identifiers).
    """
    issues = list(payload.get("issues") or [])
    # Sort chronologically by updatedAt ascending so the file reads as a
    # timeline. If updatedAt is missing, fall back to identifier.
    issues.sort(
        key=lambda i: (
            parse_iso(i.get("updatedAt") or "") or datetime.min.replace(tzinfo=timezone.utc),
            i.get("identifier", ""),
        )
    )

    body_parts: list[str] = []
    comment_count = 0
    history_count = 0
    identifiers: list[str] = []

    for issue in issues:
        identifier = issue.get("identifier") or "UNKNOWN"
        identifiers.append(identifier)
        title = issue.get("title") or "(no title)"
        url = issue.get("url") or ""
        state = issue.get("state") or "unknown"
        priority = issue.get("priority") or "none"
        assignee = issue.get("assignee") or "unassigned"
        creator = issue.get("creator") or "unknown"
        created = to_local_str(issue.get("createdAt") or "")
        updated = to_local_str(issue.get("updatedAt") or "")
        labels = issue.get("labels") or []
        description = issue.get("description") or ""

        body_parts.append(f"## {identifier} {title}")
        body_parts.append("")
        meta_lines = [
            f"- **URL:** {url}" if url else "- **URL:** _(missing)_",
            f"- **State:** {state}",
            f"- **Priority:** {priority}",
            f"- **Assignee:** {assignee}",
            f"- **Creator:** {creator}",
            f"- **Created:** {created}",
            f"- **Updated:** {updated}",
        ]
        if labels:
            meta_lines.append(f"- **Labels:** {', '.join(labels)}")
        body_parts.extend(meta_lines)
        body_parts.append("")
        body_parts.append("### Description")
        body_parts.append("")
        body_parts.append(fence_text(description))
        body_parts.append("")

        comments = issue.get("comments") or []
        if comments:
            body_parts.append("### Comments")
            body_parts.append("")
            for comment in comments:
                c_when = to_local_str(comment.get("createdAt") or "")
                c_author = comment.get("author") or "unknown"
                c_body = fence_text(comment.get("body") or "")
                body_parts.append(f"#### {c_when} {c_author}")
                body_parts.append("")
                body_parts.append(c_body)
                body_parts.append("")
                comment_count += 1

        history = issue.get("history") or []
        if history:
            body_parts.append("### History")
            body_parts.append("")
            for event in history:
                e_when = to_local_str(event.get("createdAt") or "")
                e_actor = event.get("actor") or "system"
                e_summary = event.get("summary") or "(unknown change)"
                body_parts.append(f"- {e_when} {e_actor}, {e_summary}")
                history_count += 1
            body_parts.append("")

    body = "\n".join(body_parts).rstrip() + "\n"
    return body, len(issues), comment_count, history_count, identifiers


def build_frontmatter(
    payload: dict,
    issue_count: int,
    comment_count: int,
    history_count: int,
    identifiers: list[str],
    target_date: str,
) -> str:
    scope = payload.get("scope", "")
    scope_kind = payload.get("scope_kind", "team")
    team_id = payload.get("team_id")
    project_id = payload.get("project_id")
    days = int(payload.get("days") or 7)
    ingested_at = payload.get("ingested_at_iso") or now_iso()
    start_date, end_date = date_range_strs(target_date, days)

    lines = [
        "---",
        "type: external-input",
        "source: linear",
        f"scope: {yaml_escape(scope)}",
        f"scope_kind: {scope_kind}",
        f"team_id: {yaml_escape(team_id) if team_id else 'null'}",
        f"project_id: {yaml_escape(project_id) if project_id else 'null'}",
        f"date_range: {start_date}..{end_date}",
        f"issue_count: {issue_count}",
        f"comment_count: {comment_count}",
        f"history_count: {history_count}",
        f"ingested_at: {ingested_at}",
        "entity_ids:",
        "  linear:",
    ]
    if identifiers:
        for ident in identifiers:
            lines.append(f"    - {yaml_escape(ident)}")
    else:
        lines.append("    []")
        # YAML note: an empty sequence is also valid as a flow style. Above
        # line keeps the field present without a child.
    lines.append("---")
    lines.append("")
    lines.append(f"# Linear {scope_kind} {scope}, {start_date} to {end_date}")
    lines.append("")
    lines.append(
        f"_{issue_count} issue(s), {comment_count} comment(s), {history_count} history "
        f"event(s) ingested via /ingest-linear._"
    )
    lines.append("")
    return "\n".join(lines)


def write_vault_file(payload: dict, body: str, frontmatter: str, target_date: str) -> Path:
    vault_root = Path(payload["vault_root"])
    scope = payload.get("scope", "unknown")
    out_dir = vault_root / "External Inputs" / "Linear" / scope
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date}.md"
    out_path.write_text(frontmatter + body, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Linear-to-vault normalizer. Reads a Linear payload as JSON on stdin, writes a single dated vault file.",
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

    required = ["scope", "vault_root"]
    for k in required:
        if k not in payload:
            print(f"ERROR: missing required field: {k}", file=sys.stderr)
            return 2

    target_date = args.target_date or payload.get("target_date") or today_iso()

    body, issue_count, comment_count, history_count, identifiers = normalize_issues(payload)
    frontmatter = build_frontmatter(
        payload, issue_count, comment_count, history_count, identifiers, target_date
    )
    out_path = write_vault_file(payload, body, frontmatter, target_date)

    print(
        f"Wrote {issue_count} issue(s), {comment_count} comment(s), "
        f"{history_count} history event(s) to {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
