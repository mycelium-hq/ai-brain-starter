#!/usr/bin/env python3
"""
graphify_stage_select.py — Stage selection for the graphify staged rollout.

Walks a corpus folder, applies the standard filters (≥500 words, no [AI Extract]),
checks the cache for REAL LLM extractions (not preflight stubs — see Lesson #39),
and bin-packs the misses into ~50K-word chunks ready for parallel dispatch.

LESSON #39 (2026-04-11):
The original stage2_select.py counted ANY cache file as "done", but the cache
contains both preflight regex stubs AND real LLM extractions under the same
SHA256 keying. Result: false-negative work ("0 tokens needed") when the
semantic layer is actually missing.

LLM cache entry signature (any ONE is sufficient):
  - has non-empty hyperedges list
  - any edge has confidence != "EXTRACTED"
  - any edge has confidence_score != 1.0

Preflight-only signature: structural relations ("references", "expresses_floor")
with confidence="EXTRACTED" and score=1.0. These are NOT real hits — re-extract.

Usage:
    python3 graphify_stage_select.py <corpus_folder> [--target-words 50000] [--stage-pct 1.0] [--stage-skip-pct 0.30]

Examples:
    # Stage 3: full Daily Logs
    python3 graphify_stage_select.py "📅 Daily Logs"

    # Stage 2: skip the recent 30% (already done in Stage 1), take the rest
    python3 graphify_stage_select.py "📓 Journals" --stage-skip-pct 0.30

    # Stage 5 sub-stage: full Writing folder
    python3 graphify_stage_select.py "✍️ Writing"
"""
import argparse
import json
import hashlib
import os
import sys
from pathlib import Path
from datetime import datetime

# Auto-detect vault root from script location
_SCRIPT_DIR = Path(__file__).resolve().parent
VAULT = _SCRIPT_DIR.parent.parent  # ⚙️ Meta/scripts/ -> ⚙️ Meta/ -> vault root
CACHE_DIR = VAULT / "graphify-out" / "cache"


def is_llm_extraction(cache_data: dict) -> bool:
    """Return True if a cache entry is from LLM extraction, False if preflight-only."""
    if cache_data.get("hyperedges"):
        return True
    for edge in cache_data.get("edges", []) or cache_data.get("links", []):
        conf = edge.get("confidence")
        score = edge.get("confidence_score")
        if conf and conf != "EXTRACTED":
            return True
        if score is not None and score != 1.0:
            return True
    for node in cache_data.get("nodes", []):
        conf = node.get("confidence")
        if conf and conf != "EXTRACTED":
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_folder", help="Folder relative to vault root, e.g. '📅 Daily Logs'")
    ap.add_argument("--target-words", type=int, default=50000)
    ap.add_argument("--stage-skip-pct", type=float, default=0.0,
                    help="Skip the most-recent N%% of files (e.g. 0.30 for 30%%, used by Stage 2 to skip Stage 1's slice)")
    ap.add_argument("--min-words", type=int, default=500)
    ap.add_argument("--skip-ai-extract", action="store_true", default=True)
    ap.add_argument("--out-prefix", default="graphify-out/.chunk_")
    args = ap.parse_args()

    os.chdir(VAULT)
    folder = Path(args.corpus_folder)
    if not folder.exists():
        print(f"folder not found: {folder}", file=sys.stderr)
        sys.exit(1)

    all_files = [f for f in folder.rglob("*.md") if "_review_alternate_drafts" not in f.parts]
    print(f"Total files in {folder}: {len(all_files)}")

    if args.stage_skip_pct > 0:
        def sort_key(f):
            try:
                return datetime.strptime(f.stem[:10], "%Y-%m-%d").timestamp()
            except Exception:
                return f.stat().st_mtime
        all_files.sort(key=sort_key, reverse=True)
        skip_count = int(len(all_files) * args.stage_skip_pct)
        candidates = all_files[skip_count:]
        print(f"Skipping most-recent {args.stage_skip_pct*100:.0f}% ({skip_count} files)")
        print(f"Candidates: {len(candidates)}")
    else:
        candidates = all_files

    eligible = []
    skipped_small = 0
    skipped_ai = 0
    word_counts = {}
    for f in candidates:
        if args.skip_ai_extract and f.stem.startswith("[AI Extract]"):
            skipped_ai += 1
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        wc = len(text.split())
        word_counts[str(f)] = wc
        if wc < args.min_words:
            skipped_small += 1
            continue
        eligible.append(f)
    print(f"Eligible for LLM: {len(eligible)}")
    print(f"  Skipped <{args.min_words} words: {skipped_small}")
    if args.skip_ai_extract:
        print(f"  Skipped [AI Extract]: {skipped_ai}")

    # Cache check (LLM-only, per Lesson #39)
    llm_hits = 0
    preflight_only_hits = 0
    real_misses = []
    for f in eligible:
        try:
            content = f.read_bytes()
            resolved = str(f.resolve()).encode()
            h = hashlib.sha256(content + b"\x00" + resolved).hexdigest()
            cache_file = CACHE_DIR / f"{h}.json"
            if cache_file.exists():
                data = json.loads(cache_file.read_text())
                if is_llm_extraction(data):
                    llm_hits += 1
                else:
                    preflight_only_hits += 1
                    real_misses.append(f)
            else:
                real_misses.append(f)
        except Exception:
            real_misses.append(f)

    print()
    print(f"Cache breakdown (preflight-aware):")
    print(f"  Real LLM hits:          {llm_hits}")
    print(f"  Preflight-only (redo):  {preflight_only_hits}")
    print(f"  Total needing LLM work: {len(real_misses)}")

    # Bin-pack
    total_words = sum(word_counts[str(f)] for f in real_misses)
    target_chunks = max(1, (total_words + args.target_words - 1) // args.target_words)
    print()
    print(f"Total words needing LLM: {total_words:,}")
    print(f"Target chunks: {target_chunks}")

    items = sorted([(f, word_counts[str(f)]) for f in real_misses], key=lambda x: -x[1])
    bins = [[] for _ in range(target_chunks)]
    bin_w = [0] * target_chunks
    for f, w in items:
        idx = bin_w.index(min(bin_w))
        bins[idx].append(f)
        bin_w[idx] += w

    # Clean old chunk files matching this prefix
    for old in Path("graphify-out").glob(".chunk_*_files.txt"):
        old.unlink()
    for old in Path("graphify-out").glob(".chunk_*_result.json"):
        old.unlink()

    for i, (b, w) in enumerate(zip(bins, bin_w), 1):
        Path(f"{args.out_prefix}{i:02d}_files.txt").write_text("\n".join(str(f) for f in b))
        print(f"  chunk_{i:02d}: {len(b)} files, {w:,} words")

    print()
    print(f"Total: {sum(len(b) for b in bins)} files, {sum(bin_w):,} words")
    naive = sum(bin_w) * 2.55 / 1000
    grep_first = sum(bin_w) * 2.55 * 0.54 / 1000  # 46% reduction per Lesson #42
    print(f"Expected cost naive: ~{naive:.0f}K tokens")
    print(f"With Grep-first (Lesson #42 — 46% reduction): ~{grep_first:.0f}K tokens")


if __name__ == "__main__":
    main()
