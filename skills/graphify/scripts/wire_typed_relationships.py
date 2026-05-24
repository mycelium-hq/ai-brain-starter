"""Zero-LLM typed-relationship extractor for graphify.

Walks markdown, reads frontmatter + body, applies regex patterns to emit
typed edges to JSONL. Extracts ~80% of explicit edges (frontmatter +
wikilinks) at zero LLM cost. Designed to run BEFORE graphify's Part B
semantic extraction so the LLM only fires on the genuinely-ambiguous
~20% of edges (proper-noun disambiguation, novel entity types,
negation parsing).

Pattern source: github.com/garrytan/gbrain — zero-LLM graph wiring.

Usage:
    python3 wire_typed_relationships.py                  # walk current dir
    python3 wire_typed_relationships.py --root <path>    # walk a different root
    python3 wire_typed_relationships.py --output <path>  # custom output JSONL
    python3 wire_typed_relationships.py --limit 100      # cap files for smoke test

Frontmatter fields it understands:
    type: journal | meeting | decision | person   (drives edge typing)
    company:      <value>   → works_at edge
    floor_level:  <int>     → floor_at edge
    decision_in_force: <id> → governs edge
    creationDate: <date>    → created_on edge
    relationship: investor  → in a CRM/person file, flips mentions→investor_for

Edge confidences:
    high   = derived from frontmatter (structured, unambiguous)
    medium = derived from path-typed wikilink (file kind narrows the relation)
    low    = generic wikilink mention (could be anything)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# Skip system noise + worktrees (worktrees are session-bound copies, not canonical content)
SKIP_DIR_NAMES = {".git", ".obsidian", "__pycache__", ".pytest_cache",
                  "node_modules", "worktrees", ".trash", "graphify-out"}

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Frontmatter field extractors (line-based, not full YAML, to stay zero-dep).
FRONTMATTER_FIELDS = {
    "type": re.compile(r"^type:\s*(.+)$", re.MULTILINE),
    "relationship": re.compile(r"^relationship:\s*(.+)$", re.MULTILINE),
    "company": re.compile(r"^company:\s*(.+)$", re.MULTILINE),
    "floor_level": re.compile(r"^floor_level:\s*(\d+)$", re.MULTILINE),
    "decision_in_force": re.compile(r"^decision_in_force:\s*(.+)$", re.MULTILINE),
    "creationDate": re.compile(r"^creationDate:\s*(.+)$", re.MULTILINE),
}


@dataclass
class TypedEdge:
    src: str          # source entity (wikilink target or file title)
    dst: str          # destination entity (wikilink target or frontmatter value)
    edge_type: str    # attended | investor_for | works_at | journaled_about |
                      # floor_at | governs | created_on | mentions
    src_file: str
    confidence: str   # "high" (frontmatter) | "medium" (path-typed) | "low" (mention only)


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.search(text)
    if not match:
        return {}
    fm_text = match.group(1)
    out = {}
    for key, pattern in FRONTMATTER_FIELDS.items():
        m = pattern.search(fm_text)
        if m:
            out[key] = m.group(1).strip()
    return out


def _classify_file_kind(rel_path: Path, frontmatter: dict[str, str]) -> str:
    """Classify the source-file kind to drive edge typing.

    Frontmatter `type` field wins (most portable across vault layouts).
    Path-substring fallback is case-insensitive and supports common
    Obsidian conventions including emoji-prefixed folders (e.g.
    '📓 Journals', '👤 CRM', '📋 Strategy', 'Decisions/').
    """
    type_field = frontmatter.get("type", "").lower()
    if type_field in {"journal", "daily-journal", "weekly", "monthly"}:
        return "journal"
    if type_field in {"meeting", "meeting-note"}:
        return "meeting"
    if type_field == "decision":
        return "decision"
    if type_field == "person":
        return "crm"

    parts_lower = [p.lower() for p in rel_path.parts]
    if any("journal" in p for p in parts_lower):
        return "journal"
    if any("crm" in p for p in parts_lower) or any("people" in p for p in parts_lower):
        return "crm"
    if any("meeting" in p for p in parts_lower) or any("strategy" in p for p in parts_lower):
        return "meeting"
    if any("decision" in p for p in parts_lower):
        return "decision"
    return "other"


def _extract_edges(file_path: Path, root: Path) -> list[TypedEdge]:
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    frontmatter = _parse_frontmatter(text)
    rel_path = file_path.relative_to(root) if file_path.is_relative_to(root) else file_path
    src = file_path.stem  # filename IS the title in Obsidian
    file_kind = _classify_file_kind(rel_path, frontmatter)
    edges: list[TypedEdge] = []

    # Frontmatter-derived edges (highest confidence)
    if "company" in frontmatter:
        edges.append(TypedEdge(
            src=src, dst=frontmatter["company"], edge_type="works_at",
            src_file=str(rel_path), confidence="high",
        ))
    if "floor_level" in frontmatter:
        edges.append(TypedEdge(
            src=src, dst=f"floor_{frontmatter['floor_level']}", edge_type="floor_at",
            src_file=str(rel_path), confidence="high",
        ))
    if "decision_in_force" in frontmatter:
        edges.append(TypedEdge(
            src=src, dst=frontmatter["decision_in_force"], edge_type="governs",
            src_file=str(rel_path), confidence="high",
        ))
    if "creationDate" in frontmatter:
        edges.append(TypedEdge(
            src=src, dst=frontmatter["creationDate"], edge_type="created_on",
            src_file=str(rel_path), confidence="high",
        ))

    # Wikilink-derived edges (typed by file kind)
    seen_wikilinks: set[str] = set()
    for match in WIKILINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or target in seen_wikilinks:
            continue
        seen_wikilinks.add(target)

        if file_kind == "meeting":
            edge_type, confidence = "attended", "medium"
        elif file_kind == "journal":
            edge_type, confidence = "journaled_about", "medium"
        elif file_kind == "crm" and frontmatter.get("relationship") == "investor":
            edge_type, confidence = "investor_for", "medium"
        else:
            edge_type, confidence = "mentions", "low"

        edges.append(TypedEdge(
            src=src, dst=target, edge_type=edge_type,
            src_file=str(rel_path), confidence=confidence,
        ))

    return edges


def _walk_markdown(root: Path, limit: int | None) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for fname in filenames:
            if fname.endswith(".md"):
                files.append(Path(dirpath) / fname)
                if limit and len(files) >= limit:
                    return files
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wire_typed_relationships", description=__doc__)
    parser.add_argument("--root", default=".",
                        help="root directory to walk (default: current directory)")
    parser.add_argument("--output", default="graphify-out/.graphify_typed_edges.jsonl",
                        help="output JSONL path (default: graphify-out/.graphify_typed_edges.jsonl)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of files walked (for smoke testing)")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: root not a directory: {root}", file=sys.stderr)
        return 2

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc)
    files = _walk_markdown(root, args.limit)
    edge_count = 0
    by_type: dict[str, int] = {}

    with output.open("w", encoding="utf-8") as f:
        for file_path in files:
            for edge in _extract_edges(file_path, root):
                f.write(json.dumps(asdict(edge)) + "\n")
                edge_count += 1
                by_type[edge.edge_type] = by_type.get(edge.edge_type, 0) + 1

    elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    print(f"wired {edge_count} typed edges from {len(files)} files in {elapsed_ms:.0f}ms")
    for edge_type, count in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {edge_type}: {count}")
    print(f"output: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
