# Graphify Optimizations

**Read this BEFORE running `/graphify` on a corpus larger than ~50 files.** Without these optimizations, a full graphify run on a notes/journal vault will burn 2-12× more LLM tokens than necessary and produce a worse graph.

These are wrapper scripts (`scripts/graphify_prep.py`, `graphify_canonicalize.py`, `graphify_chunk.py`) that bracket the upstream graphify pipeline. They are tuned for the High-Rise framework that ai-brain-starter installs (the 16 floors from Shame to Peace). The prep step automatically picks up `dominant_floors:` / `floor:` frontmatter tags and turns each into a free EXTRACTED edge to the canonical floor node.

## TL;DR — the cost problem and the fix

A naive `/graphify <vault>` on a 1,500-file markdown vault costs ~10M LLM tokens. With these scripts the same run costs ~1.5M tokens (-85%) and produces a graph with 5-10× more edges. The single biggest savings come from:

1. **Dedupe before LLM extraction** (typical: -32% to -66% files). Vaults accumulate ` 2.md` siblings, cross-directory copies from abandoned staging runs, and other near-duplicates the LLM would otherwise re-process at full cost.
2. **Pre-extract `[[wikilinks]]` with regex** (typical: -50% LLM output). Every wikilink is already an EXTRACTED edge waiting to be picked up — no LLM needed. The LLM should only do INFERRED / semantic / rationale work on top of the regex baseline.
3. **Cache after merge** (next run: ~free for unchanged files). graphify has a built-in `save_semantic_cache` API that the upstream skill never calls if you bypass its merge step. Without this, `--update` mode re-extracts everything.

## The optimized pipeline

```
graphify-input/                          ← your source folder
        ↓
[1] graphify_prep.py --apply             ← dedupe + regex preflight (no LLM)
        ↓
[2] graphify_chunk.py                    ← word-balanced chunking, skip junk
        ↓
[3] dispatch N subagents in parallel     ← LLM-only does INFERRED edges
        ↓
[4] merge chunks + preflight             ← combine regex + LLM
        ↓
[5] graphify_canonicalize.py --cache     ← collapse duplicate labels + write cache
        ↓
[6] build_from_json + cluster + HTML     ← upstream graphify functions
        ↓
graphify-out/graph.json + graph.html
```

For weekly/monthly updates, run `/graphify <path> --update`. The cache from the last full run means only new files cost LLM tokens.

## Step-by-step

### Step 1 — Dedupe + structural pre-extraction

```bash
cd <vault root>

# Dry run first (always)
python3 skills/graphify/scripts/graphify_prep.py graphify-input

# Then apply
python3 skills/graphify/scripts/graphify_prep.py graphify-input --apply
```

What this does:
- **Pass A:** finds `* 2.md` sibling duplicates and deletes md5-identical pairs (quarantines true alternate drafts to `_review_alternate_drafts/`)
- **Pass B:** finds files with the same name in multiple directories (common when previous incomplete runs left staging copies); keeps the shallowest copy, deletes md5-identical others
- Removes empty subdirs after dedupe
- Walks all remaining `.md` files with regex and writes `graphify-out/.graphify_preflight.json` containing every `[[wikilink]]` and YAML frontmatter framework tag as a node + EXTRACTED edge — these are FREE structural edges the LLM should not re-extract

The script auto-recognizes the 16 High-Rise floors (Shame, Guilt, Apathy, Grief, Fear, Desire, Anger, Pride, Courage, Neutrality, Willingness, Acceptance, Reason, Love, Joy, Peace) from `dominant_floors:` or `floor:` frontmatter keys and creates a free `expresses_floor` edge from each tagged file to the canonical floor node. No LLM needed for any of this.

### Step 2 — Word-balanced chunking

```bash
python3 skills/graphify/scripts/graphify_chunk.py graphify-input \
  --target-chunks 12 \
  --skip-ai-extract
```

What this does:
- Walks all `.md` files in `graphify-input/`
- Skips files smaller than 500 words (LLM rarely finds inferred edges in tiny files)
- Skips files prefixed `[AI Extract]` (already-LLM-generated chat summaries with low marginal value)
- Greedy bin-packs the rest across N chunks balanced by **word count, not file count**
- Writes one `graphify-out/.chunk_NN_files.txt` per chunk

Why bin-packing matters: alphabetical chunking on Adelaida's 566-file corpus produced one chunk with 102K words and another with 2K words — 50× variance, slow stragglers, risk of context overflow on the big chunk. Bin-packed chunks all hit ~46K words ± 50.

Why 12 chunks (not 25): each subagent pays a fixed ~1.5K of prompt overhead. 12 large chunks instead of 25 small chunks cuts overhead by ~50% with no quality penalty.

### Step 3 — Dispatch subagents

This step is done by Claude in the `/graphify` skill flow. The agent prompt should:
- Be told that `graphify-out/.graphify_preflight.json` already contains every `[[wikilink]]`
- Be told to **NOT re-extract wikilinks** — only add INFERRED / semantic / rationale / hyperedge content
- Use a strict schema: `file_type` MUST be one of `["document", "code", "image", "paper", "rationale"]` (agents will invent `person`, `concept`, etc. otherwise — see `graphify_canonicalize.py` for the auto-fix)
- Use canonical framework labels with no suffix (`Love` not `Love Floor`)
- Output 1-3 hyperedges per chunk (not 0 — always provide a non-empty `[]` example or agents skip the field)

A complete agent prompt template lives in the parent project's `⚙️ Meta/templates/graphify-extraction-prompt.md` if you want a starting point.

### Step 4 — Merge chunks + preflight

```python
import json
from pathlib import Path

all_nodes = []
all_edges = []
all_hyper = []

# Start with the regex preflight
preflight = json.loads(Path("graphify-out/.graphify_preflight.json").read_text())
all_nodes.extend(preflight["nodes"])
all_edges.extend(preflight["edges"])

# Add LLM chunks
for p in sorted(Path("graphify-out").glob(".chunk_*_result.json")):
    d = json.loads(p.read_text())
    all_nodes.extend(d.get("nodes", []))
    all_edges.extend(d.get("edges", []))
    all_hyper.extend(d.get("hyperedges", []))

Path("graphify-out/.graphify_extract.json").write_text(json.dumps({
    "nodes": all_nodes,
    "edges": all_edges,
    "hyperedges": all_hyper,
    "input_tokens": 0,
    "output_tokens": 0,
}))
```

### Step 5 — Canonicalize + write cache (CRITICAL)

```bash
python3 skills/graphify/scripts/graphify_canonicalize.py \
  graphify-out/.graphify_extract.json \
  --cache
```

What this does:
- Collapses nodes with the same canonical label (`coo_advisory_love`, `breathwork_higher_self_love`, etc. → single `c_love`)
- Strips invalid `file_type` values agents invented (forces them to `document`)
- Remaps edges to canonical IDs and dedupes
- **`--cache` writes results to `graphify-out/cache/` via `graphify.cache.save_semantic_cache`** — this is the single most important optimization for repeat runs. Without it, the next `/graphify --update` re-extracts everything at full price. With it, unchanged files are free cache hits forever (until their content changes).

### Step 6 — Standard graphify build (unchanged)

```python
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_json, to_html
import json
from pathlib import Path

extraction = json.loads(Path("graphify-out/.graphify_extract.json").read_text())
G = build_from_json(extraction)
communities = cluster(G)
to_json(G, communities, "graphify-out/graph.json")
to_html(G, communities, "graphify-out/graph.html")
```

## Cumulative savings

Measured on Adelaida's 1,660-file vault (April 2026):

| Optimization | Savings | Cumulative cost vs naive |
|---|---|---|
| Pass A (` 2.md` dedupe) | -32% files | 68% |
| Pass B (cross-dir dedupe) | -50% of remaining | 34% |
| Skip files <500 words | -10% files | 31% |
| Skip `[AI Extract]` files | -38% remaining | 19% |
| Word-balanced chunks (12 vs 29) | -60% prompt overhead | 12% |
| Regex wikilink preflight | -50% LLM output | 8% |
| **Total naive → optimized** | **-92%** | **~8% of naive** |
| `save_semantic_cache` after merge | next run free for unchanged | weekly runs ~free |

A naive run that would cost ~12M LLM tokens drops to ~1M for the first run, and the next weekly run is essentially free.

## Known gotchas

1. **First `detect()` call sometimes hangs at 0% CPU** for 7+ minutes (Python 3.14 + pipx env startup quirk). Always wrap detect calls with a 90-second `signal.alarm()` and retry once on timeout — the second call always works.
2. **Parallel subagent cap is ~10-12.** Dispatching more than that in a single message causes 429 rate limits on follow-up agent operations. The result writes usually succeed (you just lose the closing handshake message), but be aware that "agent failed" notifications may be misleading — always check the result file directly.
3. **`signal.alarm()` is process-global.** Don't span a single timeout across multiple stages of a script (build + cluster + cache). Set fresh alarms per stage or skip alarms inside the cache write step.
4. **The graphify cache uses `SHA256(file_contents + null + resolved_path)`.** This means moving a file to a new path invalidates its cache entry even if the content is identical. Plan accordingly when reorganizing.
5. **The 16 floor names (Shame...Peace) are baked in.** They come from the High-Rise framework that ai-brain-starter installs in every vault. If you've added your own framework variants, add their lowercase names to `CANONICAL_FLOORS` in `graphify_prep.py` and to `LABEL_SUFFIX_VARIANTS` in `graphify_canonicalize.py`.

## When to update this doc

Every time you run graphify and discover something new — a duplicate pattern that wasn't caught, an agent prompt issue, a chunk size sweet spot, a new graphify version — update both this doc and the corresponding script. The first run of any process is always more expensive than the second; the goal of this doc is to make sure the second run is always cheaper than the first.
