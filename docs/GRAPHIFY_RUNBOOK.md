---
type: runbook
last_updated: 2026-04-21
---

# Graphify Runbook

> 🛑 **READ THIS BEFORE RUNNING `/graphify` OR `/second-brain-mapping` (Phase 2).**
>
> Graphify is the most expensive operation in the ai-brain-starter stack. One full run on a 2,000-file vault costs ~1–3 million tokens. Skipping the optimization wrappers multiplies that 5–10x. A bad run can burn hours and hundreds of thousands of tokens without a useful graph.
>
> The good news: `/second-brain-mapping` already gates graphify behind an explicit y/N prompt, so accidental runs don't happen. This runbook exists for when you intentionally run it.

---

## When to run, when to skip

| Vault size (typed files) | Action |
|---|---|
| < 50 | **Skip.** Not enough cross-doc signal. Metadata extraction + insight engine alone give you more than graphify would. |
| 50–200 | **Slice only.** Pick the richest folder (books, concepts, or journals — not all at once). Smoke-test on 1 chunk before committing. |
| 200–500 | **Full run OK.** Use optimization wrappers. Budget ~1–2M tokens. |
| 500–1500 | **Full run with caution.** ~2–4M tokens. Confirm budget with the user first. |
| > 1500 | **Incremental only.** `graphify <path> --update`. Never full-rebuild. |

## What graphify does vs what metadata extraction does

| Capability | vault-metadata-extract | graphify |
|---|---|---|
| Cost per run | 0 tokens | 100k – millions |
| Speed | seconds | minutes to hours |
| Granularity | file-level frontmatter | concept-level edges across files |
| Best for | Dataview queries, filtering, "show me every X where Y" | cross-document surprise, community detection, "what did I not know was connected" |
| Updates on | every file change | only when you run it |

**Rule of thumb:** if a question can be answered by filtering frontmatter, use Dataview (metadata extract is enough). If the question is "what else is this connected to that I wouldn't have thought of", run graphify.

---

## Pre-flight checklist (every run)

1. **Know what changed since last run.** `stat` the `graphify-out/graph.json`. Anything new? Use `--update`, not full rebuild.
2. **Verify no concurrent process.** Look for running Python processes on `graphify_*.py`. Running two graphifies at once corrupts the cache.
3. **Check disk space.** Graph JSON + cache can hit 500MB on large vaults.
4. **Budget confirmed with user.** Never run >1M tokens without explicit "yes, spend the tokens."
5. **Scope confirmed.** Full vault? One folder? A named subset? Decide before dispatching.

---

## The optimized pipeline (use every time)

Skip these wrappers and cost goes up 5–10x. Per lessons learned across multiple production runs:

```
1. graphify_prep.py              # collect files, filter skip-patterns
2. graphify_dedupe_by_adjacency.py  # drop files nearly identical to already-indexed
3. graphify_chunk.py             # word-balanced chunks of ~20 files each
4. Parallel dispatch             # max 10-12 in flight, waves of 10
5. graphify_stage_finish.py      # merge chunks into graph.json atomically
6. graphify_canonicalize.py --cache  # label canonicalization + cache update
7. graphify_prune_stale_cache.py # remove cache entries for deleted files
```

**Always `--cache` on canonicalize.** Without it, the next `--update` re-extracts everything you just paid for.

---

## Cost guardrails (measured)

- **~110K tokens per chunk of 20 files** (input + reasoning + output JSON)
- **~4-7 min wall time per chunk**
- **Parallel cap: 10-12 in flight**

| Files | Chunks | LLM cost | Wall time |
|---|---|---|---|
| 200 | 10 | ~1.1M tokens | 5-8 min |
| 500 | 25 | ~2.8M tokens | 15-30 min |
| 2,000 (full) | 100 | ~11M tokens | 1-3 hrs |
| 50 (weekly delta) | 3 | ~330K tokens | 2-5 min |

**Non-negotiables:**
1. 1-chunk smoke test before full batch. Every time.
2. Ask the user before any run >1M tokens. Offer: full / slice / skip.
3. Never dispatch >12 chunks at once. Use waves.
4. Save to cache BEFORE cleanup, never after.

---

## Cold-install strategy (new vaults)

**Do NOT run graphify during initial setup.** The ai-brain-starter Phase 23.5 install explicitly defers it.

### Why

A new ai-brain-starter vault has 5–20 files on day one. Graphify on that is all noise: 20 nodes, 30 edges, no community structure. Running costs ~100k tokens for near-zero signal.

### What to tell the new user

> "`/second-brain-mapping` has four phases. Phases 1 (metadata) and 4 (insights) are FREE — zero LLM. You get Claude's context layer on day one.
>
> Phase 2 (graphify) is expensive and opt-in. Wait until you have a month of journaling + 100+ typed files, then fire `/second-brain-mapping` and say 'y' to the graphify prompt.
>
> Until then: `/second-brain-mapping --metadata-only` weekly. Free. Claude's context stays current."

### When the time comes

After the vault has grown, the first graphify should be:
- Scoped to one folder (Books/ or Notes/) first, not everything
- Run as `--update` after the first full run, never full-rebuild
- Cached, canonicalized, and verified (node/edge counts match expectations)

---

## Quality checks (run after every graphify session)

1. **Node/edge count delta** matches expectation (e.g. "added 20 files, expected ~200 nodes + ~400 edges")
2. **No orphan clusters** (every new node has at least one edge to existing nodes)
3. **Wikilink gaps regenerated** (`graphify_wikilink_gaps.py`) — new high-degree entities should appear as candidates
4. **Insight engine re-run** surfaces new cross-channel findings
5. **Cache updated** — next `--update` should skip the files we just processed

---

## When the graph breaks

Symptoms → fixes:

| Symptom | Likely cause | Fix |
|---|---|---|
| Empty graph.json after run | Dispatch failed silently | Check run log at `graphify-out/graphify-run-log.jsonl` |
| Node count went DOWN | Merge corrupted cache | Restore from backup at `graphify-out/graph.json.backup_*` |
| `--update` re-extracts everything | Forgot `--cache` on canonicalize | Rerun canonicalize with `--cache`, then next update |
| `/graphify query "X"` returns nothing | graph.json missing "links" key | Load with `d.get('links', d.get('edges', []))` — networkx uses 'links', not 'edges' |
| Wildly high token burn | Skipped optimization wrappers | Always run the full pipeline in the order above |
| `manifest updated: 0 files recorded` | Staged-path resolution failure + preflight-only file gap | `graphify_stage_finish.py` was doing `VAULT / source_file` on `graphify-input/<flattened>.md` (path doesn't exist in vault). Also: files whose only coverage came from preflight wikilinks (no LLM-new canonical items) were silently skipped. Fix shipped: resolver now tries flat path first, then tries each `_` → `/` combination until a real vault file matches; manifest also unions all `.chunk_NN_files.txt` lines so every dispatched file is recorded regardless of LLM yield. |
| `MINIMAX_API_KEY not found` despite key being set | `~/.zshrc` is interactive-only; Python subprocesses never source it | Scripts launched via Claude Code Bash tool run in non-interactive shells that skip `.zshrc`. Fix shipped in `graphify_minimax_preprocess.py`: walks full fallback chain `env → ~/.zshenv → ~/.zsh_secrets → ~/.zshrc → ~/.zprofile → ~/.bashrc → ~/.bash_profile → ~/.profile → ~/.env`. Also add `[ -f "$HOME/.zsh_secrets" ] && source "$HOME/.zsh_secrets"` to your `~/.zshenv` so secrets inherit into every subprocess automatically. |

---

## Absolute rules

1. **NEVER fabricate cache data.** If cache save fails, report the failure. Do not write stub/marker/placeholder entries.
2. **Always use `graphify_stage_finish.py` for post-dispatch.** Never hand-roll merge/cache scripts.
3. **Never run concurrent operations on the cache directory.** Two graphifies at once corrupts state.
4. **The graph.json edge key is `"links"`, not `"edges"`.** `to_json()` uses networkx `node_link_data` format. Custom scripts that read `"edges"` silently return 0 edges.
5. **Every `--update` requires a preceding `--cache` on the prior canonicalize.** Otherwise you pay the full cost twice.
6. **New lessons in vault Graphify Lessons Advanced.md must be mirrored here.** When any lesson is appended to the vault runbook, add a matching row to the "When the graph breaks" table or a new absolute rule in the same session before closing. This file is the public-facing equivalent of the vault lessons file.

---

## Further reading

- `~/.claude/skills/graphify/SKILL.md` — the graphify skill's full instructions
- `~/.claude/skills/graphify/OPTIMIZATIONS.md` — the wrapper pipeline details (token savings of 80–92% with it vs without)
- `~/.claude/skills/second-brain-mapping/SKILL.md` — the orchestrator that gates graphify behind a confirm prompt
