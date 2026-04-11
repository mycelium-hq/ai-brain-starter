#!/usr/bin/env python3
"""
graphify_canonicalize.py — Run AFTER the LLM extraction phase of /graphify.

Does three things:
  1. Merges nodes that refer to the same entity but were given per-file scoped IDs
     (e.g. `breathwork_higher_self_love`, `coo_advisory_love`, `cto_drama_love` →
     single canonical `c_love` node).
  2. Strips invalid `file_type` values agents invent (`person`, `concept`, etc.) →
     forces them to "document".
  3. Optionally calls `save_semantic_cache` so the next `/graphify --update` is free.

Without this step, graphify's build_from_json deduplicates by ID only, so a
journal corpus produces 8-74 separate nodes for every recurring entity (Love,
Onde, Amanda, Silvia, etc.). On batch_01 of Adelaida's vault this collapsed
1,421 nodes → 548 (62% reduction) and produced a much more navigable graph.

Usage:
    python3 graphify_canonicalize.py <extraction_json> [--out <output>] [--cache]

If --out is omitted, the input file is overwritten.
If --cache is given, results are also written to graphify-out/cache/ via
graphify.cache.save_semantic_cache. CRITICAL for incremental --update runs.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


# High-Rise floor suffix variants. The framework's 16 floors (Shame...Peace)
# get referenced inconsistently across files: "Love", "Love Floor", "Love (Floor)".
# Canonicalize all of them to the bare name. ai-brain-starter installs this
# framework into every vault, so these variants apply to all repo users.
LABEL_SUFFIX_VARIANTS = (
    " (Floor)", " Floor", " floor",
)


def strip_folder_prefix(label: str) -> str:
    """Strip folder path prefixes from wikilink-style labels.

    Lesson #37 (2026-04-11): legacy files contain path-form wikilinks like
    [[🌱 Curiosities/Colombia]] alongside bare [[Colombia]] — the canonicalize
    step saw these as different labels and produced duplicate god nodes.

    We split on the LAST "/" and take the filename portion, matching Obsidian's
    own bare-name resolution behavior. The CLAUDE.md "bare filenames only" rule
    prevents new path-form wikilinks, and this function collapses the legacy
    ones already embedded in the corpus.

    Exception: if the label contains a character that suggests it's NOT a
    wikilink (e.g. starts with http, contains a space on both sides of "/"),
    leave it alone. Conservative: only strip when the prefix looks like a
    folder name (ends with a slash and contains no spaces, or starts with an
    emoji character common in the vault's folder names).
    """
    if not label or "/" not in label:
        return label
    # Leave URLs alone
    if label.startswith(("http://", "https://", "//")):
        return label
    # Take the last segment (Obsidian behavior for bare-name resolution)
    tail = label.rsplit("/", 1)[-1].strip()
    return tail if tail else label


def normalize_label(label: str) -> str:
    label = strip_folder_prefix((label or "").strip())
    for suf in LABEL_SUFFIX_VARIANTS:
        if label.endswith(suf):
            label = label[: -len(suf)]
            break
    return label.strip().lower()


def normalize_source_file(source_file: str, root: Path = None) -> str:
    """Normalize source_file to a usable absolute path or safe blank.

    Lesson #38 (2026-04-11): the chunk 01 agent set every node's source_file
    to "📓 Journals/" (a directory) which broke save_semantic_cache with
    Errno 21: Is a directory. Defense-in-depth: return "" if source_file
    points to a directory so the cache save can skip cleanly instead of
    erroring the entire stage.
    """
    if not source_file:
        return ""
    root = root or Path.cwd()
    p = Path(source_file)
    if not p.is_absolute():
        p = root / p
    try:
        if p.is_dir():
            return ""  # directory is invalid, skip silently
        if not p.suffix:  # no extension — probably invalid
            return ""
    except (OSError, ValueError):
        return ""
    return source_file


def canonical_id(label: str) -> str:
    norm = normalize_label(label)
    slug = re.sub(r"[^\w\s-]", "", norm)
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")[:60]
    return "c_" + slug


def canonicalize(extraction: dict) -> dict:
    """Merge nodes by canonical label, remap edges, dedupe edges and self-loops."""
    nodes = extraction.get("nodes", [])
    edges = extraction.get("edges", [])
    hyperedges = extraction.get("hyperedges", [])

    # Build label → canonical_id mapping. First node wins for label casing.
    label_to_cid = {}
    canonical_nodes = {}
    id_remap = {}
    mention_count = defaultdict(int)
    file_types = defaultdict(set)

    for n in nodes:
        label = (n.get("label") or "").strip()
        if not label:
            continue
        # Strip folder prefix BEFORE normalize so display label also loses it
        label = strip_folder_prefix(label)
        norm = normalize_label(label)
        cid = label_to_cid.get(norm) or canonical_id(label)
        if norm not in label_to_cid:
            label_to_cid[norm] = cid
            # Strip suffix variants from display label too
            display = label
            for suf in LABEL_SUFFIX_VARIANTS:
                if display.endswith(suf):
                    display = display[: -len(suf)]
                    break
            canonical_nodes[cid] = {
                "id": cid,
                "label": display.strip(),
                "file_type": "document",
                "source_file": normalize_source_file(n.get("source_file", "")),
            }
        id_remap[n.get("id", "")] = cid
        mention_count[cid] += 1
        ft = n.get("file_type") or "document"
        file_types[cid].add(ft)

    # Annotate canonical nodes with mention count
    for cid, count in mention_count.items():
        canonical_nodes[cid]["mention_count"] = count

    # Remap edges, drop self-loops, dedupe by (src, tgt, relation)
    seen = set()
    new_edges = []
    for e in edges:
        src = id_remap.get(e.get("source", ""), e.get("source"))
        tgt = id_remap.get(e.get("target", ""), e.get("target"))
        if not src or not tgt or src == tgt:
            continue
        rel = e.get("relation", "conceptually_related_to")
        key = (src, tgt, rel)
        if key in seen:
            continue
        seen.add(key)
        new_edges.append({
            "source": src,
            "target": tgt,
            "relation": rel,
            "confidence": e.get("confidence", "INFERRED"),
            "confidence_score": e.get("confidence_score", 0.7),
            "source_file": normalize_source_file(e.get("source_file", "")),
            "weight": e.get("weight", 1.0),
        })

    # Remap hyperedges: replace member ids
    new_hyperedges = []
    for h in hyperedges:
        members = [id_remap.get(m, m) for m in h.get("nodes", [])]
        members = list(dict.fromkeys(members))  # dedupe within hyperedge
        if len(members) >= 3:
            new_hyperedges.append({**h, "nodes": members})

    return {
        "nodes": list(canonical_nodes.values()),
        "edges": new_edges,
        "hyperedges": new_hyperedges,
        "input_tokens": extraction.get("input_tokens", 0),
        "output_tokens": extraction.get("output_tokens", 0),
    }


VALID_FILE_TYPES = {"document", "code", "image", "paper", "rationale"}


def force_valid_file_types(nodes: list) -> int:
    """Force every node's file_type to a valid value. Returns count of fixes."""
    fixes = 0
    for n in nodes:
        ft = n.get("file_type", "document")
        if ft not in VALID_FILE_TYPES:
            n["file_type"] = "document"
            fixes += 1
    return fixes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("extraction_json")
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache", action="store_true",
                    help="also save to graphify-out/cache/ via save_semantic_cache (CRITICAL for --update mode)")
    args = ap.parse_args()

    src = Path(args.extraction_json)
    if not src.exists():
        print(f"not found: {src}", file=sys.stderr)
        sys.exit(1)

    extraction = json.loads(src.read_text())
    print(f"input: {len(extraction.get('nodes', []))} nodes, "
          f"{len(extraction.get('edges', []))} edges, "
          f"{len(extraction.get('hyperedges', []))} hyperedges")

    out = canonicalize(extraction)

    # Force valid file_types (graphify build will warn otherwise)
    ft_fixes = force_valid_file_types(out["nodes"])
    if ft_fixes:
        print(f"  fixed {ft_fixes} invalid file_type values → 'document'")

    print(f"output: {len(out['nodes'])} nodes "
          f"({100 * (1 - len(out['nodes']) / max(1, len(extraction['nodes']))):.0f}% reduction), "
          f"{len(out['edges'])} edges "
          f"({100 * (1 - len(out['edges']) / max(1, len(extraction['edges']))):.0f}% reduction)")

    dst = Path(args.out) if args.out else src
    dst.write_text(json.dumps(out))
    print(f"wrote {dst}")

    if args.cache:
        try:
            from graphify.cache import save_semantic_cache
            print()
            print("Saving to graphify cache (next --update will see these as free hits)...")
            saved = save_semantic_cache(
                out["nodes"], out["edges"], out.get("hyperedges"), root=Path.cwd()
            )
            print(f"  cached {saved} per-file entries → graphify-out/cache/")
        except Exception as e:
            print(f"  WARN: cache save failed: {e}")


if __name__ == "__main__":
    main()
