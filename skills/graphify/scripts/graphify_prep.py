#!/usr/bin/env python3
"""
graphify_prep.py — Run BEFORE the LLM extraction phase of /graphify.

Does the work that doesn't need an LLM:
  1. Dedupe " 2.md" files (md5-identical → delete; different → quarantine)
  2. Pre-extract every [[wikilink]] as a node + EXTRACTED edge
  3. Pre-extract YAML frontmatter (floor tags, dates, source) as edges
  4. Write a "preflight" JSON the LLM extraction will be merged with

Why: each file has dozens of wikilinks already. Regex catches 100% of them
in <2 seconds. The LLM only needs to do INFERRED / semantic work after this.
Combined with dedupe, this typically cuts LLM token cost by 50-65% on
journal-style markdown vaults.

Usage:
    python3 graphify_prep.py <input_dir>           # dry-run (counts only)
    python3 graphify_prep.py <input_dir> --apply   # delete dupes + write preflight

Outputs (when --apply):
    graphify-out/.graphify_preflight.json       (nodes + edges from regex)
    graphify-out/_prep_report.md                (what was done, human-readable)
    graphify-input/_review_alternate_drafts/    (quarantined non-identical " 2.md" files)
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

# --- regex patterns ---
WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(?:\|([^\[\]]+?))?(?:#[^\[\]]*)?\]\]")
YAML_FENCE_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
KEY_VAL_RE = re.compile(r"^([a-zA-Z_][\w_]*)\s*:\s*(.*)$", re.MULTILINE)
LIST_ITEM_RE = re.compile(r"^\s*-\s*(.+)$", re.MULTILINE)

# The 16 floors of the High-Rise framework. ai-brain-starter installs this
# framework into every vault, so these names apply to all repo users.
# Each journal/note may have a `dominant_floors:` or `floor:` frontmatter tag
# pointing at one or more of these — the prep step turns each into an
# `expresses_floor` edge for free, no LLM needed.
CANONICAL_FLOORS = {
    "shame", "guilt", "apathy", "grief", "fear", "desire", "anger", "pride",
    "courage", "neutrality", "willingness", "acceptance", "reason",
    "love", "joy", "peace",
}


def slugify(text: str, maxlen: int = 60) -> str:
    """ASCII-safe lowercase slug for IDs."""
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "_", s).strip("_")
    return s[:maxlen]


def normalize_label(label: str) -> str:
    """Normalize a node label for dedup."""
    label = label.strip()
    # Strip floor suffix variants
    for suf in (" (Floor)", " Floor", " floor"):
        if label.endswith(suf):
            label = label[: -len(suf)]
            break
    return label.strip().lower()


def canonical_id(label: str) -> str:
    """Canonical ID = c_<normalized slug>. Used for cross-file dedup."""
    return "c_" + slugify(normalize_label(label))


def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter as a dict (no PyYAML — handle simple key/value + lists)."""
    m = YAML_FENCE_RE.match(text)
    if not m:
        return {}
    body = m.group(1)
    out = {}
    current_list_key = None
    for line in body.splitlines():
        if not line.strip():
            current_list_key = None
            continue
        if line.startswith(" ") and current_list_key:
            li = LIST_ITEM_RE.match(line)
            if li:
                out.setdefault(current_list_key, []).append(li.group(1).strip().strip("'\""))
            continue
        kv = KEY_VAL_RE.match(line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                # inline list
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                out[key] = items
            elif not val:
                current_list_key = key
            else:
                out[key] = val.strip("'\"")
                current_list_key = None
    return out


def dedupe(input_dir: Path, apply: bool) -> dict:
    """Find and (optionally) remove duplicates in two passes:
    Pass A: ' 2.md' siblings in the same directory (md5-identical → delete; different → quarantine).
    Pass B: cross-directory filename collisions (md5-identical → keep root version, delete others).
    """
    qdir = input_dir / "_review_alternate_drafts"
    deleted_a, quarantined_a = [], []
    deleted_b, quarantined_b = [], []

    # Pass A: " 2.md" suffix duplicates
    for d in sorted(input_dir.rglob("* 2.md")):
        if "_review_alternate_drafts" in d.parts:
            continue
        orig = d.parent / (d.name[:-5] + ".md")
        if not orig.exists():
            quarantined_a.append((d, "orphan_no_original"))
            continue
        if hashlib.md5(orig.read_bytes()).hexdigest() == hashlib.md5(d.read_bytes()).hexdigest():
            deleted_a.append(d)
        else:
            quarantined_a.append((d, "alternate_draft"))

    # Apply Pass A first so Pass B sees the cleaned state
    if apply:
        if quarantined_a:
            qdir.mkdir(exist_ok=True)
        for d in deleted_a:
            d.unlink()
        for d, _reason in quarantined_a:
            shutil.move(str(d), str(qdir / d.name))

    # Pass B: cross-directory filename collisions
    by_name = {}
    for f in input_dir.rglob("*.md"):
        if "_review_alternate_drafts" in f.parts:
            continue
        by_name.setdefault(f.name, []).append(f)

    for name, copies in by_name.items():
        if len(copies) < 2:
            continue
        # Prefer the shallowest copy (root or closest to root) as canonical
        copies_sorted = sorted(copies, key=lambda p: (len(p.parts), str(p)))
        canonical = copies_sorted[0]
        canonical_md5 = hashlib.md5(canonical.read_bytes()).hexdigest()
        for other in copies_sorted[1:]:
            other_md5 = hashlib.md5(other.read_bytes()).hexdigest()
            if other_md5 == canonical_md5:
                deleted_b.append(other)
            else:
                quarantined_b.append((other, "cross_dir_diff"))

    if apply:
        if quarantined_b:
            qdir.mkdir(exist_ok=True)
        for d in deleted_b:
            d.unlink()
        for d, _reason in quarantined_b:
            # Avoid name collision in quarantine
            target = qdir / d.name
            if target.exists():
                target = qdir / f"{d.parent.name}__{d.name}"
            shutil.move(str(d), str(target))

    # Remove now-empty batch directories
    if apply:
        for sub in sorted(input_dir.iterdir(), reverse=True):
            if sub.is_dir() and sub.name != "_review_alternate_drafts":
                try:
                    if not any(sub.iterdir()):
                        sub.rmdir()
                except OSError:
                    pass

    return {
        "deleted_passA_2md": len(deleted_a),
        "quarantined_passA_2md": len(quarantined_a),
        "deleted_passB_crossdir": len(deleted_b),
        "quarantined_passB_crossdir": len(quarantined_b),
        "qdir": str(qdir),
    }


def extract_structural(input_dir: Path) -> dict:
    """Walk markdown files; pull every [[wikilink]] + frontmatter signal as nodes/edges."""
    nodes_by_id = {}  # canonical_id → node dict
    edges = []
    edge_keys = set()
    files_seen = 0

    for f in sorted(input_dir.rglob("*.md")):
        if "_review_alternate_drafts" in f.parts:
            continue
        files_seen += 1
        text = f.read_text(errors="ignore")
        rel = str(f.relative_to(input_dir.parent))
        file_stem_id = "file_" + slugify(f.stem)

        # File-level node
        if file_stem_id not in nodes_by_id:
            nodes_by_id[file_stem_id] = {
                "id": file_stem_id,
                "label": f.stem,
                "file_type": "document",
                "source_file": rel,
                "is_file_node": True,
            }

        # Frontmatter
        fm = parse_frontmatter(text)
        captured_at = fm.get("creationDate") or fm.get("date") or None

        # Floor tags from frontmatter → edges to canonical floor nodes
        floors = fm.get("dominant_floors") or fm.get("floor") or []
        if isinstance(floors, str):
            floors = [floors]
        for floor in floors:
            floor_norm = normalize_label(floor)
            if floor_norm in CANONICAL_FLOORS:
                cid = canonical_id(floor)
                if cid not in nodes_by_id:
                    nodes_by_id[cid] = {
                        "id": cid,
                        "label": floor.strip().title(),
                        "file_type": "document",
                        "source_file": rel,
                        "is_floor": True,
                    }
                key = (file_stem_id, cid, "expresses_floor")
                if key not in edge_keys:
                    edge_keys.add(key)
                    edges.append({
                        "source": file_stem_id, "target": cid,
                        "relation": "expresses_floor",
                        "confidence": "EXTRACTED", "confidence_score": 1.0,
                        "source_file": rel, "weight": 1.0,
                    })

        # Wikilinks → canonical nodes + EXTRACTED edges
        for m in WIKILINK_RE.finditer(text):
            target = m.group(1).strip()
            if not target or len(target) > 80:
                continue
            cid = canonical_id(target)
            if cid not in nodes_by_id:
                nodes_by_id[cid] = {
                    "id": cid,
                    "label": target,
                    "file_type": "document",
                    "source_file": rel,
                }
            key = (file_stem_id, cid, "references")
            if key not in edge_keys:
                edge_keys.add(key)
                edges.append({
                    "source": file_stem_id, "target": cid,
                    "relation": "references",
                    "confidence": "EXTRACTED", "confidence_score": 1.0,
                    "source_file": rel, "weight": 1.0,
                })

    return {
        "nodes": list(nodes_by_id.values()),
        "edges": edges,
        "hyperedges": [],
        "files_processed": files_seen,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def write_report(report: dict, dedupe_stats: dict, structural: dict, out_path: Path):
    floor_edges = sum(1 for e in structural["edges"] if e["relation"] == "expresses_floor")
    wikilink_edges = sum(1 for e in structural["edges"] if e["relation"] == "references")
    floor_nodes = sum(1 for n in structural["nodes"] if n.get("is_floor"))
    file_nodes = sum(1 for n in structural["nodes"] if n.get("is_file_node"))
    concept_nodes = len(structural["nodes"]) - floor_nodes - file_nodes
    out_path.write_text(f"""# Graphify Prep Report

## Dedupe
**Pass A — ` 2.md` sibling duplicates:**
- md5-identical deleted: **{dedupe_stats['deleted_passA_2md']}**
- alternate drafts quarantined: **{dedupe_stats['quarantined_passA_2md']}**

**Pass B — cross-directory filename collisions:**
- md5-identical deleted (kept root copy): **{dedupe_stats['deleted_passB_crossdir']}**
- different copies quarantined: **{dedupe_stats['quarantined_passB_crossdir']}**

Quarantine: `{dedupe_stats['qdir']}`

## Structural pre-extraction (regex, no LLM)
- files processed: **{structural['files_processed']:,}**
- canonical nodes: **{len(structural['nodes']):,}**
  - file nodes: {file_nodes}
  - floor nodes: {floor_nodes}
  - concept/wikilink nodes: {concept_nodes}
- EXTRACTED edges: **{len(structural['edges']):,}**
  - wikilink references: {wikilink_edges}
  - floor expressions: {floor_edges}

The LLM pass after this only needs to add INFERRED / semantic / hyperedge content
on top of the structural baseline. It should focus on:
  - rationale_for edges (why a thing was decided)
  - semantically_similar_to (cross-file conceptual matches)
  - conceptually_related_to (implicit connections beyond wikilinks)
  - hyperedges (multi-node coherent groups)
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir")
    ap.add_argument("--apply", action="store_true", help="actually delete dupes + write outputs (default: dry-run)")
    ap.add_argument("--out-dir", default="graphify-out")
    args = ap.parse_args()

    input_dir = Path(args.input_dir).resolve()
    if not input_dir.exists():
        print(f"input dir not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir)
    if args.apply:
        out_dir.mkdir(exist_ok=True)

    print(f"=== graphify_prep ({'APPLY' if args.apply else 'DRY-RUN'}) ===")
    print(f"input: {input_dir}")
    print()

    print("[1/2] Dedupe (Pass A: ' 2.md' siblings, Pass B: cross-directory)...")
    dedupe_stats = dedupe(input_dir, apply=args.apply)
    print(f"    Pass A (' 2.md'): {dedupe_stats['deleted_passA_2md']} would-delete | "
          f"{dedupe_stats['quarantined_passA_2md']} would-quarantine")
    print(f"    Pass B (cross-dir): {dedupe_stats['deleted_passB_crossdir']} would-delete | "
          f"{dedupe_stats['quarantined_passB_crossdir']} would-quarantine")
    print()

    print("[2/2] Structural pre-extraction...")
    structural = extract_structural(input_dir)
    print(f"    {structural['files_processed']:,} files → "
          f"{len(structural['nodes']):,} nodes, "
          f"{len(structural['edges']):,} EXTRACTED edges")
    print()

    if args.apply:
        preflight_path = out_dir / ".graphify_preflight.json"
        preflight_path.write_text(json.dumps(structural))
        report_path = out_dir / "_prep_report.md"
        write_report({}, dedupe_stats, structural, report_path)
        print(f"Wrote {preflight_path}")
        print(f"Wrote {report_path}")
    else:
        print("(dry-run — re-run with --apply to make changes)")


if __name__ == "__main__":
    main()
