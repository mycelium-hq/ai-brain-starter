#!/usr/bin/env python3
"""
ingest.py: GitHub-to-vault normalizer for the ingest-github skill.

Reads a JSON payload on stdin (repo metadata + PRs + issues + commits,
already pulled by the LLM via the GitHub MCP), writes a vault file at
External Inputs/GitHub/<owner-repo>/<YYYY-MM-DD>.md.

Stdin shape:
{
  "repo": "owner/repo",
  "days": 7,
  "vault_root": "/abs/path/to/vault",
  "ingested_at_iso": "2026-04-30T19:30:00",
  "target_date": "2026-04-30",
  "pull_requests": [...],
  "issues": [...],
  "commits": [...]
}

Stdout: human-readable summary.
Exit non-zero on any failure (no silent partial writes).

CLI usage:
  python3 ingest.py --help
  python3 ingest.py owner/repo --days 7 [--vault-root /path] < payload.json
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
    excerpt,
    now_iso,
    slug_repo,
    to_local_str,
    today_iso,
    yaml_escape,
    yaml_int_array,
)

BODY_EXCERPT_LIMIT = 800


def normalize_pull_requests(prs: list) -> tuple[str, list[int]]:
    """Render PR section. Return (markdown_block, list of PR numbers)."""
    if not prs:
        return "", []
    sorted_prs = sorted(prs, key=lambda p: p.get("merged_at") or "", reverse=True)
    lines = ["## Merged PRs", ""]
    pr_ids: list[int] = []
    for pr in sorted_prs:
        number = pr.get("number")
        if number is None:
            continue
        pr_ids.append(number)
        title = pr.get("title", "(no title)")
        author = pr.get("author") or "unknown"
        merged_at = to_local_str(pr.get("merged_at", ""))
        url = pr.get("url", "")
        body = excerpt(pr.get("body", ""), BODY_EXCERPT_LIMIT)
        linked = pr.get("linked_issues", []) or []

        lines.append(f"### #{number} {title}")
        lines.append("")
        lines.append(f"**Author:** {author}  ")
        lines.append(f"**Merged:** {merged_at}  ")
        if url:
            lines.append(f"**URL:** {url}  ")
        if linked:
            linked_str = ", ".join(f"#{n}" for n in linked)
            lines.append(f"**Linked issues:** {linked_str}  ")
        lines.append("")
        lines.append(body)
        lines.append("")
    return "\n".join(lines), pr_ids


def normalize_issues(issues: list) -> tuple[str, list[int]]:
    if not issues:
        return "", []
    sorted_issues = sorted(issues, key=lambda i: i.get("created_at") or "", reverse=True)
    lines = ["## Issues", ""]
    issue_ids: list[int] = []
    for issue in sorted_issues:
        number = issue.get("number")
        if number is None:
            continue
        issue_ids.append(number)
        title = issue.get("title", "(no title)")
        author = issue.get("author") or "unknown"
        state = issue.get("state") or "unknown"
        created_at = to_local_str(issue.get("created_at", ""))
        url = issue.get("url", "")
        body = excerpt(issue.get("body", ""), BODY_EXCERPT_LIMIT)

        lines.append(f"### #{number} {title}")
        lines.append("")
        lines.append(f"**Author:** {author}  ")
        lines.append(f"**State:** {state}  ")
        lines.append(f"**Created:** {created_at}  ")
        if url:
            lines.append(f"**URL:** {url}  ")
        lines.append("")
        lines.append(body)
        lines.append("")
    return "\n".join(lines), issue_ids


def normalize_commits(commits: list) -> str:
    if not commits:
        return ""
    sorted_commits = sorted(commits, key=lambda c: c.get("committed_at") or "", reverse=True)
    lines = ["## Commits", ""]
    for commit in sorted_commits:
        sha = commit.get("sha", "")
        short_sha = sha[:7] if sha else "(no sha)"
        subject = commit.get("subject", "(no subject)")
        author = commit.get("author") or "unknown"
        committed_at = to_local_str(commit.get("committed_at", ""))
        url = commit.get("url", "")
        body = commit.get("body", "")

        lines.append(f"### {short_sha} {subject}")
        lines.append("")
        lines.append(f"**Author:** {author}  ")
        lines.append(f"**Committed:** {committed_at}  ")
        if url:
            lines.append(f"**URL:** {url}  ")
        if body and body.strip():
            lines.append("")
            lines.append(excerpt(body, BODY_EXCERPT_LIMIT))
        lines.append("")
    return "\n".join(lines)


def build_frontmatter(
    repo: str,
    days: int,
    target_date: str,
    item_count: int,
    pr_ids: list[int],
    issue_ids: list[int],
    ingested_at: str,
) -> str:
    start_date, end_date = date_range_strs(target_date, days)
    return (
        "---\n"
        "type: external-input\n"
        "source: github\n"
        f"repo: {yaml_escape(repo)}\n"
        f"date_range: {start_date}..{end_date}\n"
        f"item_count: {item_count}\n"
        f"ingested_at: {ingested_at}\n"
        "entity_ids:\n"
        f"  github_repo: {yaml_escape(repo)}\n"
        f"  github_pr: {yaml_int_array(pr_ids)}\n"
        f"  github_issue: {yaml_int_array(issue_ids)}\n"
        "---\n\n"
        f"# GitHub {repo} from {start_date} to {end_date}\n\n"
        f"_{item_count} item(s) ingested via /ingest-github._\n\n"
    )


def write_vault_file(payload: dict, body: str, frontmatter: str) -> Path:
    vault_root = Path(payload["vault_root"])
    repo_slug = slug_repo(payload["repo"])
    out_dir = vault_root / "External Inputs" / "GitHub" / repo_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    target_date = payload.get("target_date") or today_iso()
    out_path = out_dir / f"{target_date}.md"
    out_path.write_text(frontmatter + body, encoding="utf-8")
    return out_path


def run_from_payload(payload: dict) -> int:
    required = ["repo", "vault_root"]
    for k in required:
        if k not in payload:
            print(f"ERROR: missing required field: {k}", file=sys.stderr)
            return 2

    repo = payload["repo"]
    if "/" not in repo:
        print(f"ERROR: repo must be 'owner/repo', got: {repo}", file=sys.stderr)
        return 2

    days = int(payload.get("days", 7))
    target_date = payload.get("target_date") or today_iso()
    ingested_at = payload.get("ingested_at_iso", now_iso())

    prs = payload.get("pull_requests", []) or []
    issues = payload.get("issues", []) or []
    commits = payload.get("commits", []) or []

    pr_block, pr_ids = normalize_pull_requests(prs)
    issue_block, issue_ids = normalize_issues(issues)
    commit_block = normalize_commits(commits)

    body_parts: list[str] = []
    for block in (pr_block, issue_block, commit_block):
        if block.strip():
            body_parts.append(block)
    if not body_parts:
        body_parts.append("_No activity in the date range._\n")
    body = "\n".join(body_parts).rstrip() + "\n"

    item_count = len(prs) + len(issues) + len(commits)
    frontmatter = build_frontmatter(
        repo=repo,
        days=days,
        target_date=target_date,
        item_count=item_count,
        pr_ids=pr_ids,
        issue_ids=issue_ids,
        ingested_at=ingested_at,
    )

    out_path = write_vault_file(payload, body, frontmatter)

    print(
        f"Wrote {item_count} item(s) "
        f"({len(prs)} prs, {len(issues)} issues, {len(commits)} commits) "
        f"to {out_path}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ingest-github",
        description=(
            "Normalize GitHub repo activity (merged PRs, issues, commits) into a "
            "vault markdown file. Reads a JSON payload on stdin built by the LLM "
            "via the GitHub MCP. CLI flags are accepted but the payload on stdin "
            "is the source of truth."
        ),
    )
    parser.add_argument(
        "repo",
        nargs="?",
        help="Repository in 'owner/repo' form. Optional if stdin payload supplies it.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Lookback window in days (default 7). Overrides the value in the stdin payload if provided.",
    )
    parser.add_argument(
        "--vault-root",
        type=str,
        default=None,
        help="Absolute path to the vault root. Overrides the value in the stdin payload if provided.",
    )
    parser.add_argument(
        "--target-date",
        type=str,
        default=None,
        help="Target date in YYYY-MM-DD form (default: today). Overrides the value in the stdin payload.",
    )
    args = parser.parse_args()

    if sys.stdin.isatty():
        print(
            "ERROR: no JSON payload on stdin. Pipe the GitHub MCP results in. "
            "Run with --help for the expected payload shape.",
            file=sys.stderr,
        )
        return 2

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON on stdin: {e}", file=sys.stderr)
        return 2

    if args.repo:
        payload["repo"] = args.repo
    if args.days is not None:
        payload["days"] = args.days
    if args.vault_root:
        payload["vault_root"] = args.vault_root
    if args.target_date:
        payload["target_date"] = args.target_date

    return run_from_payload(payload)


if __name__ == "__main__":
    sys.exit(main())
