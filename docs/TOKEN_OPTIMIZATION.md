# Token Optimization

Claude Code charges per token — and with a large vault setup, you burn tokens before you type a single word. This guide shows you where the overhead lives and how to cut it without losing capability.

---

## Where your tokens go (before you type anything)

Every message pays a fixed cost for everything loaded into context:

| Source | Typical tokens | Notes |
|--------|---------------|-------|
| CLAUDE.md (project) | 2,000–8,000 | Loaded every message |
| CLAUDE.md (global) | 1,000–4,000 | Loaded every message |
| MEMORY.md | 500–5,000 | Grows unbounded if not pruned |
| Deferred MCP tool names | 100–300 per server | Every registered server, every message |
| Skill descriptions | 50–200 per skill | Plugin skills add up fast |
| **Total overhead (typical)** | **5,000–20,000** | Per message, before your question |

On a 30-message session at 15,000 tokens/message overhead, that's **450,000 tokens burned on overhead alone**, before any actual work. On Opus at $15/M tokens, that's $6.75 in overhead per session.

---

## Fix 1: Caveman-dense Claude-facing files

CLAUDE.md, MEMORY.md, and any rules files you load are read on every single message. Every word in them has a multiplied cost. Dense caveman prose cuts 50–70% of file size with zero information loss.

**Principles:**
- Tables beat prose. A 4-column table with 8 rows holds more info than 8 paragraphs.
- One line per rule. No intro sentences, no "it's important to note that."
- Compress when you edit. Every time you touch a Claude-facing file, shorten it too.
- Target: each file under 10KB (one Read call). Split if it can't fit.

**Before:**
```
It's important to always wikilink the first occurrence of any concept in a file. You should use 
the alias syntax [[Concept|natural text]] so that the link reads naturally in context while still 
pointing to the canonical concept note. This helps keep the graph well-connected.
```

**After:**
```
Wikilink first occurrence per file. Alias syntax: [[Concept|natural text]]
```

Same rule. 90% fewer tokens. Across hundreds of sessions the savings compound into millions of tokens.

---

## Fix 2: Memory hygiene

MEMORY.md is a fast-recall index. Left unchecked it grows until it costs more to load than it saves.

**Hard rules:**
- **Cap at 50 entries.** Before adding entry 51, prune the oldest redundant one.
- **No duplicates.** If it's already in CLAUDE.md or a rules file, skip it in memory.
- **No one-time fixes.** A bug you fixed in a script doesn't belong in memory. The fix is in the code.
- **Prune quarterly.** Delete: stale project state, completed work, entries contradicted by newer rules.
- **One line per entry.** The index line should be under 150 characters. Full detail lives in the linked file.

**When to skip memory entirely:** if a fact would go in CLAUDE.md anyway (universal rule, evergreen preference), put it there directly. CLAUDE.md loads every session. Memory files load on-demand. Redundant entries pay the cost twice.

---

## Fix 3: Disable unused MCP servers

Every MCP server you register sends its full tool listing as deferred tool names on every message, even when you're not using it. A server with 20 tools costs ~200 tokens/message whether you invoke it or not.

**Audit your MCP servers:**
```bash
cat ~/.claude/projects/<project-id>/.mcp.json  # project-level
cat ~/.claude.json | jq '.mcpServers'           # user-level
```

Disable any server you haven't used in the last two weeks. For project-specific servers (a custom connector you're actively developing), keep them in the project `.mcp.json` and remove them when the project is done.

**To disable without deleting:** set `"disabled": true` in the server entry, or comment it out. In Claude Code settings, unchecked plugins still register names but don't load.

---

## Fix 4: Route cheap work to cheap models

Claude Opus is for judgment. Haiku is for everything mechanical.

| Task | Route to | Why |
|------|----------|-----|
| File moves, renaming, frontmatter edits | **Haiku** | Zero judgment needed |
| Summarizing a single doc | **Haiku** | Template task |
| Bulk tagging, classifying notes | **Haiku** | Pattern-matching, not reasoning |
| Entity extraction from transcripts | **Haiku or MiniMax** | Structured output, low ambiguity |
| Strategy, architecture, panel sessions | **Opus** | Judgment-heavy, worth the cost |
| Standard vault work, debugging | **Sonnet** | Default for most sessions |

**Claude Code model routing:** specify in settings or use the `--model` flag per session. The `opusplan` alias (if your Claude Code supports it) uses Opus for planning and Sonnet for execution — the best of both within one session.

---

## Fix 5: Use a cheap API for text grunt work

For extracting structure from raw text (meeting transcripts, PRDs, API docs), generating boilerplate, or bulk-classifying vault files, a cheap reasoning model costs 100–150x less than Opus and is sufficient for the task.

**MiniMax M2.7** (if you have access) costs ~$0.06/M tokens vs ~$15/M for Opus. A 150x gap. For entity extraction across a 500-file vault, that's $0.30 with MiniMax vs $45 with Opus.

This repo ships a `scripts/minimax.sh` helper. You need a MiniMax API key from [platform.minimax.io](https://platform.minimax.io).

Tasks to route to cheap models:
- Pre-extracting entities before a graphify run
- Summarizing a document before Claude processes it  
- Classifying or tagging a batch of notes
- Generating boilerplate drafts from a template

Tasks that stay on Opus/Sonnet:
- Judgment calls, trade-offs, strategy
- Writing in your voice
- Cross-file inference and synthesis
- Anything with ambiguity

---

## Fix 6: Compress CLAUDE.md at setup time

The template CLAUDE.md that `/setup-brain` Phase 4 generates is a starting point. Over time, as you add rules, preferences, and memory entries, it grows. Set a quarterly habit:

1. Read CLAUDE.md start to finish.
2. Convert prose paragraphs to table rows where possible.
3. Delete any rule you've never seen fire in practice.
4. Move anything already in a rules file to a one-line pointer.
5. Check: is this still true? Stale rules cost tokens and can mislead.

Target is under 8KB for the project CLAUDE.md. If you're over that, you have prose to compress.

---

## Quick-reference checklist

Run this after any major setup change:

- [ ] CLAUDE.md (project): under 8KB, tables not prose
- [ ] CLAUDE.md (global): under 4KB
- [ ] MEMORY.md: under 50 entries, no redundant entries
- [ ] MCP servers: only what you actively use is registered
- [ ] Rules files: each under 10KB
- [ ] Grunt-work tasks routed to Haiku or cheap API
- [ ] Disabled plugins removed from plugin list (not just unchecked)
