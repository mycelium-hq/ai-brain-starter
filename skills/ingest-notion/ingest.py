#!/usr/bin/env python3
"""
ingest.py: Notion-to-vault normalizer for the ingest-notion skill.

Reads a JSON payload on stdin (root metadata + items, already pulled by
the LLM via the Notion MCP), writes a vault file at
External Inputs/Notion/<slug>/<YYYY-MM-DD>.md.

CLI usage:
  python3 ingest.py --help
  python3 ingest.py <id> [--depth N] [--vault-root /path] < payload.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# _shared is a sibling directory; add it to sys.path so we can import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from connector_utils import (
    excerpt,
    now_iso,
    slugify_unicode,
    to_local_str,
    today_iso,
    yaml_escape,
    yaml_str_array,
)

BODY_EXCERPT_LIMIT = 800
MAX_DEPTH = 5


def normalize_items(items: list, root_kind: str) -> str:
    if not items:
        return "_No pages in scope._\n"

    if root_kind == "database":
        sorted_items = sorted(
            items,
            key=lambda p: p.get("last_edited_time") or "",
            reverse=True,
        )
        lines = ["## Database entries", ""]
    else:
        sorted_items = items
        lines = ["## Page tree", ""]

    for item in sorted_items:
        title = item.get("title") or "(untitled)"
        page_id = item.get("id", "")
        url = item.get("url", "")
        last_edited = to_local_str(item.get("last_edited_time", ""))
        author = item.get("author") or "unknown"
        body_excerpt = excerpt(item.get("body_excerpt", ""), BODY_EXCERPT_LIMIT)
        props = item.get("properties_summary", "")
        depth = int(item.get("depth_in_tree", 0))

        if root_kind == "page":
            indent = "#" * min(3 + depth, 6)
            lines.append(f"{indent} {title}")
        else:
            lines.append(f"### {title}")

        lines.append("")
        if page_id:
            lines.append(f"**Notion ID:** `{page_id}`  ")
        if url:
            lines.append(f"**URL:** {url}  ")
        if last_edited:
            lines.append(f"**Last edited:** {last_edited}  ")
        if author and author != "unknown":
            lines.append(f"**Author:** {author}  ")
        if props and props.strip():
            lines.append(f"**Properties:** {props}  ")
        lines.append("")
        lines.append(body_excerpt)
        lines.append("")

    return "\n".join(lines)


def build_frontmatter(payload: dict, page_count: int, target_date: str, page_ids: list[str]) -> str:
    root_kind = payload.get("root_kind", "page")
    root_id = payload.get("root_id", "")
    ingested_at = payload.get("ingested_at_iso", now_iso())

    lines = [
        "---",
        "type: external-input",
        "source: notion",
    ]
    if root_kind == "database":
        lines.append(f"database_id: {yaml_escape(root_id)}")
    else:
        lines.append(f"page_id: {yaml_escape(root_id)}")
    lines.append(f"root_kind: {root_kind}")
    lines.append(f"page_count: {page_count}")
    lines.append(f"ingested_at: {ingested_at}")
    lines.append("entity_ids:")
    lines.append(f"  notion: {yaml_str_array(page_ids)}")
    lines.append("---")
    lines.append("")

    title = payload.get("root_title") or root_id or "Notion"
    lines.append(f"# Notion {title} on {target_date}")
    lines.append("")
    lines.append(f"_{page_count} page(s) ingested via /ingest-notion._")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_vault_file(payload: dict, body: str, frontmatter: str) -> Path:
    vault_root = Path(payload["vault_root"])
    fallback = (payload.get("root_id", "") or "notion-root")[:8]
    slug = slugify_unicode(payload.get("root_title", ""), fallback or "notion-root")
    out_dir = vault_root / "External Inputs" / "Notion" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    target_date = payload.get("target_date") or today_iso()
    out_path = out_dir / f"{target_date}.md"
    out_path.write_text(frontmatter + body, encoding="utf-8")
    return out_path


def run_from_payload(payload: dict) -> int:
    required = ["vault_root", "root_id"]
    for k in required:
        if k not in payload:
            print(f"ERROR: missing required field: {k}", file=sys.stderr)
            return 2

    root_kind = payload.get("root_kind", "page")
    if root_kind not in ("database", "page"):
        print(f"ERROR: root_kind must be 'database' or 'page', got: {root_kind}", file=sys.stderr)
        return 2

    depth = int(payload.get("depth", 1))
    if depth < 0:
        depth = 0
    if depth > MAX_DEPTH:
        depth = MAX_DEPTH
    payload["depth"] = depth

    target_date = payload.get("target_date") or today_iso()

    items = payload.get("items", []) or []
    page_ids = [item["id"] for item in items if item.get("id")]

    body = normalize_items(items, root_kind)
    frontmatter = build_frontmatter(payload, len(items), target_date, page_ids)

    out_path = write_vault_file(payload, body, frontmatter)

    print(f"Wrote {len(items)} page(s) to {out_path} (depth={depth}, root_kind={root_kind})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ingest-notion",
        description=(
            "Normalize a Notion database query or page subtree into a vault "
            "markdown file. Reads a JSON payload on stdin built by the LLM "
            "via the Notion MCP. CLI flags are accepted but the payload on "
            "stdin is the source of truth."
        ),
    )
    parser.add_argument(
        "root_id",
        nargs="?",
        help=(
            "Notion database id or page id (UUID). Optional if stdin "
            "payload supplies it."
        ),
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help=(
            f"Page-tree walk depth (default 1, max {MAX_DEPTH}). Ignored when "
            "the root is a database."
        ),
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
    parser.add_argument(
        "--root-kind",
        choices=["database", "page"],
        default=None,
        help="Whether the root is a database or a page. Overrides the value in the stdin payload.",
    )
    args = parser.parse_args()

    if sys.stdin.isatty():
        print(
            "ERROR: no JSON payload on stdin. Pipe the Notion MCP results in. "
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

    if args.root_id:
        payload["root_id"] = args.root_id
    if args.depth is not None:
        payload["depth"] = args.depth
    if args.vault_root:
        payload["vault_root"] = args.vault_root
    if args.target_date:
        payload["target_date"] = args.target_date
    if args.root_kind:
        payload["root_kind"] = args.root_kind

    return run_from_payload(payload)


if __name__ == "__main__":
    sys.exit(main())
