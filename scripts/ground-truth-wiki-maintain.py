#!/usr/bin/env python3
"""ground-truth-wiki-maintain.py: regenerate a topic-scoped Wiki page from typed memory entries.

Scans typed-memory entries in:
    Meta/Workflows/
    Meta/Decisions/
    Meta/Exceptions/
    Meta/Facts/

For a given topic, aggregates every entry that matches via:
    - frontmatter `topic:` field equal to <topic>
    - frontmatter `tags:` containing <topic>
    - body containing a wikilink to <topic>

Writes a single canonical Wiki page at Meta/Wiki/<topic>.md with:
    - frontmatter `auto_generated: true` and `last_built: <iso>`
    - sections per type (Workflows, Decisions, Exceptions, Facts)
    - a list of source files with their key fields

Idempotent: re-running on the same topic overwrites the same Wiki page.
Stdlib + PyYAML only. No external API calls.

Usage:
    python3 ground-truth-wiki-maintain.py \
        --vault-root <vault> \
        --topic-folder <topic> \
        [--out <override-path>] \
        [--dry-run]

Examples:
    python3 ground-truth-wiki-maintain.py --vault-root . --topic-folder deploy
    python3 ground-truth-wiki-maintain.py --vault-root . --topic-folder testing --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("PyYAML required. Install: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


TYPED_FOLDERS = {
    "workflow": "Workflows",
    "decision": "Decisions",
    "exception": "Exceptions",
    "fact": "Facts",
}


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, parts[2]


def topic_matches(meta: dict[str, Any], body: str, topic: str) -> bool:
    topic_lower = topic.lower()

    fm_topic = meta.get("topic")
    if isinstance(fm_topic, str) and fm_topic.lower() == topic_lower:
        return True

    tags = meta.get("tags")
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, str) and t.lower() == topic_lower:
                return True
    elif isinstance(tags, str) and tags.lower() == topic_lower:
        return True

    wikilink_pattern = re.compile(rf"\[\[\s*{re.escape(topic)}\s*(?:\||\]\])", re.I)
    if wikilink_pattern.search(body):
        return True

    return False


def gather_entries(vault_root: Path, topic: str) -> dict[str, list[tuple[Path, dict[str, Any], str]]]:
    out: dict[str, list[tuple[Path, dict[str, Any], str]]] = {k: [] for k in TYPED_FOLDERS.keys()}
    meta_root = vault_root / "Meta"

    for type_name, folder_name in TYPED_FOLDERS.items():
        folder = meta_root / folder_name
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            meta, body = split_frontmatter(text)
            if meta.get("type") != type_name:
                continue
            if not topic_matches(meta, body, topic):
                continue
            out[type_name].append((path, meta, body))
    return out


def render_workflow_block(entries: list[tuple[Path, dict[str, Any], str]]) -> str:
    if not entries:
        return ""
    lines = ["## Workflows", ""]
    for path, meta, _body in entries:
        name = meta.get("name", path.stem)
        sha8 = meta.get("sha8", path.stem)
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"Source: `{path.relative_to(path.parents[2])}` (sha8 `{sha8}`)")
        lines.append("")
        steps = meta.get("steps") or []
        if steps:
            lines.append("Steps:")
            for s in steps:
                num = s.get("step_number", "?")
                desc = s.get("description", "(missing)")
                owner = s.get("owner")
                if owner:
                    lines.append(f"{num}. {desc} ({owner})")
                else:
                    lines.append(f"{num}. {desc}")
            lines.append("")
    return "\n".join(lines)


def render_decision_block(entries: list[tuple[Path, dict[str, Any], str]]) -> str:
    if not entries:
        return ""
    lines = ["## Decisions", ""]
    for path, meta, body in entries:
        date = meta.get("decision_date", meta.get("creationDate", ""))[:10]
        sha8 = meta.get("sha8", path.stem)
        stakes = meta.get("stakes", "?")
        body_first = next((line.strip() for line in body.splitlines() if line.strip() and not line.startswith("#")), "")
        if len(body_first) > 200:
            body_first = body_first[:197] + "..."
        lines.append(f"- **{date}** (stakes: {stakes}, sha8 `{sha8}`): {body_first}")
    lines.append("")
    return "\n".join(lines)


def render_exception_block(entries: list[tuple[Path, dict[str, Any], str]]) -> str:
    if not entries:
        return ""
    lines = ["## Exceptions", ""]
    for path, meta, _body in entries:
        summary = meta.get("exception_summary", "(no summary)")
        rule = meta.get("rule_id", "(unspecified)")
        sha8 = meta.get("sha8", path.stem)
        lines.append(f"- **Rule {rule}** (sha8 `{sha8}`): {summary}")
    lines.append("")
    return "\n".join(lines)


def render_fact_block(entries: list[tuple[Path, dict[str, Any], str]]) -> str:
    if not entries:
        return ""
    lines = ["## Facts", ""]
    for path, meta, _body in entries:
        claim = meta.get("claim", "(no claim)")
        domain = meta.get("domain") or ""
        sha8 = meta.get("sha8", path.stem)
        prefix = f"[{domain}] " if domain else ""
        lines.append(f"- {prefix}{claim} (sha8 `{sha8}`)")
    lines.append("")
    return "\n".join(lines)


def render_wiki_page(topic: str, entries: dict[str, list[tuple[Path, dict[str, Any], str]]]) -> str:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    total = sum(len(v) for v in entries.values())

    fm: dict[str, Any] = {
        "type": "wiki",
        "topic": topic,
        "auto_generated": True,
        "last_built": now,
        "source_count": total,
    }
    fm_text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip() + "\n---\n\n"

    body_parts: list[str] = []
    title = topic.replace("-", " ").replace("_", " ").title()
    body_parts.append(f"# {title}")
    body_parts.append("")
    body_parts.append(f"Auto-generated ground-truth page for topic `{topic}`. Aggregates {total} typed memory entries.")
    body_parts.append("")
    body_parts.append("Do not hand-edit. Re-run `scripts/ground-truth-wiki-maintain.py` to refresh.")
    body_parts.append("")

    workflow_block = render_workflow_block(entries.get("workflow", []))
    decision_block = render_decision_block(entries.get("decision", []))
    exception_block = render_exception_block(entries.get("exception", []))
    fact_block = render_fact_block(entries.get("fact", []))

    if workflow_block:
        body_parts.append(workflow_block)
    if decision_block:
        body_parts.append(decision_block)
    if exception_block:
        body_parts.append(exception_block)
    if fact_block:
        body_parts.append(fact_block)

    if total == 0:
        body_parts.append("No matching typed memory entries found for this topic.")
        body_parts.append("")
        body_parts.append("Possible reasons:")
        body_parts.append("- Topic name does not match any frontmatter `topic:` field, tag, or wikilink.")
        body_parts.append("- Typed memory folders (`Meta/Workflows/`, `Meta/Decisions/`, `Meta/Exceptions/`, `Meta/Facts/`) are empty.")
        body_parts.append("")

    return fm_text + "\n".join(body_parts).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", type=Path, required=True, help="Vault root path")
    parser.add_argument("--topic-folder", required=True, help="Topic name (matches frontmatter topic, tag, or wikilink)")
    parser.add_argument("--out", type=Path, default=None, help="Override output path (default: Meta/Wiki/<topic>.md)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.vault_root.exists():
        print(f"vault-root not found: {args.vault_root}", file=sys.stderr)
        return 2

    topic = args.topic_folder
    entries = gather_entries(args.vault_root, topic)
    rendered = render_wiki_page(topic, entries)

    if args.out:
        out_path = args.out
    else:
        out_path = args.vault_root / "Meta" / "Wiki" / f"{topic}.md"

    if args.dry_run:
        print(f"[dry-run] would write {out_path}")
        print(rendered[:600])
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")

    total = sum(len(v) for v in entries.values())
    print(f"[wrote] {out_path} ({total} entries aggregated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
