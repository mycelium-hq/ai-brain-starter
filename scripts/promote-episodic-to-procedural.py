#!/usr/bin/env python3
"""
promote-episodic-to-procedural.py — Background consolidation for closed-loop
learning.

Walks <vault-root>/Meta/Learnings/ (the episodic capture sink populated by the
post-tool-use-learnings.py PostToolUse hook) and looks for recurring patterns.
When the same source_tool fails the same way 3 or more times, the script
drafts a procedural-memory candidate at:

    <vault-root>/Meta/Promotion-Candidates/<sha8>.md

The candidate's frontmatter is shaped to match either the workflow schema
(when the pattern is a repeatable success path) or the exception schema (when
the pattern is a repeatable failure). The default classification is
exception, because the hook only writes Learnings on failures or explicit
annotations, so the recurring case is overwhelmingly a failure pattern.

The candidate is `status: candidate`. A human reviews the file, edits it
into shape, moves it to the appropriate folder (`⚙️ Meta/Workflows/` or
`⚙️ Meta/Exceptions/`), and only then does the procedural memory go live.
The script never promotes directly: human review is the gate.

Heuristic for grouping (deliberately simple; we want false-positive bias
toward surfacing patterns):
  1. Group Learning files by source_tool.
  2. Within each group, compute a 5-gram set over the error_excerpt.
  3. Two Learnings cluster together if their 5-gram sets share at least
     30 percent of their union. Single-link agglomerative.
  4. A cluster of size >= --min-occurrences becomes a candidate.

The 5-gram approach is on whitespace-tokenized words after lowercasing and
stripping non-word punctuation. It catches "permission denied: /tmp/x" and
"permission denied: /tmp/y" as the same pattern while keeping unrelated
errors apart.

CLI:
    python3 promote-episodic-to-procedural.py \\
        --vault-root /path/to/vault \\
        --min-occurrences 3 \\
        --dry-run

Stdlib + PyYAML only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


WORD_RE = re.compile(r"[a-z0-9]+")
NGRAM_N = 5
JACCARD_THRESHOLD = 0.30


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter_dict, body). Returns ({}, text) on failure."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw_fm = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    if yaml is None:
        return parse_simple_yaml(raw_fm), body
    try:
        fm = yaml.safe_load(raw_fm) or {}
        if not isinstance(fm, dict):
            return {}, text
        return fm, body
    except yaml.YAMLError:
        return parse_simple_yaml(raw_fm), body


def parse_simple_yaml(raw: str) -> dict:
    """Tiny stdlib fallback that handles the flat key:value lines this script writes."""
    fm: dict = {}
    for line in raw.splitlines():
        if ":" not in line or line.startswith(" ") or line.startswith("-"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        fm[key] = value
    return fm


def render_frontmatter(frontmatter: dict) -> str:
    if yaml is not None:
        return yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    lines = []
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    first = True
                    for k, v in item.items():
                        prefix = "  - " if first else "    "
                        lines.append(f"{prefix}{k}: {json.dumps(v, ensure_ascii=False)}")
                        first = False
                else:
                    lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for k, v in value.items():
                lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def tokenize(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def cluster_learnings(items: list[dict], threshold: float) -> list[list[dict]]:
    """Single-link agglomerative clustering on the 5-gram Jaccard similarity."""
    clusters: list[list[dict]] = []
    for item in items:
        placed = False
        for cluster in clusters:
            for existing in cluster:
                if jaccard(item["ngrams"], existing["ngrams"]) >= threshold:
                    cluster.append(item)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            clusters.append([item])
    return clusters


def stable_sha8(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]


def common_excerpt(cluster: list[dict]) -> str:
    """Pick the shortest non-empty excerpt as the representative."""
    excerpts = [c["error_excerpt"] for c in cluster if c["error_excerpt"]]
    if not excerpts:
        return ""
    excerpts.sort(key=len)
    return excerpts[0][:300]


def build_candidate(cluster: list[dict], vault_root: Path) -> tuple[str, dict, str]:
    """Return (filename_stem, frontmatter_dict, body_string)."""
    source_tool = cluster[0]["source_tool"]
    excerpt = common_excerpt(cluster)
    seed = f"{source_tool}|{excerpt}|{len(cluster)}"
    sha8 = stable_sha8(seed)

    # Default to exception (recurring failure pattern). Could be workflow
    # later if the human reviewer reframes it as a positive recipe.
    summary = (
        f"{source_tool} repeatedly produces the same failure "
        f"(observed {len(cluster)} times)."
    )

    sources = []
    for c in cluster:
        rel = str(c["path"].relative_to(vault_root)) if vault_root in c["path"].parents else str(c["path"])
        sources.append(rel)

    frontmatter = {
        "type": "exception",
        "memory_class": "procedural",
        "status": "candidate",
        "exception_summary": summary,
        "frequency_observed": len(cluster),
        "source_episodic_files": sources,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": [
            {
                "source_type": "claude-session",
                "source_id": "promote-episodic-to-procedural",
                "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ],
    }

    body_parts = [
        "## Pattern",
        "",
        f"`{source_tool}` failed {len(cluster)} times with overlapping error signatures.",
        "",
        "## Representative excerpt",
        "",
        "```",
        excerpt or "(no excerpt available)",
        "```",
        "",
        "## Source episodic captures",
        "",
    ]
    for src in sources:
        body_parts.append(f"- `{src}`")
    body_parts.append("")
    body_parts.append("## Reviewer notes")
    body_parts.append("")
    body_parts.append("Status: candidate. Awaiting human review.")
    body_parts.append("")
    body_parts.append(
        "If this pattern reflects a real reusable failure mode, edit this file into the exception schema "
        "(see `templates/schemas/exception.json`) and move it to `Meta/Exceptions/`. "
        "If it reflects a positive repeatable recipe, reshape it to the workflow schema "
        "(see `templates/schemas/workflow.json`) and move it to `Meta/Workflows/` instead. "
        "Either way, the source episodic captures stay in `Meta/Learnings/` as evidence."
    )
    body_parts.append("")

    return sha8, frontmatter, "\n".join(body_parts)


def load_learnings(learnings_dir: Path) -> list[dict]:
    items: list[dict] = []
    if not learnings_dir.is_dir():
        return items
    for path in sorted(learnings_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = parse_frontmatter(text)
        if (fm.get("type") or "").strip() != "learning":
            continue
        excerpt = (fm.get("error_excerpt") or "").strip()
        if not excerpt:
            # Fall back to the body's "Error excerpt" code block, if any.
            m = re.search(r"## Error excerpt\s*```(.*?)```", body, re.DOTALL)
            if m:
                excerpt = m.group(1).strip()
        source_tool = (fm.get("source_tool") or "").strip() or "unknown"
        tokens = tokenize(excerpt)
        items.append(
            {
                "path": path,
                "source_tool": source_tool,
                "error_excerpt": excerpt,
                "ngrams": ngrams(tokens, NGRAM_N),
            }
        )
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--vault-root",
        type=Path,
        required=True,
        help="Path to the vault root (contains a Meta/ folder).",
    )
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=3,
        help="Minimum cluster size to draft a promotion candidate (default 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be drafted without writing any files.",
    )
    args = parser.parse_args(argv)

    vault_root = args.vault_root.expanduser().resolve()
    learnings_dir = vault_root / "Meta" / "Learnings"
    candidates_dir = vault_root / "Meta" / "Promotion-Candidates"

    items = load_learnings(learnings_dir)
    if not items:
        print(f"No learning files found at {learnings_dir}")
        return 0

    by_tool: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_tool[item["source_tool"]].append(item)

    drafted = 0
    skipped = 0
    for tool, group in by_tool.items():
        clusters = cluster_learnings(group, JACCARD_THRESHOLD)
        for cluster in clusters:
            if len(cluster) < args.min_occurrences:
                continue
            sha8, fm, body = build_candidate(cluster, vault_root)
            target = candidates_dir / f"{sha8}.md"
            content = "---\n" + render_frontmatter(fm).rstrip() + "\n---\n\n" + body
            if args.dry_run:
                print(f"[dry-run] would write {target} ({len(cluster)} captures, tool={tool})")
                drafted += 1
                continue
            if target.exists():
                skipped += 1
                continue
            try:
                candidates_dir.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                drafted += 1
            except OSError as e:
                print(f"Failed to write {target}: {e}", file=sys.stderr)

    print(f"Drafted {drafted} candidate(s). Skipped {skipped} pre-existing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
