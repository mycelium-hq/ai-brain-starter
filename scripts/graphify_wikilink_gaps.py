#!/usr/bin/env python3
"""
graphify_wikilink_gaps.py — find graph entities worth wikilink-ing.

Reads graph.json, counts each node's degree (connection count), scans vault
.md files for existing [[wikilinks]], then reports nodes that are highly
connected but never linked. Run after any graphify session to find quick wins.

Usage:
    python3 graphify_wikilink_gaps.py [options]

Options:
    --vault-root PATH   Vault root (default: current directory)
    --graph PATH        Override graph.json path
    --top N             Max candidates to report (default: 30)
    --min-degree N      Minimum connections to qualify (default: 3)
    --output PATH       Write markdown report here (default: <graph_dir>/WIKILINK_GAPS.md)
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

SKIP_PARTS = {"⚙️ Meta", "Archive", "🗄 Archive", "_review_alternate_drafts"}
SKIP_TYPES = {"document"}  # file nodes already map to real files; skip them
WIKILINK_RE = re.compile(r'\[\[([^\]|#\n]+?)(?:\|[^\]\n]+?)?\]\]')


def find_graph(vault: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    # Standard vault layout: graphify-out/ at vault root or inside ⚙️ Meta/
    for candidate in [
        vault / "graphify-out/graph.json",
        vault / "⚙️ Meta/graphify-out/graph.json",
    ]:
        if candidate.exists():
            return candidate
    # Multi-corpus layout: graph inside a corpus subfolder
    for child in sorted(vault.iterdir()):
        if child.is_dir() and child.name not in SKIP_PARTS:
            candidate = child / "⚙️ Meta/graphify-out/graph.json"
            if candidate.exists():
                return candidate
    sys.exit("ERROR: graph.json not found. Use --graph <path> to specify location.")


def scan_wikilinks(vault: Path) -> dict[str, int]:
    """Return lowercased wikilink target -> occurrence count across all vault .md files."""
    counts: dict[str, int] = defaultdict(int)
    for md in vault.rglob("*.md"):
        if any(part in SKIP_PARTS for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
            for m in WIKILINK_RE.finditer(text):
                counts[m.group(1).strip().lower()] += 1
        except OSError:
            continue
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--vault-root", default=".", metavar="PATH",
                        help="Vault root directory (default: current directory)")
    parser.add_argument("--graph", default=None, metavar="PATH",
                        help="Explicit path to graph.json")
    parser.add_argument("--top", type=int, default=30, metavar="N",
                        help="Max candidates to report (default: 30)")
    parser.add_argument("--min-degree", type=int, default=3, metavar="N",
                        help="Minimum connections to qualify (default: 3)")
    parser.add_argument("--output", default=None, metavar="PATH",
                        help="Output path for markdown report")
    args = parser.parse_args()

    vault = Path(args.vault_root).resolve()
    graph_path = find_graph(vault, args.graph)

    print(f"Graph:  {graph_path}")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    edges = graph.get("links", graph.get("edges", []))  # NetworkX uses "links"

    # Compute undirected degree per node id
    degree: dict[str, int] = defaultdict(int)
    for e in edges:
        degree[e.get("source", "")] += 1
        degree[e.get("target", "")] += 1

    # Collect nodes that meet min-degree threshold (skip document/file nodes)
    candidates: list[dict] = []
    for n in nodes:
        ntype = n.get("type", "")
        if ntype in SKIP_TYPES:
            continue
        label = n.get("label", "").strip()
        if not label:
            continue
        deg = degree.get(n.get("id", ""), 0)
        if deg >= args.min_degree:
            candidates.append({"label": label, "type": ntype, "degree": deg})

    print(f"Vault:  {vault}")
    print(f"Nodes qualifying (degree >= {args.min_degree}): {len(candidates)}")
    print("Scanning vault for existing wikilinks...")

    wikilinks = scan_wikilinks(vault)
    print(f"Unique wikilink targets found: {len(wikilinks)}")

    # Gaps: qualifying nodes with no existing wikilinks
    all_gaps = [c for c in candidates if wikilinks.get(c["label"].lower(), 0) == 0]
    all_gaps.sort(key=lambda x: -x["degree"])
    total_gaps = len(all_gaps)
    display_gaps = all_gaps[: args.top]

    # Console output
    print(f"\nWikilink Gap Report — top {len(display_gaps)} of {total_gaps} gaps\n")
    print(f"{'#':<4} {'Entity':<35} {'Type':<15} {'Connections'}")
    print("-" * 68)
    for i, g in enumerate(display_gaps, 1):
        print(f"{i:<4} {g['label']:<35} {g['type']:<15} {g['degree']}")

    # Write markdown report
    out_path = (
        Path(args.output).resolve()
        if args.output
        else graph_path.parent / "WIKILINK_GAPS.md"
    )
    lines = [
        "---",
        "type: report",
        f"generated: {date.today()}",
        "---",
        "",
        "# Wikilink Gap Report",
        "",
        f"High-connection graph entities with no existing `[[wikilinks]]`.",
        f"Showing top {len(display_gaps)} of {total_gaps} gaps (min degree: {args.min_degree}).",
        "",
        "| # | Entity | Type | Connections |",
        "|---|--------|------|-------------|",
    ]
    for i, g in enumerate(display_gaps, 1):
        lines.append(f"| {i} | {g['label']} | {g['type']} | {g['degree']} |")
    lines += [
        "",
        "*Run `graphify_wikilink_gaps.py` to refresh after adding wikilinks.*",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport saved: {out_path}")


if __name__ == "__main__":
    main()
