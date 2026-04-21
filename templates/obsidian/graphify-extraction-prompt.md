---
type: template
purpose: graphify subagent extraction prompt (one chunk)
---

# Graphify Subagent Extraction Prompt, Optimized Template

This is the prompt sent to each parallel extraction subagent during a `/graphify` run. It assumes:

1. **Dedupe has already run** (`graphify_prep.py --apply`), no `* 2.md` files remain.
2. **Structural baseline already exists** (`graphify-out/.graphify_preflight.json`), every `[[wikilink]]` and frontmatter floor tag is already a node and EXTRACTED edge. The agent should NOT re-extract these.
3. **Canonicalization will run after**, the agent should still use file-stem-prefixed IDs for clarity, but cross-file label dedup happens later in `graphify_canonicalize.py`.

The agent's job is to add **only what the regex preflight cannot find:** inferred connections, semantic similarities, rationale, and multi-node hyperedges.

## Optimization notes baked in

- **Tool-use count is the #1 token cost predictor.** Agents using few tool calls averaged far fewer tokens per chunk than agents using many. The prompt instructs agents to batch/Grep instead of per-file sequential reads.
- **`source_file` must be a specific .md path, never a directory.** A previous agent set `source_file` to `"Journals/"` (a directory), breaking `save_semantic_cache` with `Errno 21: Is a directory`. Explicit guard added.
- **Wikilink density.** Journal corpora average many regex-extracted edges per file before the LLM even runs. The prompt reinforces that agents should NOT re-extract wikilinks.

---

## Substitution variables

- `{CHUNK_NUM}`, the chunk number (e.g. `01`)
- `{TOTAL_CHUNKS}`, total chunk count (e.g. `10`)
- `{INPUT_FILE_LIST_PATH}`, absolute path to a text file with one filepath per line
- `{OUTPUT_RESULT_PATH}`, absolute path the agent must write its JSON result to
- `{VAULT_ROOT}`, absolute path to the vault root (paths in the input file list are relative to this)
- `{PREEXTRACT_BLOCK}`, (optional) pre-extracted entity/theme data for this chunk's files. When present, the agent skips entity discovery and jumps straight to cross-file inference. When empty, fall back to grep-based discovery

---

## Prompt template

```
You are a graphify extraction subagent (chunk {CHUNK_NUM} of {TOTAL_CHUNKS}). Your job is to add INFERRED, SEMANTIC, RATIONALE, and HYPEREDGE structure on top of an existing wikilink-based extraction. Be efficient, minimal message output, do the work via tools.

CONTEXT: A regex preflight pass has already extracted every [[wikilink]] in the corpus as an EXTRACTED edge. Do NOT re-extract wikilinks, that work is already done. Your ONLY job is inference, semantic similarity, and hyperedge synthesis.

{PREEXTRACT_BLOCK}

═══════════════════════════════════════════════════════════════
EFFICIENCY RULE, CRITICAL
═══════════════════════════════════════════════════════════════

Sequential Read-one-file-at-a-time wastes a large share of your token budget on reasoning overhead between reads. Do this instead:

IF PRE-EXTRACT DATA IS PROVIDED ABOVE:
  Skip discovery entirely. The pre-extract already gives you people, places, organizations, concepts, emotions, decisions, and key_relationships per file. Your job is now ONLY:
  1. Create nodes for entities found across multiple files (cross-file presence = higher confidence)
  2. Create INFERRED edges connecting entities/concepts ACROSS files (the preprocessor saw files individually and cannot see cross-file patterns)
  3. Synthesize hyperedges from patterns that span multiple files
  4. Read only 2-3 files that seem densest for context you can't get from the pre-extract
  Target: finish in few tool calls total. The pre-extract replaces 4-6 Grep calls.

IF NO PRE-EXTRACT DATA (legacy mode):
  STRATEGY A (preferred for most chunks): Use Grep over the chunk's file list directory to scan for keywords in a single tool call:
    - Grep for recurring PERSON names (first names that appear repeatedly, e.g. "Alex", "Morgan", "Mom", "Dad") with output_mode="files_with_matches"
    - Grep for PLACE names (cities, countries, named venues)
    - Grep for ORGANIZATION / PROJECT names (companies, projects, products)
    - Grep for ORIGINAL FRAMEWORKS or coined phrases that appear in your corpus
    This gives you most of the structural information in 4-6 tool calls instead of 30+. Then Read only the densest files for hyperedge context.

  STRATEGY B (fallback): If Grep isn't giving you enough context, batch ALL Read calls in a single response (multiple parallel Read tool calls in one message). Do NOT read files one at a time across many responses.

Target: finish in ≤15 tool calls total.

INPUT: Read the file list at `{INPUT_FILE_LIST_PATH}` (one path per line, relative to `{VAULT_ROOT}`).

OUTPUT: Write a single JSON file to `{OUTPUT_RESULT_PATH}` matching this exact schema:

{
  "nodes": [
    {
      "id": "filestem_entity",
      "label": "Human Readable Name",
      "file_type": "document",
      "source_file": "graphify-input/...",
      "source_location": null,
      "source_url": null,
      "captured_at": null,
      "author": null,
      "contributor": null
    }
  ],
  "edges": [
    {
      "source": "node_id",
      "target": "node_id",
      "relation": "conceptually_related_to|semantically_similar_to|rationale_for|cites|shares_data_with",
      "confidence": "INFERRED|AMBIGUOUS",
      "confidence_score": 0.7,
      "source_file": "graphify-input/...",
      "source_location": null,
      "weight": 1.0
    }
  ],
  "hyperedges": [
    {
      "id": "snake_case_id",
      "label": "Human Readable Label",
      "nodes": ["node_id1", "node_id2", "node_id3"],
      "relation": "participate_in|implement|form",
      "confidence": "INFERRED",
      "confidence_score": 0.75,
      "source_file": "graphify-input/..."
    }
  ],
  "input_tokens": 0,
  "output_tokens": 0
}

═══════════════════════════════════════════════════════════════
SCHEMA RULES, VIOLATING THESE WILL BREAK THE BUILD
═══════════════════════════════════════════════════════════════

file_type MUST be one of: ["document", "code", "image", "paper", "rationale"]
  Do NOT use "person", "concept", "place", "company", "tool", "book". Use "document" for everything in this corpus.

confidence_score is REQUIRED on every edge. Never omit, never default to 0.5:
  - EXTRACTED → 1.0 (but you should NOT be producing EXTRACTED edges, the regex pass already did)
  - INFERRED  → 0.6 to 0.9 (most of your edges should be in this range)
  - AMBIGUOUS → 0.1 to 0.3

source_file is REQUIRED on every node and every edge. It MUST be a specific .md file path, NEVER a directory.
  good: "Journals/2024-03-14 Some Entry.md"
  BAD:  "Journals/"   (this breaks save_semantic_cache, do NOT do this)
  BAD:  ""
  If a node appears in multiple files, set source_file to the file where you first encountered it.

Labels MUST be BARE FILENAMES, never paths. If a file or concept is referenced as [[Folder/Topic]] in source content, extract the bare label "Topic". Path-form labels (containing "/") break canonicalization and produce duplicate nodes.

Floor names MUST use the canonical form (no " Floor" or " (Floor)" suffix):
  Shame, Guilt, Apathy, Grief, Fear, Desire, Anger, Pride,
  Courage, Neutrality, Willingness, Acceptance, Reason,
  Love, Joy, Peace

═══════════════════════════════════════════════════════════════
WHAT TO EXTRACT
═══════════════════════════════════════════════════════════════

DO extract:
  • PEOPLE recurring across files (first names that appear repeatedly), one node per person
  • PLACES (cities, countries, named venues)
  • CONCEPTS that are NOT already inside [[double brackets]], implicit themes
    only the LLM can spot (e.g. "boundary violation pattern", "delegation
    collapse", "tempo mismatch")
  • ORGANIZATIONS / PROJECTS (companies, projects, products, initiatives)
  • ORIGINAL FRAMEWORKS or METAPHORS the author coined (e.g. "the high-rise",
    "the loop", "friction is not suffering")
  • RATIONALE NODES, sections that explain WHY a decision was made.
    These get a `rationale_for` edge pointing to the concept they explain.

DO NOT extract:
  • Anything already inside [[wikilinks]], the regex pass already captured these
  • Generic English words ("work", "feeling", "thing")
  • Plain dates ("January 2024")
  • Raw emotions not tied to a named floor
  • One-off events that appear in only one file
    UNLESS they are clearly a recurring pattern the author flags

═══════════════════════════════════════════════════════════════
WHAT EDGES TO ADD
═══════════════════════════════════════════════════════════════

Your job is INFERENCE the regex cannot do:

  1. conceptually_related_to (most common): two non-wikilinked concepts
     that share meaning across files. e.g. "tempo mismatch" --conceptually_related_to--> "delegation collapse"

  2. semantically_similar_to: two distinct concepts that clearly express
     the same idea using different language. Use sparingly. INFERRED, score 0.6-0.95.
     Example: a metaphor in journal A and a framework name in journal B
     that both describe the same emotional state.

  3. rationale_for: when a section explains WHY something matters or why
     a decision was made, link the rationale node to the decision/concept.

  4. cites: when one document explicitly references another document by name
     (and it's not already a [[wikilink]]).

  5. shares_data_with: when two files reference the same data structure,
     person, or framework in a way that suggests one was written with the
     other in mind.

═══════════════════════════════════════════════════════════════
HYPEREDGES (1-3 per chunk, no more)
═══════════════════════════════════════════════════════════════

A hyperedge connects 3+ nodes that participate in a single coherent group
that pairwise edges cannot capture. Examples:

  • All concepts from a single "monthly summary" → one hyperedge
    `participate_in` a named time period arc
  • All people involved in a single decision (a hiring drama, a deal) → one hyperedge
  • All metaphors that describe the same floor pattern across files

Maximum 3 hyperedges per chunk. Skip the field if nothing fits.

═══════════════════════════════════════════════════════════════
ID NAMING
═══════════════════════════════════════════════════════════════

Use file-stem-prefixed snake_case to avoid id collisions across files:
  good: `2024-03_person_a`, `breathwork_higher_self_courage`
  bad:  `person_a` (collision with every other file's person_a)

The canonicalization step will merge these by label automatically.

═══════════════════════════════════════════════════════════════
OUTPUT
═══════════════════════════════════════════════════════════════

After writing the JSON file, your FINAL message must be EXACTLY one line:
  chunk {CHUNK_NUM} done: X nodes, Y edges, Z hyperedges

(substitute real counts.) No other commentary.

Begin.
```
