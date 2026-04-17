# Knowledge Graph Rules

Your vault has (or can have) a knowledge graph built with `/graphify`. It is the fastest and most accurate way to get structural context across your notes. **For multi-concept questions, start here before reading individual files.**

**ANY graphify-related question or action? MANDATORY: Read your Graphify Runbook IN FULL before doing anything else.** This includes running the pipeline, checking coverage/status, answering questions about the graph, estimating costs, or any other graphify topic. The runbook is long (typically 12-15k tokens). Chunk with `offset`+`limit` (e.g. offset=1 limit=200, then offset=200 limit=200, etc.). Every skipped lesson costs 10-60 min of wasted work.

## Graph location

Your graph lives at `graphify-out/graph.json` in your vault root. The report is at `graphify-out/GRAPH_REPORT.md`.

If you have multiple vaults (e.g. personal + team), each vault has its OWN graph and cache. Never run one vault's graphify from the other vault's root. See the Runbook's scope rules for details.

## Context-loading decision tree

| Question type | Start with | Then drill into |
|---|---|---|
| Strategic / cross-topic | GRAPH_REPORT.md | Top 3-5 source files in relevant community |
| "What connects X and Y?" | `/graphify path "X" "Y"` | Shortest-path files |
| "What's in the vault about X?" | `/graphify explain "X"` | Top-degree neighbors |
| "Find files mentioning X" | Search tool with query="X" | Matching files |
| Editing a specific file | `Read` the file directly | N/A |

## Maintenance rules

1. **Read the Runbook first.** Every time. No exceptions.
2. **Use `/graphify query` for targeted lookups** instead of reading many files.
3. **Use `/graphify path "A" "B"` for cross-concept connections.**
4. **Update after significant writing sessions.** `/graphify <path> --update`. Cache makes incremental runs cheap.
5. **Stale if god nodes/community labels don't match reality.** Re-run `/graphify --update`.
6. **When merging duplicates, update aliases.** Add old name as alias so existing wikilinks still resolve.
7. **Run wikilink gap report after each graphify session.** `python3 scripts/graphify_wikilink_gaps.py --vault-root .` — finds high-connection entities with no `[[wikilinks]]` yet. Output saved to `graphify-out/WIKILINK_GAPS.md`. Good starting point for new vaults with sparse linking.
