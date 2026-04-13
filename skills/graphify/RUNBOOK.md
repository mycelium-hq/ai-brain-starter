# Graphify Runbook

> 🛑 **CLAUDE — STOP. READ THIS WHOLE FILE IN FULL BEFORE DOING ANYTHING GRAPHIFY-RELATED. NO EXCEPTIONS.**
>
> This applies to ALL graphify-related work: running the pipeline, checking coverage or status, answering questions about the graph, estimating costs, querying graph data, or any other graphify topic. "I'm just checking coverage" is NOT an exception. The runbook contains the correct methods, filters, and lessons that determine HOW to do every graphify task.
>
> This file is long, typically 12-15k tokens, which means **it will exceed the Read tool's 10k-token cap** and a single naive Read call will return an error. When that happens, use `offset` + `limit` to chunk through it (e.g. `offset=1 limit=200`, then `offset=200 limit=200`, then `offset=400 limit=200`). **Do NOT substitute Grep, head_limit, or sampling for reading.** Every skipped lesson has historically cost 10-60 minutes of wasted work.
>
> **Session-start gate:** before doing ANY graphify-related work you must have (a) read this file in full, (b) completed the pre-flight checklist below, (c) verified no other stale graphify process is running. If any of the three is not true, stop and complete them first. This gate exists because skimmed runbooks have been the single biggest source of wasted work in production sessions.

---

## PRE-FLIGHT CHECKLIST (run before every graphify session)

Do these in order. Each one takes <30 seconds and prevents a known failure class.

1. **Read this whole file.** Chunked via offset+limit if needed.
2. **Check for stale graphify processes** from other sessions or worktrees: `ps aux | grep -E "graphify|stage_select" | grep -v grep`. If one is sitting at 0% CPU for >2 minutes, it's hung on Lesson #6 (first-Python-detect hang) — kill it and restart cleanly.
3. **Force-warm the target folder if your vault is on a sync service** (iCloud Drive, Google Drive, OneDrive, Dropbox). Lesson #17 — cold reads can be 1000x slower than warm reads and look exactly like a hang. On macOS iCloud: `brctl download "<folder>"` queues the download; wait 30–60s then do `ls` / `find | wc -l` on the folder to confirm files are actually local. Exit 0 from `brctl` means "queued," not "downloaded."
4. **Never call `check_semantic_cache` on large corpora.** It re-hashes every file and blocks for minutes on cold reads. Use the fast cache-iteration pattern: iterate `graphify-out/cache/*.json`, read each cache file's `source_file` fields, bucket by folder + by `is_llm_extraction()` discriminator. Runs in <2s on any corpus size.
5. **Prioritize concept-dense corpora over episodic ones.** Books / Notes / Writing / Strategy / Business yield roughly 3x the unique concepts per token of Journals / Daily Logs / AI Chats. If the budget is tight or you want maximum structural signal, graphify the concept-dense corpora **first**, then spend remaining budget on journals. The default for "run /graphify on more of the vault" should be **concept-dense first** unless the user explicitly names an episodic corpus.
6. **Verify the cwd matches the target vault root.** Wrong-root runs produce 0 cache hits, inflate the cost estimate 5–10x, and write new nodes into the wrong graph. See Lesson #35.
7. **Run the stage-selection script to size the job BEFORE dispatching any subagents.** It already knows about the ≥500-word filter, the `[AI Extract]` skip, the preflight-aware cache discriminator, and emits a real cost estimate with the Grep-first reduction applied. If you're estimating cost by hand instead of running the sizer, you're overestimating 2–4x. **Exception:** for capped slices ("pick 200 newest journals"), skip the full-corpus sizer and use a targeted picker instead — see Lesson #38.

If you complete this checklist and still haven't read the full file, **stop here and go read it.** The checklist is the lower bound, not a substitute.

---

How to run `/graphify` on a vault efficiently. **Read this before every graphify session** and update it whenever a run reveals a new optimization or gotcha.

This runbook is the production playbook from running graphify on a 4,700-file personal vault across 5 sessions and ~5M tokens. Every lesson is from a real failure or optimization that landed.

---

## TL;DR — Pick the right mode

| Situation | Mode | Cost |
|---|---|---|
| Brand-new corpus, never extracted | full pipeline (Phases 0–7 below) | high (one-time) |
| Weekly/monthly additions | `/graphify <path> --update` | low (only new files) |
| Recovery / re-extraction | full + cache restore | medium |
| Re-cluster after manual edits | `--cluster-only` | free |
| Just added a new article | `add` then `--update` | tiny |

**Default for ongoing work:** `--update`. Full runs are one-time.

---

## How graphify accumulates state

By default, `/graphify <path>` **overwrites** `graphify-out/graph.json` with a fresh build. Each run is independent unless you use `--update`.

With `--update`:
1. Reads existing `graphify-out/graph.json`
2. Computes which files changed since the last run (via the manifest)
3. Re-extracts only changed files via LLM (skips cached ones)
4. Calls `G_existing.update(G_new)` — networkx union — to merge
5. Re-clusters the merged graph
6. Writes the merged result back

**`--update` is additive. Default is replace.**

The `graphify-out/cache/` directory is what makes incremental runs cheap. Every per-file extraction is stored there with a content hash. Unchanged files = free cache hits.

**Implication for weekly maintenance:** add new files → run `/graphify <folder> --update`. Only the new files cost LLM tokens.

---

## The optimized pipeline (use this every time on big runs)

### Phase 0 — Sanity check

```bash
cd /path/to/your/vault
ls graphify-out/graph.json && echo "existing graph present"
cp graphify-out/graph.json "graphify-out/graph.json.backup_$(date +%Y%m%d_%H%M)"
```

Always back up before any run that might overwrite.

### Phase 1 — Prep (run BEFORE LLM extraction)

```bash
# Dry-run shows what will be deleted/quarantined and how many regex edges
# will be pre-extracted for free.
python3 skills/graphify/scripts/graphify_prep.py graphify-input

# Apply: deletes byte-identical " 2.md" duplicates, quarantines alternate
# drafts to graphify-input/_review_alternate_drafts/, and writes
# graphify-out/.graphify_preflight.json with all regex-extracted wikilinks.
python3 skills/graphify/scripts/graphify_prep.py graphify-input --apply
```

**What this does:**
- Deletes `* 2.md` files byte-identical to their original (often 30%+ of files in legacy vaults)
- Quarantines `* 2.md` files that ARE different to `_review_alternate_drafts/` for human review
- Walks every remaining `.md` file with regex and pre-extracts:
  - All `[[wikilink]]` references → EXTRACTED edges
  - YAML frontmatter `floor` / `dominant_floors` → typed edges to canonical floor nodes
  - Every wikilink target becomes a canonical node

**Why this matters:** wikilink regex pre-extraction yields **more edges than the LLM does** — and is free. On one 566-file run: regex produced 11,809 EXTRACTED edges vs 1,468 LLM edges on a 200-file batch. Always run prep first.

### Phase 2 — Detect

```python
from graphify.detect import detect
from pathlib import Path
import json

result = detect(Path('graphify-input'))
print(f"{result['total_files']} files / {result['total_words']:,} words")
open('graphify-out/.graphify_detect.json', 'w').write(json.dumps(result))
```

**If `total_files > 200`: stop and show the user the scope before dispatching subagents.** Let them choose A (full) / B (slice) / C (skip). See "Cost guardrails" below.

**Known issue:** the first `detect()` call after a fresh shell sometimes hangs at 0% CPU for 7+ minutes (Python + pipx env init). If it hangs >90s, kill and retry — it works the second time. Wrap with a 90s `signal.alarm()` so a hang doesn't burn the session.

### Phase 3 — Stage select + chunk + dispatch

For staged runs, use the stage selector:

```bash
python3 skills/graphify/scripts/graphify_stage_select.py "Notes" --target-words 50000
```

This reads the cache, discriminates real LLM extractions from preflight stubs (Lesson #18), and bin-packs only the files that genuinely need LLM work into ~50K-word chunks. Output: `graphify-out/.chunk_NN_files.txt`.

Then dispatch ALL chunk subagents **in a single message** (parallel calls). Each subagent gets the prompt from `graphify-extraction-prompt.md` with the chunk file list path and output path substituted in.

**Tighten the prompt:** since regex already grabbed wikilinks, tell agents to skip them and only add INFERRED / semantic / hyperedge content.

### Phase 4 — Finish

```bash
python3 skills/graphify/scripts/graphify_stage_finish.py \
    --num-chunks 12 \
    --stage-name "stage 2" \
    --token-cost-k 1377
```

This script runs the entire end-of-stage cascade:
1. Combines all chunk JSON results
2. Auto-cleans slash labels (Lesson #29)
3. Canonicalizes (Lesson #3)
4. Backs up + union-merges with existing `graph.json`
5. Reclusters and regenerates `GRAPH_REPORT.md`
6. Saves the semantic cache
7. Verifies the cache upgrade succeeded (Lesson #19)

### Phase 5 — Cleanup

```bash
rm -f graphify-out/.chunk_*_files.txt graphify-out/.chunk_*_result.json
rm -f graphify-out/.graphify_extract.json graphify-out/.graphify_detect.json
# Keep: graph.json, graph.html, GRAPH_REPORT.md, _prep_report.md, cache/, the backup
```

**Gate cleanup behind a success flag.** Don't delete chunk results until `graph.json` has been written successfully — if the report step errors, you'll need them to recover.

---

## Cost guardrails — non-negotiable

**Token estimate per chunk** (measured on real runs):
- ~110K total tokens per chunk of 20 files (input + output combined)
- ~50K input tokens (file reading)
- ~10–20K reasoning context
- ~3–5K output JSON
- ~1.5K of pure prompt-instruction redundancy per chunk

**Per-chunk wall time:** 4–7 minutes.

**Parallel cap:** ~10–12 in flight at once. Going beyond hits 429 rate limits.

| Files | Chunks (size 50) | LLM cost | Wall time |
|---|---|---|---|
| 200 | 4 | ~1M tokens | 5–8 min |
| 566 | 12 | ~3M tokens | 15–30 min |
| ~50 weekly additions | 1 | ~330K tokens | 2–5 min |

**Rules:**
1. **Always smoke-test 1 chunk first** before dispatching the full batch. Measure real cost-per-chunk, multiply, decide.
2. **Ask the user before any run estimated > 1M tokens.** Always offer A (full) / B (slice) / C (skip).
3. **Don't dispatch more than ~12 in parallel.** For >12 chunks, dispatch in waves of 10 with 30–60s gaps.
4. **Save to cache before cleanup.** If you skip this, the next weekly run repays the entire cost.
5. **Track cumulative session spend.** The per-stage budget ≠ rolling-window budget. Default cap: 2M per session. Above that, force `/clear` and start fresh.

---

## Quality checks (run after every session)

```python
import json
from collections import Counter

g = json.loads(open('graphify-out/graph.json').read())
nodes = g['nodes']
edges = g.get('links', g.get('edges', []))
print(f'nodes: {len(nodes)}, edges: {len(edges)}')
print(f'edges/node: {len(edges)/max(1,len(nodes)):.2f}')

labels = Counter(n.get('label', '') for n in nodes)
dupes = [(l, c) for l, c in labels.items() if c > 1]
print(f'duplicate labels: {len(dupes)} (should be 0 after canonicalize)')
```

**Healthy signals:**
- edges/node ratio between 0.8 and 2.0
- duplicate labels = 0
- Top god nodes match what you intuitively know about the corpus
- Community count under 80 for a corpus under 1,500 nodes

**Red flags:**
- edges/node < 0.3 → extraction may have failed
- duplicate labels > 0 → canonicalize was skipped
- 200+ communities for a small corpus → graph is fragmented, run canonicalize

---

## Lessons learned

These are the lessons from real production runs. Each one comes from a failure that cost time, tokens, or both.

#### Standing rule — active lesson capture

**Capture optimizations and gotchas THE MOMENT they surface, not at session-end.** Every graphify session produces new lessons as it runs — new cold-read thresholds, new filter-attrition math, new content-level gotchas, new failure modes. If you wait until the end to write them up, you lose the specifics (exact numbers, exact error messages, exact file paths) and the lesson degrades to vague pattern-matching. **The rule:** as soon as you observe something that would change how you'd run the next session, stop and append it to this file *before* continuing. Ten seconds to write now beats ten minutes of re-derivation next week.

**Triggers for a new lesson:**
- Unexpected cost or time delta (better OR worse than estimate)
- New failure mode or error class
- A workaround that worked (so next time you skip the broken path)
- A content-level pattern the tooling can't auto-detect (e.g. near-duplicate draft clusters)
- Any moment you think "I should remember this next time"

**Where to put it:** as a numbered lesson at the appropriate subsection below. Use the most recent number + 1. Add a `*(was #NN)*` cross-ref only if it supersedes or merges with a previous lesson. Lessons are append-only — if a finding turns out to be wrong, update the existing lesson with the correction and the date, don't delete it.

#### Standing rule — every batch/dispatch doc includes a validation-hypotheses section

**Every handoff doc for a graphify batch or stage must include an explicit "What this run is testing" section** with numbered hypotheses, predictions, measurement methods, and kill criteria. Table format: *# | Hypothesis | Prediction | How to measure | Kill criterion*. This turns every stage into a live experiment for the lessons it depends on, so claims either ship permanently or get falsified before they calcify into folklore.

**Why it matters:** you already pay the tokens. Recording the measured result against a pre-registered prediction is free signal. Without it, lessons stay anecdotal — you remember "cap-7 worked on the last run" but you don't know if it's still working three stages later. WITH it, every stage either strengthens the lesson (with N more data points) or explicitly overturns it (with a measured kill-criterion trigger).

**What to include in the hypotheses table:**
- **Predictions should be quantitative when possible** ("concepts/Ktoken ≥ 0.85", "chunk emits 5–7 hyperedges", "0 fallback parses needed") — not qualitative ("works well", "looks right"). Quantitative predictions force real measurement and have real kill criteria.
- **Kill criteria should specify a revision or rollback**, not just "investigate." Example: *"if <4 hyperedges emitted, reset single-file chunks to cap-5 in the prompt template for future runs."* That way a failed hypothesis is immediately actionable.
- **Cover the new lessons from the most recent session** as the default set. If no new lessons shipped recently, cover the oldest un-revalidated lessons in the relevant sections — a standing inventory of "what's due for a re-test."
- **Target 4–8 hypotheses per stage.** Fewer = under-utilized, more = diluted focus.

**Post-dispatch discipline:** when the stage finishes, append a "Results" section to the handoff doc BEFORE running cleanup. For each hypothesis, write *measured value → verdict (SHIPS / REVISE / KILL) → runbook update action*. Copy the verified findings as numbered-lesson updates in this runbook. Do not delete the handoff doc until the runbook updates are in place — it's the only source of the experimental log.

**Why this is a rule not a suggestion:** the alternative failure mode is optimizations that "felt right" at the time but never get measured against reality. A cap-change shipped based on N=1 observation would stay shipped regardless of whether it continued to work. This rule catches drift early.

---

### Dedupe + preflight

1. **Run `graphify_prep.py --apply` first — dedupe is enormous.** Pass A handles `* 2.md` siblings, Pass B handles cross-directory duplicates. **Always grep the vault for subdirectory names before deleting cross-dir dupes** to confirm nothing depends on them.

2. **Wikilink regex pre-extraction yields more edges than the LLM does — and is free.** Always run prep first; tell agents to skip wikilinks. ~50% of files have zero wikilinks and need full LLM extraction; the other 50% are already covered by regex.

3. **Per-file scoped IDs cause node bloat.** Agents emit `2024-03_topic` style IDs to avoid collisions. Always run `graphify_canonicalize.py` after merge or you'll see the same concept as 60+ separate nodes.

4. **Validate extractions before build.** Agents invent invalid `file_type` values (`person`, `concept`, `place`, etc. — only `document/code/image/paper/rationale` are valid). `validate_extraction()` is a free pre-flight check.

5. **Hyperedges silently disappear if the prompt example shows `[]`.** Tighter prompt requests 1–3 per chunk (1–5 for concept-dense corpora — see #30).

6. **First Python detect call hangs in some shells.** Always wrap with a 90s timeout and retry once.

### Chunking + dispatch

7. **Chunk-size-20 wastes prompt overhead.** Each chunk pays ~1.5K tokens of redundant prompt instructions. **Use 50 files per chunk** — same per-file cost, ~60% fewer redundant prompts.

8. **Word-balanced chunking, not alphabetical.** Greedy bin-pack across word count to avoid the slow-stragglers problem (one chunk with 100K words while another has 2K).

9. **Parallel cap is ~10–12 in flight.** Dispatching 29 in one message hits 429 rate limits. For runs >12 chunks, dispatch in waves of 10 with 30–60s gaps.

10. **Skip `[AI Extract]` files and files <500 words from LLM extraction** — they rarely yield novel inferred edges beyond what regex catches.

11. **Chunk results stay valid even when the agent's closing message fails** with a rate limit. The result JSON is written before the close-out call. Always check the file before assuming the agent failed.

### Cache mechanics

12. **`save_semantic_cache` MUST run before cleanup.** Without it, the next `--update` run pays full price again. The cache is keyed by `SHA256(file_contents + null + resolved_path)`, so it survives renames-but-not-content-changes.

13. **`save_semantic_cache` silently writes 0 entries when `source_file` paths are relative** and the CWD is a temp workdir not matching the vault root. Symptom: cache count = 0 even though extraction has thousands of nodes. **Fix:** normalize every `source_file` to absolute paths before calling the cache API.

14. **Cache misses when a corpus is re-rooted.** Cache keyed by `SHA256(content + null + resolved_path)` — same content at different paths = 0 cache hits. Restructuring the vault invalidates the cache.

15. **Cache-hit detection must distinguish preflight stubs from real LLM extractions** (Lesson #18). Preflight regex stubs and real LLM extractions share the same SHA256 cache keying but encode very different quality. A naive "does a cache file exist?" check counts preflight as "done" and reports `0 tokens needed` even when the semantic LLM layer is missing. Use `is_llm_extraction()` from `graphify_stage_select.py`.

16. **Cache upgrades are invisible by directory count.** Every new LLM extraction OVERWRITES the matching preflight stub at the same hash. Directory count never grows from preflight upgrades. To audit success, count entries with `mtime > now - 1h` AND `is_llm_extraction()` signature, not raw entry count. `graphify_stage_finish.py` Step 5b does this automatically.

### Performance + I/O gotchas

17. **Remote-storage cold reads are 2–1000x slower than local.** Two known triggers: **iCloud demand-paging** (0.15s warm vs 226s for 1,000 files cold — looks exactly like a hang). **Google Drive sync** (2–5x slower on cloud-synced inputs). **Fix:** `brctl download "<folder>"` before any bulk file op on iCloud paths; use smaller `--target-chunks` for cloud-synced inputs. **Smell test:** read 200 files in Python — if it takes >5s, files are cold.

18. **`signal.alarm` is process-global.** A 180s timeout set at script start will fire mid-cache-save if build/cluster ate most of it. Don't span timeouts across stages. Set fresh alarms per stage.

19. **System `python3` may not have the `graphify` module.** The package is typically installed via pipx as `graphifyy`. Use the pipx venv's python for any script that does `from graphify.* import *`.

20. **graphify package API drifts.** `suggest_questions`, `to_html`, and `generate` all need different args than the simple "import and call" pattern. **Fix:** build `community_labels` manually as `{cid: G.nodes[max(nids, key=lambda n: G.degree(n))]['label'] for cid, nids in communities.items()}`. Then either skip the broken callsites or write a simplified report by hand. `graphify_stage_finish.py` handles all the API drift.

### Tool-use efficiency

21. **Tool-use count is the #1 per-chunk token cost predictor — Grep-first prompt cuts 46% off baseline.** Low tool-use chunks (≤15 calls) average ~100K tokens / 80 nodes. High tool-use chunks (≥35 calls) average ~160K tokens / 70 nodes — same quality, 60% more tokens.

    **The fix — add this block to every dispatch prompt:**

    > Do NOT read files one at a time. Either: (a) use Grep over the entire chunk file list to find people/concepts/frameworks in one pass, then Read only the ~5 files with the densest hits, OR (b) batch all Read calls in parallel in a single response.

    **Target:** median tool-use ≤15 per chunk, max 25, red flag at 30+.

22. **Subagents must set `source_file` to a specific .md path, never a directory.** A bug emitted `source_file: "Notes/"` for every node, which broke `save_semantic_cache` with `Errno 21: Is a directory`. **Prompt rule:** *"For every node and edge, `source_file` MUST be the specific .md file path that content came from, NEVER a directory."*

### Canonicalize + label hygiene

23. **Path-form wikilinks don't canonicalize with bare-name wikilinks.** `Folder/Concept` and `Concept` show up as separate god nodes because canonicalize matches by label. **Fix:** extend canonicalize to strip folder prefixes from labels before hashing. Safer than rewriting vault files.

24. **Long filenames become unreadable god nodes.** Cap file-stem labels at 60 characters with ellipsis. Full path stays in `source_file`.

25. **Auto-patch slash labels before merge.** Slash-in-label violations like `Person/Role` (where `/` is "or"-separator, not a path) break canonicalize. `graphify_stage_finish.py` has `clean_slash_label()` that runs as a pre-canonicalize pass.

### Hyperedges

26. **Hyperedge yield is consistent and high-quality.** Pairwise edges literally cannot capture multi-node concepts like "Five Steps of Feedback Wheel". Most novel signal in a run.

27. **Cap 1–5 for concept-dense corpora** (Books, Notes, Writing, Strategy, Business) — these often have material for 5+ interpretable hyperedges per chunk. **Cap 1–3 for episodic content** (Journals, Daily Logs, AI Chats, CRM) — these are narrative-dense, not framework-dense.

28. **Self-restraint behavior is the cleanest signal the cap is working.** If a chunk has only material for 4 hyperedges and the cap is 5, agents emit 4 — not padded 5. If you see padding, the cap is too high.

### Token budget + session orchestration

29. **Per-stage budget ≠ session budget.** The "ask before any run > 1M" guardrail is per-stage. The real constraint is the rolling window across ALL recent agent calls. Stage 2 (1.4M) + Stage 3 (0.3M) + Stage 5 (~500K) = 2.2M cumulative, exceeded the per-rolling-window quota. **Fix:** track cumulative spend; default budget 2M per session. Above that, `/clear` and a fresh session.

30. **Wave-of-10 cap is too generous when usage is tight.** When the rolling window is already consumed, even 5 parallel agents can blow the remaining quota in seconds. **Fix:** when cumulative session spend > 1M, drop to **waves of 3 with 60s gaps**.

### Subagent failure modes

31. **Subagents from a worktree session can't write to disk — inline-JSON-in-message is the only escape.** Worktree-restricted permissions deny Write to ALL absolute paths (including `/tmp`). **Mitigations:**
    - **Best:** dispatch from the main session, not a worktree
    - **Always include in the prompt template:** *"If Write or Bash is denied, inline the COMPLETE JSON payload in your final message inside a ```json code fence, followed by 'chunk NN done'."*
    - **Always verify `.chunk_NN_result.json` files exist before merging** — recovery loop is now standard practice

32. **Always run a normalizer before merge.** Agents emit JSON in subtly-different schemas: `relationship` vs `relation`, numeric `confidence: 0.9` vs split `confidence: "INFERRED"` + `confidence_score: 0.9`, `from`/`to` vs `source`/`target`, custom relation names like `authored`, `cites_example`, `framework_cluster`. **The prompt schema is an ASPIRATION, not a guarantee.** The LLM improvises ~80% of the time. Always normalize before merge.

### Optimization patterns

33. **Known-entity priming is a focus directive, not an output filter.** Telling the LLM "skip the top-100 god nodes" doesn't reduce output — it **redirects attention to second-tier depth**. Measured +59% efficiency gain (0.79 → 1.26 concepts per Ktoken). Ship priming on every dispatch.

34. **Concept whitelist for the regex preflight.** Hand-curated list of authors, frameworks, and companies that frequently appear in prose without wikilinks. `graphify_prep.py` scans every file for these and emits free `mentions` edges. After each dispatch, scan the LLM-only nodes for entities that appeared in 3+ files and append them to the whitelist. **Whitelists scale better than re-inference because they compound across runs at zero marginal cost.**

35. **Wrong-root cache miss is the costliest beginner mistake.** Symptoms: detect flags everything as "new", cache returns 0 hits, cost estimate jumps 5–10x. **Rule:** if a folder was previously graphified and shows 0% hits, you're 100% at the wrong root. The pre-flight sanity assertion in `graphify_stage_select.py` warns when this happens.

### Long-form / single-file routing

36. **Long-form Writing should use graphify's native chunker, not a parallel-agent flow.** The parallel pipeline was designed for episodic corpora where each file is self-contained. For book chapters and long-form essays where a single file IS the conceptual unit, use `/graphify "Writing/" --update` (intra-file chunker).

### Session-start discipline and read-tool patterns

37. **Read-tool 10k-token cap is a trap for long runbooks — use offset+limit, never Grep sampling.** This file is ~12–15k tokens. A naive `Read` call returns an error. The wrong response is to fall back to Grep with `head_limit` — Grep is a search tool, not a reading tool, and sampling from the middle of a structured document leaves you confident you've "covered it" while missing most of the actual content. **The correct response** is to chunk the Read: `offset=1 limit=220`, then `offset=220 limit=200`, then `offset=420 limit=200`. Three reads cover the whole file and cost ~45s total. This discipline applies to ALL runbooks and SKILL files that exceed the cap — not just this one.

38. **Full-corpus sizers waste I/O when the request is a capped slice — use a targeted picker instead.** The full stage-selection script walks every file in the target folder because it's designed for "full stage" rollouts: word-count every file, SHA256-hash every file for cache lookup, then bin-pack everything eligible. For a capped request like "pick 200 newest journals + 100 largest writing files" this is a **~9x overshoot on I/O** (2,700 files instead of the 300 you actually need) and it compounds with Lesson #17 cold-read costs. **The rule:** if the request is a capped count (`N newest`, `N largest`, `N random`), write a targeted picker that (a) globs the folder, (b) sorts by the selection key *without* reading file contents (date parsed from filename, `st_size` for "largest-first", `st_mtime` for recency), (c) iterates only up to ~1.6–2.0x the cap (overshoot to survive the <500w + cache filters), (d) reads each file ONCE in a `ThreadPoolExecutor` with 16 threads to compute word count + cache hit in a single pass, (e) stops at the cap. **Filter-attrition math:** journals typically lose ~70% of candidates to the `<500w OR already-cached` filter, so overshoot 2.0x. Writing loses ~40%, so overshoot 1.6x. Different corpora have different attrition profiles — measure on the first run and hard-code constants per corpus type. **Threaded reads matter:** sequential cold reads on a sync-service vault hit ~1.3–1.9s per file; a 16-thread pool cleanly overlaps the latency and gets a 6–8x speedup. Python's GIL releases during I/O and sync-service cold reads are network-wait bound, not CPU bound. Sweet spot is 16 threads — 4 leaves bandwidth on the table, 32 hits diminishing returns. **Implementation detail:** classify each file in one pass — read bytes once, word-count from the bytes, hash from the same bytes for cache lookup. Never re-read the file for a second derived metric.

39. **Scan for content-level duplicates in concept-dense corpora BEFORE chunking.** `graphify_prep.py --apply` only catches ` 2.md` siblings (Pass A) and byte-identical cross-dir duplicates (Pass B). It does NOT catch **near-duplicate drafts** — files that share 99% of their content but differ in formatting, wikilinking conventions, or tag style. In practice you'll find these in `Writing/`, `Drafts/`, and any `Substack/Drafts/`-style folder where the same draft lives in multiple places as it's being iterated. **The fix:** after building the chunk file list but before dispatch, run a "potential-duplicate scanner" that groups files by normalized-title similarity (≥0.8 title Jaccard on stemmed words), flags groups of 2+, and prompts for resolution. Writing/, Drafts/, Essays/, and Substack-style folders are the ones most likely to contain variants. Journals and Notes typically don't have this pattern because their naming conventions enforce uniqueness. **Why it matters at token cost:** a single 57k-word draft triplicated across three folders costs ~430K tokens to extract redundantly. The scan takes <10s and can save 5–15% of stage budget on any writing-heavy rollout.

40. **When merging divergent drafts, normalize wikilinks + tags before line comparison AND preserve unique lines in a "Recovered from earlier drafts" appendix — never silent-drop.** Use this normalizer before comparing lines across draft variants: (a) `[[Target|display]]` → `display`, (b) `[[Target]]` → `target`, (c) `#tag` → `tag`, (d) collapse whitespace + lowercase. After normalization you'll typically find that each non-canonical draft has 50–100 substantive lines the canonical version lacks — real prose that would be silently lost if you naively picked one file as canonical and deleted the rest. **The rule:** every merge of divergent content must end with an appendix section under a clearly-marked heading (e.g. `## Recovered from earlier drafts (YYYY-MM-DD merge)`) listing every line that was unique to a non-canonical source. The appendix is annotated with which file it came from, which mtime that file had, and a one-line note telling the user to re-integrate into the main body when they have time. **Never silently drop content during a merge.** Backups of all originals go to `/tmp/<topic>_merge_backup_YYYYMMDD_HHMM/` before any file is overwritten or deleted — recoverable if the merge is wrong.

---

## Cumulative token savings vs naive run

| Optimization | Saved | Cumulative |
|---|---|---|
| Pass A: ` 2.md` dedupe | -32% files | -32% files |
| Pass B: cross-dir dedupe | -50% of remaining | **-66% files** |
| Regex wikilink pre-extract | -50% LLM output | -75% total cost |
| Skip wikilink work in agents | -10% LLM input | -80% total cost |
| Chunk size 50 instead of 20 | -60% prompt overhead | -85% total cost |
| Grep-first prompt | -46% per chunk | -90% total cost |
| Known-entity priming | +20% efficiency | -92% total cost |
| Concept whitelist | ~free edges per session | +5–10% more |
| Cap-7 hyperedges (concept-dense) | +60% hyperedges per chunk | +60% signal density |

A naive run on a 1,660-file corpus would have cost ~12M tokens. With all optimizations: ~5M tokens for a graph with **7,700 nodes / 42,000 edges / 177 hyperedges**. **Net optimization: ~80% cost reduction with strictly higher quality.**

The next weekly maintenance run on the same corpus is targeted at **<200K LLM tokens total** because of the cache + whitelist + Grep-first stack.

---

## When to update this runbook

- After every `/graphify` run that surfaces a new optimization or gotcha
- When graphify itself releases a breaking change
- When the corpus structure changes (new folders, new file naming conventions)
- When the cost model shifts (new model pricing, new chunk size sweet spot)
