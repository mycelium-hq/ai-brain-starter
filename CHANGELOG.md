---
name: changelog
description: What's new in AI Brain Starter — plain English, no jargon
---

# What's new

*Every time you update (`git pull` or tell Claude "update the ai-brain-starter skill"), check here to see what changed and why.*

---

## 2026-04-16 (late p.m.) -- Session close protocol: no more stubs, 7-day retention, compressed rule

**The problem:** the session-end-hook created a "stub" session file every time the hook fired, expecting Claude to fill it in. In practice most sessions end without running the full protocol (short sessions, abrupt exits, worktree subagents, compactions), so stubs piled up unused. One user had 966 of 1,046 files as empty stubs -- 92% noise, 4.2 MB of clutter in the `⚙️ Meta/Sessions/` folder.

**What changed:**

**`scripts/session-end-hook.sh`** (rewritten):
- No longer creates stub files. Claude writes the real session file directly during session close (Phase 2 of the protocol).
- Added retention cleanup on every hook invocation: stubs older than 7 days are deleted, substantive files older than 7 days are archived to `Sessions/Archive/`. Fast and idempotent -- only touches files past the cutoff.
- Cross-platform date math (BSD `date -v-7d` on macOS, GNU `date -d '7 days ago'` on Linux).
- Step 4 prompt trimmed: points Claude at the session-close rule file instead of restating the entire protocol inline in a JSON blob.

**`templates/rules/session-end-cascade.md`** (rewritten, same filename for install compatibility):
- Went from 7 lanes / 192 lines to 4 phases / 84 lines. No information lost -- just compressed per the "caveman prose" rule (machine instructions, not human-facing).
- Phase 0: run `date` once, reuse the timestamp everywhere (session file, time tracking, to-do dates).
- Phase 1: single-pass conversation scan fills all output buckets in memory before writing anything.
- Phase 2: batch writes in parallel, aggregators run in background.
- Phase 3: conditional change-impact audit and repo propagation.

**`phases/phase-05-context-layer.md`**: the inline hook template embedded in the phase doc was updated to match the new scripts/ version (no stubs, retention cleanup, compressed Step 4 prompt).

**`phases/phase-04-claude-md.md`**: the CLAUDE.md session-end section was updated from "7-lane capture cascade" to "4-phase session close protocol" to match the new rule file.

**Why this matters for you:**
- Your `⚙️ Meta/Sessions/` folder will stop filling up with empty placeholders.
- The folder self-cleans: anything older than 7 days either goes away (stubs) or moves to `Archive/` (substantive). You get a week of rolling context, nothing more.
- Session close runs faster (single-pass scan, parallel writes, background aggregators).

**Upgrade notes:**
- If you already have hundreds of stub files, delete them: `grep -rl 'session_label: "update pending"' "$VAULT/⚙️ Meta/Sessions/" | xargs rm` (one user went from 1,046 files / 4.2 MB to 83 files / 476 KB).
- The new hook is backward-compatible with existing substantive session files; they'll sit untouched until they pass the 7-day cutoff, then move to `Archive/`.

---

## 2026-04-16 (p.m.) -- Removed claude-mem from bundled stack (security)

Dropped claude-mem from the default install after a security audit surfaced: (1) unauthenticated local HTTP API on port 37777; (2) arbitrary file-read via the `smart_unfold` / `smart_outline` MCP tools; (3) API keys stored plaintext at `~/.supermemory-claude/credentials.json`; (4) a `UserPromptSubmit` hook injecting content into every session (persistent prompt-injection surface); (5) deprecated `glob@11.1.0` transitive dep flagged for ReDoS; (6) PreToolUse:Read hook truncating Read output to line 1 (we had shipped a local patch around this).

Fresh installs no longer register the `thedotmack` marketplace, enable `claude-mem@thedotmack`, install `bun` as a claude-mem runtime, or run `npx claude-mem install`. Existing installs that already had it are NOT auto-uninstalled (bootstrap is additive). To remove manually: `claude plugin uninstall claude-mem@thedotmack` + drop the `thedotmack` entry from `extraKnownMarketplaces` in `~/.claude/settings.json`.

What replaces it for most users: the auto-memory system at `~/.claude/projects/.../memory/` (typed markdown files, durable, human-readable) plus graphify for cross-session knowledge. That combo covers `mem-search` / `knowledge-agent` use cases without the attack surface. For AST-aware code search (the one unique capability), install `ast-grep` as a standalone CLI if a specific project needs it.

Removed from: bootstrap.sh, bootstrap.ps1 (if present), README.md, docs/POWER_TOOLS.md, phases/phase-00-install.md, phases/phase-01-welcome.md, phases/phase-06-09-tools-templates.md, scripts/patch-claude-mem-read-hook.sh (deleted).

---

## 2026-04-16 (p.m.) -- Removed notebooklm from bundled stack

Dropped the notebooklm skill from the default install. Not part of the daily workflow for most users; the overhead (Chromium browser automation, Google auth dance, first-run setup) wasn't paying off. If you want it, clone directly: `git clone https://github.com/PleasePrompto/notebooklm-skill.git ~/.claude/skills/notebooklm`. Existing installs are untouched (bootstrap never overwrites the folder).

Removed from: bootstrap.sh, bootstrap.ps1, README.md, docs/POWER_TOOLS.md, phases/phase-00-install.md, phases/phase-06-09-tools-templates.md, scripts/vault-repo-drift-check.sh, skills/notebooklm/.

---

## 2026-04-16 (p.m.) -- Session close rule: compressed + restructured

**templates/rules/session-end-cascade.md** (rewrite, 191 → 85 lines):
- Renamed "11-lane capture cascade" to "Session close protocol" and restructured into Phase 0 (single timestamp) / Phase 1 (single-pass scan with output buckets) / Phase 2 (batch writes) / Phase 3 (verify + propagate). Same semantics, dense caveman prose.
- Added explicit "Report zeros, never skip silently" directive and a templated summary format so every session ends with the same shape.
- Backgrounded both aggregators in Phase 2 (parallel `&`) for faster wall time.
- Added Phase 0 timestamp discipline: one `date` call per session, reuse everywhere.
- Added 7-day retention policy (session files archived or stubbed, prevents unbounded growth).
- Kept the `gh issue create` heredoc under Phase 3 so end users have the actual command, using `<owner/repo>` placeholder.
- Tightened skip condition: <5 user messages with no decisions/info/learnings.

## 2026-04-16 (p.m.) -- Hookify template README: correct upstream URL

**templates/hookify-rules/README.md**:
- Fixed two links that pointed to `github.com/anthropics/claude-code/tree/main/plugins/hookify`. The hookify plugin actually lives in a separate repo: `github.com/anthropics/claude-plugins-official/tree/main/plugins/hookify`. Both references updated.
- Discovered while filing an upstream PR to fix a CLAUDE_PLUGIN_ROOT fallback bug in hookify itself: [anthropics/claude-plugins-official#1441](https://github.com/anthropics/claude-plugins-official/pull/1441).

## 2026-04-16 (p.m.) -- Claude Performance Self-Improvement System

**scripts/claude_performance_digest.py** (new):
- Weekly digest script that reads Claude Code JSONL session data from ~/.claude/projects/ and computes six effectiveness metrics: activity distribution (Coding/Exploration/Debugging/Delegation/Planning/Conversation), one-shot edit rate, agent spawn analysis, model mix (Opus/Sonnet/Haiku), per-project allocation, and hookify firings.
- Six diagnostic rules with configurable thresholds. When triggered, writes prescriptive to-dos to "Claude To-dos.md" for investigation items, and for four specific rule types (VERBOSE AGENTS, MODEL ROUTING, LOW ONE-SHOT RATE, EXPLORATION OVERHEAD) writes permanent behavioral rules to ~/.claude/CLAUDE.md so future sessions read them at start.
- Stdlib only, stream-parses JSONL, idempotent to-do appending. Self-locates via __file__. Configurable PROJECT_LABELS dict for clean display labels.
- Usage: python3 scripts/claude_performance_digest.py [--days N] [--dry-run] [--no-report]

## 2026-04-16 -- Plugin hook fix + graphify encoding hardening (Lessons #95-99)

**scripts/fix-plugin-hooks.sh** (new):
- Claude Code does not reliably expand `${CLAUDE_PLUGIN_ROOT}` in plugin hooks.json. When the variable is unset, hook commands resolve to a nonexistent path, error, and Claude Code defaults to BLOCK for PreToolUse -- silently denying all Write/Edit operations. Run this script after any plugin install to replace all `${CLAUDE_PLUGIN_ROOT}` references with absolute paths. Safe to re-run.

**graphify_stage_finish.py** -- encoding hardening (Lesson #98):
- All `write_text()` calls now use `encoding="utf-8"`. Without it, emoji characters in node labels (e.g. folder names like `📋 Strategy`) can be silently mangled on some systems. Affected calls: raw JSON, canon JSON, graph.json (already had `ensure_ascii=False`, now also has explicit encoding), GRAPH_REPORT.md, and extraction_manifest.json.

**graphify_stage_select.py** -- SKIP_PARTS expanded (Lesson #89):
- Added `⚙️ Meta` and `🗄 Archive` to the skip set. Without these, vault meta folders (templates, GRAPH_REPORT.md, runbook files) would appear as eligible extraction candidates, inflating file counts and wasting LLM tokens.

**What NOT to do (Lesson #99)**:
- Never write `graph.json` directly from a NetworkX object (`nx.node_link_data()`). The `hyperedges` key lives outside the NetworkX model and is silently dropped. Always use `graphify_stage_finish.py --num-chunks 0` for recluster/report-only runs -- it reads `merged_graph` as a dict and preserves hyperedges through the full pipeline.

---

## 2026-04-16 -- Graphify pipeline hardening: layout auto-detect, mtime manifest, dual-SHA, cache pruner

Four improvements to the graphify staged-rollout scripts, plus a new utility:

**graphify_stage_select.py** (rewrite):
- Layout auto-detect (Lesson #87): detects personal vs. multi-vault (team) layout at startup. Personal vault keeps cache + chunks under graphify-out/. Team layout splits cache at vault root, chunks under corpus subfolder. Prints layout name for clarity.
- SKIP_PARTS filter (Lesson #89): excludes Archive/, _review_alternate_drafts/, and iCloud/GDrive conflict copies ("foo 2.md") from file listing. Prevents non-content files from entering the extraction pipeline.
- Mtime-manifest short-circuit (Lesson #93): reads extraction_manifest.json and skips files whose mtime is within 5 seconds of their last LLM extraction. Falls back to SHA check when the manifest doesn't cover a file. Cuts re-run times dramatically on large vaults.
- Dual-SHA cache lookup (Lesson #94): tries both relative-to-vault and absolute path variants when checking the SHA cache. The graphify library uses relative paths internally, older scripts used absolute. This prevents false cache misses after upgrades.
- Now accepts multiple corpus folders in a single run and supports --max-files-per-chunk (default 45) to prevent schema collapse on large batches.

**graphify_stage_finish.py** (rewrite):
- Layout auto-detect with --corpus-folder and --cache-dir args. Auto-detects corpus folder by scanning vault children. Uses detected base path for raw/canon output, graph path, and report path.
- Manifest writer (Lesson #93): after cache save, writes extraction_manifest.json with per-file entries (llm_time, sha, node_count, stage). This is the write side of the mtime short-circuit that select.py reads.
- Fixed cache_dir in Step 5b to use args.cache_dir instead of hardcoded path.
- Added import hashlib (required for manifest SHA computation).

**graphify_prune_stale_cache.py** (new):
- Deletes cache entries whose SHA256 key no longer matches any current file. Run monthly or after vault restructuring. Honors the same SKIP_PARTS and dual-SHA logic as select.py.

**patch-claude-mem-read-hook.sh** (new):
- Disables the claude-mem PreToolUse:Read hook that replaces file content with a one-line summary. Idempotent, creates timestamped backup before patching. Run after any claude-mem plugin update.

---

## 2026-04-16 -- Bug fixes: pip, graph edge key, directed graphs, and skill guardrails

Porting improvements that surfaced from production use:

**graphify/SKILL.md** -- Three fixes:
- `pip install` changed to `"$PYTHON" -m pip install` (with bare-pip fallback). Prevents the case where the system `pip` installs to a different Python than the one graphify actually runs under, causing "module not found" on first run.
- Added `--directed` flag to the usage table. Builds a `DiGraph` that preserves edge direction (source to target) instead of the default undirected `Graph`. Useful for code dependency graphs, citation networks, or any corpus where direction matters.
- Added `--whisper-model` flag to the usage table. Lets you pass a larger model (`small`, `medium`, `large`) when transcribing audio/video files for higher accuracy at the cost of speed.

**meeting-todos/SKILL.md** -- Added guardrail to the description: "Do NOT use for general task management, journaling, or pulling full meeting transcripts (use the meeting workflow for that)." Prevents Claude from triggering this skill when someone asks to journal or pull a full transcript.

**patterns/SKILL.md** -- Added guardrail: "Do NOT use for weekly/monthly journal reviews (use insights), daily journaling (use daily-journal), or one-off decisions (use deconstruct)." Clarifies the skill's scope so Claude routes correctly instead of running `/patterns` on a prompt that belongs in `/journal` or `/weekly`.

---

## 2026-04-15 -- To-do system template

New template: `templates/generated/todo-system-template.md`. A complete prioritized task management system for Obsidian with Dataview integration.

**What it includes:**
- **Main to-do file** with P1/P2/P3 priority tiers, Dataview inline fields (`[area::]`, `[priority::]`, `[due::]`), and a Done Archive section
- **This Week view** that auto-pulls all P1 items via Dataview (never needs manual refresh)
- **Waiting On tracker** with sections for delegations, external blockers, and "blocked on self" items
- **Team variant** with per-person views, `[owner::]` field, and sprint progress queries

**System rules baked in:**
- Lint rule: every task must have `[area::]` and `[priority::]` or Claude adds them on contact
- Stale item decay: open items older than 14 days with no due date get flagged during weekly reviews
- Overdue rule: past-due items auto-surface and must be re-dated or dropped
- Priority assignment framework: three questions (hard deadline? someone blocked? moves top goal?)

**Integration:** Added as a conditional folder in Phase 2-3 (only created if the user wants in-vault task management). Personal to-do Dataview queries added to the query library.

Born from the maintainer's own vault restructure: the "organize by when I thought of it" pattern always decays into a mess. Priority tiers with inline fields and auto-refreshing views don't.

---

## 2026-04-15 -- Graph query MCP + conditional graph loading + Minimax routing + session length flag

Four optimizations for high-volume, multi-account Claude setups:

**Graph query MCP** (`scripts/mcps/graph-query-server.py`): FastMCP server that loads your vault graph (NetworkX node-link JSON) at startup and exposes surgical tools: `search_nodes`, `get_neighbors`, `find_path`, `query_subgraph`, `get_community_members`. Replaces reading the full GRAPH_REPORT.md (~3K tokens) every time you ask a question. Load graph once, query it many times. Supports two vaults via `scope` param ('primary'/'secondary'). Requires two env vars: `GRAPH_JSON_PATH` and `SECOND_GRAPH_JSON_PATH`. Install via `fastmcp` (pip) and add to `.mcp.json`.

**Conditional graph loading** (`templates/generated/claude-md-template.md`): Session Protocol step 1 changed from "always load both graphs" to "load only when the first message is topic-relevant." Keyword hook (`graph-context-hook.sh`) catches natural-language queries (not just exact nouns) so casual questions like "what's my pattern with money?" or "my pitch needs work" trigger graph loading automatically. Saves 6K+ tokens on sessions that don't touch the graph.

**Explicit Minimax routing list** (`templates/rules/efficiency.md`, rule 28): Five operation types always route to the cheap model without asking: (a) structured extraction from raw text, (b) bulk tagging/classifying, (c) boilerplate from template, (d) single-doc summary under 5K tokens with no voice requirement, (e) pre-extraction for graphify/weekly/insights pipelines. Removes the hesitation loop where Claude second-guesses whether to route.

**Session length flag** (`templates/rules/efficiency.md`, rule 29): At 30 exchanges, surface a reminder to run `/compact`. Long sessions degrade in the back half. Early compaction keeps the context clean.

---



## 2026-04-14 -- Advisory panel: Colombia localization section + named-only rule

Two additions to the advisory panel template:

- **New "Colombia: Life & Business" section** with 8 named, integrity-verified voices covering corporate culture (Carlos Raul Yepes), brand building (Catalina Escobar), cultural identity (Hector Abad Faciolince), business law (Francisco Reyes Villamizar), women in business (Sylvia Escovar), relationships/gender (Florence Thomas), bicultural identity (Patricia Engel), and holistic wellness (Dr. Jorge Carvajal Posada). Every person was researched for integrity before inclusion.
- **Rule #8: Named panelists only.** Claude must never invent archetypes or unnamed experts. Every panel voice must be a named person from the roster. If none fit, say so and offer to add one. Prevents fabricated "a hospitality GM" or "a marketplace founder" style voices.

## 2026-04-14 -- Doc compression rule + memory durability enforcement

Two new efficiency rules that make the whole setup more reliable:

- **Rule #25: Compress all Claude-facing docs.** Every file Claude reads (rules, runbooks, SKILL.md, CLAUDE.md, templates) must fit in a single Read call (<10k tokens). Dense prose, no filler. If a file exceeds the limit, split it. This prevents the Read tool from silently truncating important instructions.
- **Rule #26: Memory durability.** Never store something only in Claude's project memory. Memory is tied to one account on one machine. Every memory must also be written to a vault file in the same response. The vault is the source of truth across all accounts and computers.

Both rules in `templates/rules/efficiency.md`.

## 2026-04-14 -- MCP Build Runbook + 13 build lessons

New `docs/MCP_BUILD_RUNBOOK.md` — the full protocol for building MCP servers and managed agents on top of this vault setup. Distilled from a single build session that shipped 13 agents.

What's in it:
- **Optimization Pass** (mandatory before every build): kills over-engineered stacks before you write code. Saved multiple Next.js + Postgres + Railway setups that were meant for one internal user.
- **13 lessons** from real builds: symlink handling in macOS vaults, dict access safety, lazy Anthropic client pattern, datetime.utcnow() deprecation fix, financial math goes in Excel not Python/LLM, and more.
- **Self-test protocol**: every agent must pass a no-API-key self-test before it's done.
- **GitHub publishing checklist**: strip personal data, standard files, README requirements.
- **Which agents are worth publishing**: decision table for when to open-source vs keep private.

The lazy client pattern and symlink rules alone will save most people 30-60 minutes per build.

## 2026-04-14 -- ChatPRD and RescueTime MCP setup docs + RescueTime server script

Two new MCP integrations documented and ready to use:

- **ChatPRD MCP** — HTTP MCP at `https://app.chatprd.ai/mcp`. Add to your vault `.mcp.json`, authenticate once via OAuth, and Claude can create/read/search PRDs directly from Claude Code. Setup snippet in `docs/POWER_TOOLS.md`.
- **RescueTime MCP** — Custom FastMCP server at `scripts/mcps/rescuetime-server.py`. Gives Claude read access to your productivity data (pulse, top apps, category breakdown, trends). Pairs with the session-end time tracking lane so `/weekly` reviews can merge app-level data (RescueTime) with purpose-level logs (session end cascade). Setup instructions in `docs/POWER_TOOLS.md`.
- **Tool routing template updated** — added RescueTime row so the routing table is complete for anyone who sets it up.

Important: never commit your RescueTime API key or ChatPRD tokens. Keep secrets in the `env` block of your vault `.mcp.json` and make sure that file is gitignored.

---



## 2026-04-14 -- custom-sort auto-activates on install (no manual toggle needed)

- **Fix:** custom-sort plugin now writes `data.json` with `suspended: false` during Phase 2 setup. Previously the plugin installed silently disabled (Obsidian's default is `suspended: true`) and required a manual ribbon-click to activate. First-time users had no idea why their folders weren't sorting. This is now handled automatically.

---



## 2026-04-14 -- Journal organization by month + insights save path fix

- **New script: `scripts/organize-journals.py`** — organizes a flat Journals folder into month subfolders ("January 2026", "February 2026", etc.) based on the `creationDate` field in each entry's YAML frontmatter. Also moves any existing `Monthly Summaries/` and `Weekly Insights/` subfolders into their matching month folders and removes the empty parent folders. Run once to reorganize, or after any bulk import. Usage: `python3 scripts/organize-journals.py --vault-root "/path/to/vault"`.
- **Insights skill save path updated** — `/weekly` and `/monthly` reports now save directly inside the appropriate month folder (e.g. `Journals/April 2026/Apr. 7-13, 2026 Weekly.md`) instead of a separate `Weekly Insights/` or `Monthly Insights/` root subfolder. Keeps all content for a given month together in one place.

---



## 2026-04-14 -- Recursive folder sorting by most recently modified

- **New plugin: Custom File Explorer sorting** (`custom-sort` by SebastianMC). Phase 2 now installs this automatically. It sorts every folder in your vault by the most recently modified note *inside* it, recursively. This means if you edit a file deep inside a subfolder, that folder and all its parents bubble to the top of the file explorer — not just the file itself. Fixes the limitation where Obsidian's built-in sort only used the folder's own filesystem mtime (which macOS doesn't update recursively).
- **New file: `sortspec.md`** at vault root. Auto-generated during setup. Contains the `> advanced recursive modified` rule for all folders. You can customize per-folder rules here if needed.

---



## 2026-04-14 -- Optional time tracking lane in session-end cascade

- **New Lane 8 (optional): Time tracking.** If you add a "Time tracking" preference to your CLAUDE.md, Claude will auto-log what you worked on at the end of each session, categorized by type (Writing, Business, Vault, Personal, Admin, etc.). No manual tagging needed: Claude infers the category from conversation context. Pairs well with productivity APIs like RescueTime for a combined "what app" + "what purpose" view during weekly reviews. Opt-in: does nothing unless you enable it.
- Session-end cascade is now 9 lanes (was 8). Lane 9 is the former Lane 8 (change impact audit).

---



## 2026-04-14 -- Customer discovery meeting template + to-do system guidance

- **New template: `templates/meeting-prep-discovery.md`** -- A Mom Test-based customer discovery meeting prep template. Includes: 3-point agenda to send the client, role assignments (lead/relationship owner/listener), 30-question bank organized by block (their world, pain points, how they buy, competitive landscape, expansion), meeting structure with time blocks, case study outline draft, and post-meeting action items. Generic and ready to use for any B2B client meeting. Based on Rob Fitzpatrick's "The Mom Test" framework.
- **To-do system tip: external tracker callout** -- When team members use an external task tracker (Linear, Jira, Asana) for certain work (e.g., engineering), don't duplicate those tasks in the vault. Instead, add a callout in the vault to-do file noting where those tasks live. Prevents sync drift and double maintenance.

---

## 2026-04-15 -- Advisory panel: Technology & AI section

Five new panelists covering the AI/automation gap most knowledge workers have in their advisory roster:

- **Ethan Mollick** (Wharton/Co-Intelligence) — practical AI integration, what to delegate vs. own
- **Tiago Forte** (Building a Second Brain) — PKM, vault architecture, knowledge compounding
- **Andy Matuschak** (evergreen notes, tools for thought) — stress-tests whether systems actually change thinking over time
- **Andrej Karpathy** (Tesla AI, OpenAI) — technical AI sanity-checks, capability assumptions
- **Tim Ferriss** (4-Hour Workweek) — ruthless elimination, delegation, systems over heroics

Pick when: AI workflow decisions, vault/system design, automation choices, delegation triage.

---

## 2026-04-14 -- Cowork project guide + floor voice verification

- **New doc: `docs/COWORK_PROJECTS.md`** — Guide for creating project-scoped CLAUDE.md files when using Cowork projects. Includes template, architecture diagram, and tips from real usage (iterate with Cowork feedback, split tool routing, don't over-duplicate). Solves the common problem where a Cowork project scoped to a subfolder doesn't inherit root vault context.
- **Writing voice as floor verification** — New section in SKILL.md (under "Emotional floor tagging") that teaches Claude to cross-check floor assignments against writing style, not just content. Includes a voice signature table for all 16 floors and cross-floor heuristics (entry length, bilingual code-switching, body vocabulary). Template is calibrated per-user after ~100 entries.

---

## 2026-04-13 -- Naming conventions + journal integration

- **Insight report naming:** Weekly reports now use human-readable dates (e.g., "Apr. 7-13, 2026 Weekly.md") instead of ISO week numbers. Monthly uses "Apr. 2026 Monthly.md".
- **Journal / Session Captures integration:** Daily journal skill now checks the Session Captures staging file before starting the interview, surfaces accumulated seeds, and deletes them after use.
- **Journal index note:** Users with emoji folder names (e.g., "Journals" vs. "Journals") must pass `--journal-dir` and `--meta-dir` explicitly to `build-journal-index.py`, or update the defaults in the script to match their vault structure.

---

## April 13, 2026 (forty-second session -- LLM accuracy guardrails)

Five new efficiency rules that prevent Claude from guessing when a tool gives the right answer instantly:

- **Rule #10: Never count in-context.** Use `wc` for words/chars/lines. LLMs tokenize subwords, not characters, so counting by reading is architecturally unreliable.
- **Rule #11: Never do math in-context.** Use `python3 -c` or `bc` for any arithmetic. Anthropic's own docs say to verify with specialized software. There's an open bug for this (anthropics/claude-code#9421).
- **Rule #12: Verify wikilinks exist.** Check with `obsidian unresolved` or Glob before creating `[[links]]`. Never link to non-existent notes without flagging it.
- **Rule #13: Use IANA timezones.** Never hardcode UTC offsets or use ambiguous abbreviations (EST/EDT). Use `python3` with `zoneinfo` for conversions. DST differences between cities make offsets unreliable.
- **Rule #14: Check file size before reading.** Run `wc -l` first. Under 2000 lines: read whole. Over 2000: use offset/limit. Over 5000: question whether you need the whole file.

---

## April 13, 2026 (forty-first session -- always check system clock)

- **Efficiency rule #9: Always check the system clock.** Claude's internal sense of time is unreliable, and the system prompt only provides a rough date (no time). New rule: always run `date` in bash before writing any timestamp. Applies to journal entries, meeting notes, file headers, session captures, and to-do dates. Use `date "+%Y-%m-%d %I:%M %p"` for human-readable format.

---

## April 13, 2026 (fortieth session -- optimize-on-repeat + change impact audit)

Two process improvements ported from production use:

- **Efficiency rule #8: Optimize on repeat.** Expanded beyond "recurring processes get a runbook." Now: before running a repeated task, review what happened last time. After running, note what could be better and fix it immediately (update the runbook, fix the script, add a rule, file the bug). The key addition is "don't just note it and move on." Document deduplication misses, schema violations, hung steps, parallelization opportunities, caching gaps, new tools, and pattern drift.

- **Session close Lane 8: Change impact audit.** When a session modifies rules, scripts, skills, hooks, schedules, integrations, or paths, verify nothing broke before closing. Six checks: (1) paths resolve, (2) skills still trigger, (3) hooks still fire, (4) schedules still run, (5) cross-file references valid, (6) integrations connect. Catches silent breakage from renamed paths, moved files, or updated configs.

---

## April 13, 2026 (thirty-ninth session -- Session-close capture system)

- **Session close protocol:** 8-lane automatic capture at end of every session (journal seeds, writing notes, actionable content, to-dos, delegations, decisions, belief shifts, change impact audit). Nothing valuable stays trapped in chat transcripts.
- **Session Captures staging file:** template added for journal seed accumulation across sessions. Journal skill pulls from it and deletes used items.
- **Decision archive lifecycle:** active decisions in Decisions/ move to Decisions/Archive/ after Outcome + Pattern are filled in during weekly/monthly retrospectives.
- **Decision retrospective:** added to weekly/monthly insights skill (section 5b2) to close the loop on past decisions.

---

## April 13, 2026 (thirty-eighth session -- Obsidian sort order)

Phase 2 plugin installer now configures `fileSortOrder: "byModifiedTime"` in `.obsidian/app.json` during setup. Files and folders sort by most recently modified (newest first) out of the box. Uses `setdefault` so it won't overwrite if the user already set a preference.

## April 13, 2026 (thirty-seventh session -- new skill + panel automation)

Added **1 new skill** and **1 automation script**:

- **repurpose-talk** (`/repurpose-talk`) -- turns a speaking engagement into 10-30 content pieces. Extracts key insights, stories, and one-liners, then generates LinkedIn posts, short-form notes, article seeds, and a video clip plan with timestamps. Includes a 2-week posting calendar and cross-pollination checks (business angles, investor soundbites, CRM follow-ups). Supports bilingual output. Trigger: `/repurpose-talk` or "I just gave a talk."
- **panel-trigger-hook.sh** -- a UserPromptSubmit hook that detects decision language in prompts ("should I", "weighing", "torn between", "pros and cons", etc.) and injects an advisory panel reminder so Claude pulls 3-5 relevant voices with mandatory dissent. Silent passthrough on non-decision prompts. Install by adding to settings.local.json hooks. Solves the problem of advisory panels only firing when explicitly invoked -- this makes them proactive.

## April 13, 2026 (thirty-sixth session -- 5 new skills)

Added **5 skills** that were missing from the repo:

- **daily-journal** -- conversational journaling with floor detection, behavior accountability, and advisory panel dialogue. Interviews you, identifies your emotional floor, runs checks (gym, sleep, scrolling), consults 90+ advisory voices, and saves a properly formatted entry. Includes idea quarantine and to-do extraction.
- **humanizer** (v2.7.0) -- removes AI writing patterns from text using Wikipedia's 29-pattern library. Pre-flight doc-type detection, voice calibration against your own writing, Spanish/bilingual support, 4-tier ROI-ranked pattern ordering, and adaptive pass strength.
- **insights** (/weekly, /monthly) -- generates insight reports from journal entries with floor trends, life coach flags, therapist observations, 60+ panel voices, first-principles audit, skill usage snapshots, and Obsidian ecosystem checks.
- **nano-banana** -- image generation via Google Gemini 3 Pro Image. Text-to-image, editing, multi-image composition (up to 14 images), iterative refinement, and search-grounded generation.
- **notebooklm** -- query Google NotebookLM notebooks from Claude Code for source-grounded, citation-backed answers. Browser automation, library management, persistent auth.

All skills were sanitized: personal paths replaced with `[VAULT_PATH]`, names removed, personal context genericized. Panel rosters preserved (they're public figures and the framework is universal).

---

## April 13, 2026 (thirty-fifth session -- proactive compaction rule)

Added efficiency rule #7: **compact proactively at ~50% context usage.** Long sessions (graph pipelines, weekly reviews, multi-step cascades) degrade quality when context fills silently. The rule is simple: if you've done 3+ major tasks, compact before the next one. The PreCompact hook already preserves state, so compaction is safe.

---

## April 13, 2026 (thirty-fourth session -- patterns auto-detection)

The `/patterns` skill (Instinct Engine) now has **session-end auto-detection triggers** inspired by Hermes Agent's skill generation heuristics. Instead of only running when you manually invoke `/patterns`, Claude now silently evaluates four triggers at the end of every session:

1. **High tool-call friction** (5+ calls for routine work, suggesting a missing shortcut)
2. **User correction** (approach was wrong, may echo a recurring pattern worth codifying)
3. **Dead-end recovery** (backtracked before finding the right path, worth preserving)
4. **Non-trivial discovery** (undocumented finding that should become a rule)

If any trigger fires, Claude suggests running `/patterns` but never auto-runs it. You can say "yes" (full scan), "just save it" (quick capture), or "no" (skip).

---

## April 13, 2026 (thirty-third session -- vault maintenance automation)

Three additions that keep your vault clean automatically so it doesn't become a junk drawer over time:

1. **Vault maintenance script.** New `scripts/vault_maintenance.py` runs a monthly hygiene scan checking 7 categories: inbox overdue files, naming issues (too-long or lowercase-starting filenames), stray binaries outside designated folders, backup file accumulation, empty folders, oversized folders (500+ files), and graphify backup count. Writes a Markdown report to your Meta folder. Fully configurable via CLI flags.

2. **Graphify backup rotation script.** New `scripts/rotate_graphify_backups.py` keeps only the N most recent graph.json backups (default 3) and deletes the rest. Also cleans .bak files older than N days. Prevents the 50-backup pileup that can consume hundreds of MB.

3. **Inbox zero pattern.** New Rule 23 in `templates/rules/obsidian.md`: create an Inbox/ folder as a quick-capture landing zone with a 7-day max residency rule. The maintenance scan flags overdue items. Prevents notes from piling up in random folders.

4. **Maintenance docs.** New `docs/MAINTENANCE.md` with setup instructions, CLI usage, and three recommended scheduled task patterns (monthly scan, quarterly audit, weekly backup rotation) with cron expressions.

All scripts require `--vault-root` (no hardcoded paths), auto-detect emoji-prefixed Meta folders, and work in any vault.

---

## April 13, 2026 (thirty-second session -- Obsidian plugin integration + skill tracking)

Five additions that connect your vault to Obsidian's plugin ecosystem and help you understand which skills you actually use:

1. **Skill usage tracking.** New hook + script (`skill-usage-tracker.sh`) that logs every `/skill` invocation to a JSONL file. Companion report script (`skill-usage-report.py`) generates a Markdown usage report with per-skill counts, daily/weekly trends, and peak-time analysis. Add it to your `/monthly` routine to spot which skills earn their keep and which you forgot exist.

2. **Obsidian plugin integration guide.** New template `templates/rules/obsidian-plugins.md` covering three plugins that extend what Claude Code can do with your vault: Local REST API (open notes, search, run commands over HTTP), Smart Connections (semantic search that finds conceptually related notes even without shared links), and Juggl/Neo4j (visual graph exploration). Includes a search routing table so you know when to use which tool.

3. **Open-in-Obsidian rule.** Rule 22 in `templates/rules/obsidian.md`: after creating or significantly editing a file, auto-open it in Obsidian via the Local REST API so you don't have to hunt for it. Skips bulk operations.

4. **Neo4j export script.** `scripts/graph-to-neo4j.py` converts your graphify `graph.json` into Neo4j-compatible CSVs and a Cypher import script. For power users who want Cypher queries over their knowledge graph.

5. **PostToolUse Skill hook.** Added to `hooks.json` so the skill tracker fires automatically. Existing hooks unchanged.

All scripts auto-detect vault root from `$VAULT_ROOT` env var or their own file location, so they work in any vault without editing paths.

---

## April 13, 2026 (thirty-first session -- to-do system with Dataview views)

New documentation and templates for a complete to-do system that scales from solo use to small teams.

**What's new:**

- **`docs/TODO_SYSTEM.md`** -- full architecture guide for an inline-field to-do system. Covers: Dataview inline fields (`[owner::] [area::] [priority::]`), a three-question prioritization framework, view file templates (per-person, by-area, sprint progress, overdue, due-this-week, waiting-on), a "This Week" focusing lens (max 7 items, ONE Thing pattern), a Done Archive for completed tasks, and a lint rule so Claude auto-fixes missing fields. All templates are generic with placeholder names and paths.

- **`templates/dataview-queries.md`** -- added 6 to-do system queries: filter by person + priority, group by area, overdue items, due this week, waiting-on (delegated), and sprint progress. These complement the existing journal, CRM, and decision-log queries.

**How to use it:** Read `docs/TODO_SYSTEM.md`, adapt the folder paths and team member names to your vault, create the view files from the templates, and add inline fields to your existing tasks (a script approach is recommended for 100+ tasks). Add the lint rule to your CLAUDE.md so fields stay complete over time.

---

## April 13, 2026 (thirtieth session -- obsidian hygiene rules)

New file: `templates/rules/obsidian.md` -- 21 rules for wikilink hygiene, naming conventions, and import safety. Born from a vault-wide audit that found and fixed 3,548 issues across a 5,900-file vault. The four most impactful rules (discovered during the audit):

- **Never wikilink inside URLs.** Auto-linking scripts that insert `[[wikilinks]]` into URLs break both the URL and the link. 205 instances found and fixed.
- **No em dashes in filenames.** Em dashes (`---`) break Obsidian anchor links and TOC slugs. Use ` - ` instead. 46 files renamed.
- **Heading links use wikilink syntax.** Markdown anchors `[text](#slug)` silently break in Obsidian with emojis or special characters. Use `[[#Heading|display]]`.
- **No Roam artifacts.** `[[//database-path/...]]` references from Roam exports never resolve. Clean on import.

Drop this file into your vault's rules folder and reference it from your root CLAUDE.md.

---

## April 13, 2026 (twenty-ninth session -- graphify multi-vault pipeline)

Three new graphify scripts that make the knowledge graph pipeline work across multiple vaults:

1. **`graphify_stage_finish.py`** -- the end-to-end finish script that combines chunk results, canonicalizes, merges into the existing graph, reclusters, regenerates the report, and saves the cache. Now accepts `--vault-root`, `--report-title`, and `--report-path` so it works for any vault (personal, team, or project) without hardcoded paths.

2. **`graphify_canonicalize.py`** -- merges nodes that refer to the same concept but were given different IDs across files (e.g., 74 separate "Love" nodes from different journals collapse to 1). Also strips invalid file_type values agents invent and normalizes folder-prefix wikilink labels.

3. **`graphify_stage_select.py`** -- walks a corpus folder, applies filters (500-word minimum, skip AI-generated content), checks the cache for real LLM extractions vs. preflight stubs, and bin-packs the uncached files into word-balanced chunks ready for parallel dispatch.

All three auto-detect your vault root from their own script location, so they work anywhere without editing paths.

---

## April 13, 2026 (twenty-eighth session -- context optimization)

Three fixes that prevent your vault from slowing down over time:

1. **Session aggregator bug fix.** The script that builds Last Session.md had a bug where old content got duplicated on every run. Over time this could balloon the file to hundreds of KB, making it unreadable. Fixed: old content now gets stripped properly, and there's a 15KB safety cap so it can never snowball again.

2. **Smarter session-start hook.** The hook used to tell Claude to re-read your CLAUDE.md file, but it's already loaded automatically. That was wasting tokens. Now it just tells Claude to read Last Session + Current Priorities, and load rules files only when needed for the specific task.

3. **New: context-audit.py script.** Run `python3 "⚙️ Meta/scripts/context-audit.py"` to check your vault's health: file sizes, aggregator integrity, stale memories, zombie worktrees, rules completeness. All checks should show green. Run it anytime things feel slow, or add it to your /monthly routine.

---

## April 13, 2026 (twenty-seventh session -- /deconstruct first-principles skill)

New skill: `/deconstruct` strips away assumptions you don't realize you're making and rebuilds your thinking from scratch. Modeled on Aristotle's first-principles method.

**What changed:**

- **New skill: `skills/deconstruct/SKILL.md`** — a 4-phase analysis framework. Phase 1 surfaces hidden assumptions and classifies their origin (convention, imitation, precedent, fear, or unexamined default). Phase 2 finds what's true independent of all that. Phase 3 rebuilds 3 approaches from scratch. Phase 4 identifies the single high-leverage move.
- **Two modes:** Full mode (all 4 phases) for big decisions. Fast mode (Phase 1 + Phase 4 only) for daily use when auto-triggered.
- **Three auto-trigger integration points:** (1) Panel trigger for convention-following language during journaling ("best practice," "that's how it's done"). (2) Decision-log gate that auto-offers deconstruct when stakes are high. (3) Weekly retrospective audit that flags high-stakes decisions made without a first-principles check.
- **Fear-to-journal bridge:** When an assumption is classified as fear-origin, the skill explicitly flags it as an emotional problem, not an analytical one: "This isn't an analysis problem. It's a journal entry. What are you actually afraid of?"

**Why this matters:** Most thinking tools help you think better within your current frame. This one questions the frame itself. The auto-triggers mean you don't have to remember to use it; it catches convention-following and high-stakes moments automatically.

---

## April 12, 2026 (twenty-sixth session — modular CLAUDE.md + aggregator tightening)

Two problems: CLAUDE.md and Last Session.md both grew past the 10,000-token read limit, which meant Claude needed multiple reads at session start and could miss important rules.

**What changed:**

- **CLAUDE.md split into modular rule files.** Three large protocol blocks — session-start checks (~200 lines), session-end cascade (~120 lines), and meeting workflow (~55 lines) — were extracted into standalone files in `⚙️ Meta/rules/`. CLAUDE.md now has concise trigger pointers that tell Claude *when* to load each protocol and *where* to find it. The pointers explicitly say "the summary below is NOT sufficient — you MUST read the full file." This keeps CLAUDE.md under 10K tokens while preserving every detail of every protocol.
- **New rule template files** in `templates/rules/`: `session-start-checks.md` and `session-end-cascade.md` — the universal (non-personal) versions of the extracted protocols. These get installed into your vault's `⚙️ Meta/rules/` directory during setup.
- **Session aggregator tightened.** Default changed from top 3 sessions to top 2. New `--max-lines` flag (default: 60) truncates verbose session entries with a pointer to the full file in `Sessions/`. Legacy pre-split content archived to `Sessions/legacy-pre-split.md` instead of bloating the aggregated view. Result: Last Session.md dropped from ~25K tokens to ~4K tokens.
- **Old inline rule templates preserved.** The old `session-start-update-check.md` and `session-end-capture.md` templates still exist for backwards compatibility. New installs will use the modular rule files instead.

**Net result:** both mandatory session-start files now load in a single read call. No protocol details were lost — they just moved from "always loaded" to "loaded when triggered."

---

## April 11, 2026 (twenty-fifth session — graphify runbook hardening)

Hardened `skills/graphify/RUNBOOK.md` with a top-of-file STOP-READ gate, a PRE-FLIGHT CHECKLIST, two new standing rules, and four new lessons (#37–#40) — all from a real session that started with "run graphify on more of the vault" and turned into 30+ minutes of wasted work because the runbook got skimmed instead of read.

### Part 1 — The STOP-READ gate and PRE-FLIGHT CHECKLIST

The runbook now opens with a big red directive telling Claude to read the whole file in full before touching any graphify work. If the file exceeds the Read tool's 10k-token cap (which it does), Claude is instructed to chunk the read with `offset` + `limit` — never to fall back to Grep sampling or `head_limit`, because those are search tools, not reading tools, and they leave you confident you've "covered it" while missing most of the content.

Right after the gate is a 7-step **PRE-FLIGHT CHECKLIST** that catches the five most destructive antipatterns before they cost time:

1. Read this whole file
2. Check for stale graphify processes from other sessions
3. Force-warm the target folder if your vault is on a sync service (iCloud, Google Drive, OneDrive, Dropbox) — cold reads can be 1000x slower and look exactly like a hang
4. Never call `check_semantic_cache` on large corpora — re-hashing blocks for minutes
5. Prioritize concept-dense corpora (Books/Notes/Writing) over episodic ones (Journals/Daily Logs) — roughly 3x more concepts per token
6. Verify the cwd matches the target vault root
7. Run the stage-selection script to size the job before dispatching — NOT on capped slices though, see Lesson #38

### Part 2 — Two new standing rules

**Active lesson capture.** Any optimization or gotcha gets written up the moment it surfaces, not saved for end-of-session. If you wait, the specifics (exact numbers, exact error messages) degrade into vague pattern-matching and the lesson loses most of its value. Ten seconds to write now beats ten minutes of re-derivation next week.

**Validation hypotheses on every batch/dispatch doc.** Every handoff doc for a graphify batch must include a "What this run is testing" table with numbered hypotheses, quantitative predictions, measurement methods, and explicit kill criteria. This turns every stage into a live experiment for the lessons it depends on. You already pay the tokens — recording the measured result against a pre-registered prediction is free signal. Without it, lessons stay anecdotal ("cap-7 worked last time") and drift silently. With it, every stage either strengthens the lesson with N more data points or explicitly overturns it when a kill criterion triggers.

### Part 3 — Four new lessons (#37–#40)

- **#37** — Read-tool 10k cap handling: use `offset`+`limit` chunking, never Grep sampling
- **#38** — Don't run the full-corpus sizer for capped slices. Write a targeted picker that sorts by metadata (filename date, `st_size`, `st_mtime`) without reading contents, then reads only the top `cap × 1.6–2.0` candidates in a 16-thread pool for a 6–8x speedup over sequential. Includes filter-attrition math: journals lose ~70% to `<500w OR already-cached`, writing loses ~40%, so overshoot constants are corpus-specific.
- **#39** — Scan for content-level near-duplicate drafts in `Writing/` and `Drafts/` folders BEFORE chunking. `graphify_prep.py` only catches byte-identical duplicates; files that share 99% of their content but differ in formatting or wikilink conventions slip through. A single 57k-word draft triplicated across three folders costs ~430K tokens to redundantly extract. A 10-second title-similarity scan before dispatch catches it.
- **#40** — Merge discipline: normalize wikilinks + tags + whitespace before line-level comparison, then preserve every unique line in a "Recovered from earlier drafts" appendix at the bottom of the merged file. Never silent-drop content. Back up all originals to `/tmp` before overwriting or deleting anything.

### Why this matters for non-technical users

These four lessons are the difference between a `/graphify` run that costs 30 minutes and one that costs 3 hours. For someone who has never written a Python script and whose vault is on iCloud or Google Drive, the cold-read gotcha (Lesson #17) combined with the skimmed-runbook pathology (now blocked by the new top-gate) was the most common "it hung, I don't know what happened" outcome. The gate + checklist force a diagnostic path before any action, and the new lessons give Claude explicit fallbacks for the three most common failure modes.

**What you should do:** nothing. Next time you run `/graphify`, Claude will read the hardened runbook first and apply the new pre-flight checklist automatically. You'll notice faster runs and fewer "why is this hanging?" moments. If you want to see the new lessons, open `skills/graphify/RUNBOOK.md` and scroll to the "Session-start discipline and read-tool patterns" subsection (Lessons #37–#40) and the two "Standing rule" blocks at the top of "Lessons learned."

---

## April 11, 2026 (twenty-fourth session — CHANGELOG rotation)

Rotated 28 older session entries (April 8 → April 11 sessions 1–18) out of `CHANGELOG.md` and into a new `CHANGELOG_archive_2026Q1.md`. The live changelog now carries only the most recent ~5 sessions, which is what almost every post-pull update check actually needs to read.

**Why:** the live `CHANGELOG.md` had grown to 1,313 lines. Every `git pull` triggers Claude to read it and translate "what's new" into plain English for the user, so every line is a real token cost on every pull. The full release history is preserved in the archive file — nothing is lost. To read it: open `CHANGELOG_archive_2026Q1.md` next to this file.

**What you should do:** nothing. The next pull will show you this rotation entry and that's it. If you want the full history, the archive file is right next to the live one.

---

## April 11, 2026 (twenty-third session — non-technical onboarding overhaul + automatic file drift detection)

This is two things shipped together because they share the same theme: **make a non-technical user's first install (and every subsequent pull) work without them ever having to ask "why doesn't this work?"**

### Part 1 — Non-technical onboarding overhaul (14 fixes)

Audited the full first-install experience for someone who has never opened a terminal and doesn't know what Obsidian, Claude Code, Python, Node, or an API key is. Found 14 friction points where the setup assumed the user knew something they don't, or made them do a manual step that the bootstrap could just do for them. All 14 are fixed in this release.

**Auto-installs added — you no longer have to download anything yourself:**

- **Obsidian** — auto-installed by the bootstrap (Mac via `brew install --cask obsidian`, Windows via `winget install Obsidian.Obsidian`, Linux via snap → flatpak → AppImage download fallback). Previously the README mentioned Obsidian as a "prerequisite" with a one-line bullet, the bootstrap didn't touch it, and you'd hit a wall mid-setup when /setup-brain asked "do you have Obsidian?" You no longer have to think about it.
- **Claude Code itself** — auto-installed by the bootstrap via `npm install -g @anthropic-ai/claude-code`. Previously listed as a prerequisite with no install step. Now installed automatically once Node is present, on every OS.
- **winget on older Windows 10** — bootstrap.ps1 used to abort hard with "winget is required, install App Installer from the Microsoft Store and re-run." That sentence is opaque to a non-technical user. Now the bootstrap auto-downloads and installs App Installer from Microsoft's official URL (`aka.ms/getwinget`) before doing anything else, with a fallback to direct MSI installs of Python, Node, and Obsidian if winget can't be installed at all.
- **Obsidian community plugins** (Dataview, Templater, Tasks) — Phase 2 of `/setup-brain` used to walk you through ~36 manual clicks across the Obsidian Community Plugins UI to install three plugins one at a time. Now Phase 2 runs a Python helper that downloads each plugin's latest release directly from GitHub, drops it into your vault's `.obsidian/plugins/` folder, and writes `.obsidian/community-plugins.json` to enable them. Manual UI walkthrough is still there as a fallback for any plugin that fails to auto-install.

**Onboarding-flow clarity:**

- **README install section rewritten end-to-end.** Step 1 (open your terminal — with concrete instructions for Mac, Windows, Linux including the critical "PowerShell, NOT cmd.exe" warning), Step 2 (paste the install command and watch it run), Step 3 (type `claude` then `/setup-brain`). The "Prerequisites" section is gone — replaced with one line that says "all you need is a Mac, Windows, or Linux computer; the bootstrap installs everything else." Manual `git clone` install path removed since it's confusing to non-technical readers.
- **`/setup-brain` Phase 0 progress messaging.** Used to go silent for 2-3 minutes while installing tools, which makes non-technical users think the setup has frozen. Now Claude says "Setting up the tools you'll need — give me a moment" before starting, and gives a one-line `tool ready ✓` confirmation as each tool finishes.
- **`/setup-brain` Phase 1 step 6 — Obsidian question rewritten.** Used to ask "Do you have Obsidian installed? If not, go to obsidian.md and download it. I'll wait." Now detects whether Obsidian is already installed (which it always should be after the bootstrap) and skips the question. If somehow it's missing, the skill auto-installs it instead of asking.
- **Homebrew password prompt warning.** Bootstrap now prints a multi-line `⚠️ HEADS UP` block before installing Homebrew, telling you the password prompt is coming, that you won't see characters as you type, and to NOT close the window. Reduces "is this thing frozen?" anxiety.
- **`gh auth login` framing.** Previously asked you to log in to GitHub with developer-jargon defaults ("GitHub.com → HTTPS → Login with web browser"). Now framed as OPTIONAL with explicit "if you don't have a GitHub account, press Ctrl+C to skip — everything else still works." The implicit pressure to log in is gone.
- **Granola post-install authorization step.** Bootstrap registers the Granola MCP server but used to never tell you that the MCP only works AFTER you've signed into the Granola Mac/web app at least once. Now the install message says explicitly "I just wired up Granola — one more step on YOUR side: log in to the Granola app once before the connection works. Want me to walk you through it?" If you say "I don't use Granola," the bootstrap removes the dead MCP entry instead of leaving it stranded.
- **Nano-banana / Gemini API key deferred.** Phase 0 used to mention setting up nano-banana with a `GEMINI_API_KEY` env var as part of the main setup. That's a 5-minute side quest involving API jargon for a feature most users don't need on day 1. Now the install is deferred entirely — nano-banana only gets installed when you explicitly ask for image generation, and Claude walks you through the API key setup interactively at that point with concrete clicks instead of CLI commands.

### Part 2 — Automatic file drift detection (`drift-check.sh` + `drift-check.ps1`)

`update-check.sh` only knows whether you're behind on commits. It does NOT know whether files that were already installed in a prior release have since drifted from the repo's version. That happens when a previous sync only partially landed, when you hand-edit a script in your vault, when a `git stash` recovery leaves files mixed, or when a manual cherry-pick missed something. Until now the only way to find stale files was to manually ask Claude "compare everything" — which defeats the whole point of automatic updates.

**New script: `scripts/drift-check.sh` (and `drift-check.ps1` for Windows).** Runs at session start alongside `update-check.sh`, on the same once-per-day cooldown. Read-only — never modifies anything. Detects three kinds of drift:

1. **Installed skills** — files under `~/.claude/skills/<skill>/` that differ from the repo's `skills/<skill>/<rel-path>`.
2. **Vault scripts** — files under `$VAULT/⚙️ Meta/scripts/<basename>` that differ from `<starter>/scripts/<basename>`. Curated list of scripts the starter installs into vaults during /setup-brain.
3. **Vault CLAUDE.md rule blocks** — for each `templates/rules/*.md`, finds its top-level heading inside `$VAULT/CLAUDE.md` and diffs the block underneath. Tolerates trailing `---` separators (a CLAUDE.md formatting convention, not part of any rule).

**`session-start-update-check.md` rule extended with the drift-handling UX.** When drift is found, Claude walks you through it one file at a time: reads both files, shows you a `diff -u` of the changes, asks {update / skip / **skip permanently** / update all / stop}, **backs up before every single change** (no exceptions, even on "update all"), and for `vault-rule` drift, replaces only the targeted block via Edit (never the whole CLAUDE.md file). Files annotated with `note: hand-edited CONFIG block` (currently just `graph-context-hook.sh`) are never overwritten wholesale — they get cherry-pick treatment with a manual ask instead.

**Permanent ignore registry: `~/.claude/.ai-brain-starter-drift-check-ignore`.** Files like `graph-context-hook.sh` ship as a generic template in the repo and get hand-customized in your vault during /setup-brain. Drift on those files is permanent-by-design — having drift-check nag about them every session is noise. The ignore file is a plain-text per-user registry: one entry per line, supports literal paths and shell-glob patterns, `#` for comments. When you pick "skip permanently" during the walkthrough, Claude appends the file to this registry for you. If you change your mind, open the file in any text editor and delete the line. Defensive normalization (BOM, CRLF, thematic-break separators) prevents false-positive drift on benign formatting differences too.

**Why human-in-the-loop instead of auto-update:** because the drifted file might be a hand-edit you intentionally made (e.g. customizing `graph-context-hook.sh` with your vault paths and routing keywords), and an auto-replace would silently destroy your work. Backup-before-every-change is non-negotiable.

### What you do

Nothing — both parts apply automatically on the next bootstrap re-run or `git pull`. The drift check honors a once-per-day cooldown so it won't double-prompt during a single day.

If you want to verify drift detection right now: `bash ~/.claude/skills/ai-brain-starter/scripts/drift-check.sh --vault "<your vault path>" --force` (or the `.ps1` equivalent on Windows).

---

## April 11, 2026 (twenty-second session — update-check summary skips the corporate-event rule bullet)

Small tone-only change to `templates/rules/session-start-update-check.md`.

The session-start update check reads new CHANGELOG entries after a `git pull` and translates them into plain-English bullets for you. One of those bullets kept describing the corporate-event Onde suggestion rule (Phase 16 rule 15, added April 10) in persuasive language — framing the rule as a thing that "suggests it as a sales opportunity" or similar. That framing misses the point of the rule, which is opt-out, inline-disclosed on first fire, and scoped tightly to corporate events you're already planning. Describing it in promotional terms in the post-pull summary made it read like the starter was marketing at you, which is exactly what the rule is designed *not* to do.

The fix is the smallest possible: an "Opinionated skip list" in the update-check template that explicitly tells Claude to leave the corporate-event rule out of the update summary entirely. You'll discover the rule the first time it fires, with the full inline disclosure ("Onde was built by the same person who made this starter skill") right there at fire-time. That's where the honesty lives — not in a release-notes bullet two days earlier.

**Nothing changes about the rule itself.** It still auto-installs, still fires on the 12 corporate-event categories, still opts out permanently the moment you decline, still carries the inline disclosure on every fire. The only change is that future pulls won't announce it in a persuasive bullet in the update summary.

### What you do

Nothing. The template edit applies the next time the update-check runs. If you want to apply it right now without waiting for the next session start: pull the repo and the new template takes effect.

---

## April 11, 2026 (twenty-first session — concurrent-worktree race fix for session-end cascade)

### The bug this fixes

If you run multiple Claude Code sessions at the same time in different worktrees (which you'll do if you're using the parallel-worktrees workflow for different tasks), and each session follows the session-end cascade rule — they all race on `⚙️ Meta/Last Session.md` and `⚙️ Meta/Decision Log.md`. Each session reads the file, adds its entry, writes it back. Last write wins. **Earlier sessions' entries are silently clobbered.**

This isn't a bug in any one session. It's a structural race condition in the cascade rule itself. If you've been using this setup with parallel worktrees for any length of time, some of your session summaries and decisions have quietly disappeared without you knowing.

I caught it live on 2026-04-11 — four concurrent worktrees wrote to the meta files in one evening; at least two decisions and one session summary were overwritten before the fix shipped. Reported and tracked in [#5](https://github.com/adelaidasofia/ai-brain-starter/issues/5).

### What changed

**New folder structure (created automatically on update via the session-end hook):**

```
⚙️ Meta/
  Sessions/
    2026-04-11T22-30-my-worktree.md          # one file per session, unique filename
    2026-04-11T17-18-other-worktree.md
  Decisions/
    2026-04-11T22-30-daily-journal-redesign.md  # one file per decision, unique filename
    2026-04-11T22-30-per-worktree-meta-writes.md
  Last Session.md         # auto-generated from Sessions/ by aggregate-sessions.py
  Decision Log.md         # auto-generated from Decisions/ by aggregate-decisions.py
```

Concurrent worktrees write to *different files*, so there is no contention. The shared `Last Session.md` and `Decision Log.md` are rebuilt by aggregator scripts that produce deterministic output from sorted input — so even two concurrent aggregator runs write identical bytes. The race is structurally eliminated, not papered over with locks or retries.

**Two new scripts** (installed to your vault's `⚙️ Meta/scripts/`):

- `aggregate-sessions.py` — rebuilds `Last Session.md` by reading `Sessions/*.md`, sorting by filename descending, concatenating the top N (default 3). Filters out stub files (unfilled placeholders) so orphaned session-end hook writes don't pollute the view.
- `aggregate-decisions.py` — same for `Decisions/` → `Decision Log.md`, showing all decisions newest-first.

Both scripts read the vault path from `$VAULT_ROOT` so you don't need to edit them for your setup — the bootstrap sets the env var for you, and the hook passes it on every run.

**Updated `session-end-hook.sh`** — now detects your worktree name (three fallback methods: pwd parse → `.git` file read → PID-based unique fallback), writes a session stub to `Sessions/{timestamp}-{worktree}.md`, and runs the aggregator as the final step. The hook never writes to `Last Session.md` directly.

**Updated session-end capture rule** — tells Claude to write session content to a per-worktree file (not the shared view) and to create per-decision files (not append to `Decision Log.md`). Runs the aggregators after each write. The destination table in the rule was updated to reflect the new paths.

**Backwards-compatible migration.** Your existing `Last Session.md` and `Decision Log.md` are NOT touched on first run. The aggregator preserves all pre-split historical content below a `## Legacy (pre-split) historical entries` / `## Legacy (pre-split) historical decisions` header. Nothing gets deleted. You can roll back by deleting `Sessions/` and `Decisions/` and restoring from the `.bak-pre-aggregator-*` backups if anything goes wrong.

**Idempotency.** The aggregators are byte-stable across runs — three consecutive runs produce identical MD5 hashes. Safe to run as many times as you want, including concurrently.

### What you do (nothing, unless you want to)

The update auto-installs the new scripts and updates the hook. The next time you end a session, the hook will create your first entry in `Sessions/` and rebuild `Last Session.md` as the aggregator view. If you want to manually trigger a rebuild before then: `VAULT_ROOT="<your vault path>" python3 "<vault>/⚙️ Meta/scripts/aggregate-sessions.py"`.

If you've been running parallel worktrees and want to know what you may have lost, check `⚙️ Meta/Session Log.md` (the always-append log) for timestamps of ended sessions without matching entries in `Last Session.md`. That's your missing-content list.

---

## April 11, 2026 (twentieth session — daily journal panel becomes a live participant, with real pushback)

If you've been using `/journal` for a while, you've probably noticed the advisory panel at the end of each entry mostly cheers you on. Warm, supportive, agreeable. The problem: on good days that means *no real signal*, and on days when you're rationalizing something, it means the panel *helps you* rationalize it. The whole point of having an advisory panel is that it pushes back when you need it — and the old setup couldn't, because it ran after you'd already decided how the story goes.

This update restructures the journal skill so the panel works the way a real advisory board works.

### What's different

**1. The panel can now interrupt you mid-journal.** A new "Standing Rules" section in the journal skill has a trigger table — if you say hedge words ("I guess," "I don't know why"), drop a vague "I should" without a date, mention a new side idea during a hard stretch, brush past a missed habit, avoid naming a hard conversation, etc. — the relevant advisor pulls in with one sentence, in character, then hands the conversation back. You don't wait until the end for the panel's reaction.

**2. At least one panelist must dissent on every entry.** Especially on good days. Rationalizations slip through most easily on high-floor entries, and the old "1–2 sentences per advisor, keep it tight" format couldn't force disagreement. The new rule is simple: if all 3–5 panelists agree, you have not looked hard enough. Dissent is required, not optional.

**3. Panel dialogue, not parallel bullets.** Step 5 now stages an actual in-character exchange where panelists can challenge each other and you, ask you questions back, and push on what you avoided. Not a stack of isolated advisor quotes.

**4. Omission pass.** Before the panel weighs in, the skill checks: *what did the user NOT say tonight that a panelist would notice?* A commitment from yesterday that vanished. A meeting tomorrow with no prep. A person they were upset with who's suddenly absent from the entry. A body signal they skipped. If an omission exists, one panelist names it in Step 5.

**5. Strict voice separation in the saved entry.** This is the biggest long-term change. Every new journal entry now has two clearly-labeled sections separated by horizontal rules:
   - `## Journal — [your name]'s voice` — your original thought only, your words, your voice. Panel lines never appear here.
   - `## Panel dialogue (synthetic — not [your name]'s original thought)` — the AI-generated panel exchange, below a ⚠️ disclaimer.

Why this matters: when you reread your journals in 6 months or 6 years, you'll be able to tell at a glance which sentences were *you* thinking and which were AI commentary. Without this separation, the two voices bleed together and the journal archive loses its value as a record of how you actually think. This was the single biggest long-term failure mode of AI-assisted journaling and it's now structurally impossible in the generated skill.

**6. Panel dissents auto-log to a cross-context Panel Feedback Log.** If Step 5 produced a dissent or omission flag, the skill automatically appends it to your Panel Feedback Log (the same file that catches feedback from real human meetings). Patterns surface over time — if three different daily entries all got the same dissent, that's a real pattern to act on.

**7. Full advisory roster expanded.** The panel now includes more specialized voices: female-physiology experts (Stacy Sims, Lara Briden), pelvic-floor and embodiment (Carrie Pagliano, Bonnie Bainbridge Cohen), LGBTQ+ relational voices (Alexandra Solomon, queer polarity archetypes), cross-border tax and family office archetypes, and "archetype" slots (Curious Friend, Buddhist Monk, Stoic Philosopher, CBT Therapist, Existential Psychotherapist, Inner Child Therapist) for when no specific real person fits.

**8. Roster customization during setup.** When you run the setup flow, you'll now be offered the chance to customize the advisory panel — add or remove voices, swap in specific people from your own life (a mentor, a grandparent, a coach). Whatever you say gets baked into the generated skill so your daily journal uses *your* panel, not a generic one.

### Why

This came from noticing a real pattern: on two consecutive entries, the panel gave four affirming voices in a row and not a single piece of pushback. Nothing challenged the user's framing. On a day when the user rationalized a non-obvious decision, the panel agreed with the rationalization. That's not what an advisory board is for. The redesign fixes it at the structural level — dissent is required, the panel can interrupt mid-interview, the original voice is walled off from commentary, and patterns of pushback get logged across sessions so they don't evaporate.

If you're already set up, the next time you run `/journal` the skill file will still be the old version until you tell me to regenerate it. Ask: *"regenerate my daily-journal skill with the latest panel behavior"* and I'll rebuild it using the new template, preserving your existing floor framework, habit tracking, and customizations.

---

## April 11, 2026 (nineteenth session — bootstrap best practices for advanced users with custom skills + forks)

Session 18 added the basic safety guarantees. This session adds the protections specifically aimed at advanced users — people who have their own forks of bundled skills, their own custom CLAUDE.md rules, their own divergent ai-brain-starter clone, or any other heavy customization. The bar: **never silently overwrite anyone's hard work, regardless of how complex their setup is.**

### What's now protected for advanced users

Four new protection layers in both `bootstrap.sh` and `bootstrap.ps1`:

#### 1. Forked sub-skill detection

If you have your own `.git/` directory inside `~/.claude/skills/graphify/` (or `meeting-todos/`, or `patterns/`) — meaning you cloned your own customized version of one of the bundled skills — the bootstrap **detects this and skips that skill entirely.** It won't sync the upstream version over yours. You manage updates to your fork yourself.

The signal is the presence of `.git/` inside the skill folder. The bootstrap logs:

```
graphify has its own .git/ directory — detected as YOUR FORK, skipping entirely
  Your fork is preserved untouched. You manage updates to it yourself.
```

#### 2. Symlinked sub-skill detection

If `~/.claude/skills/graphify` (or another bundled skill) is a **symlink** instead of a regular folder — meaning you've pointed it at a shared location, a development checkout elsewhere, or a Dropbox/Drive path — the bootstrap detects the symlink and refuses to write through it. The target may be a shared resource you don't want surprised by this script.

```
graphify is a SYMLINK to /Users/you/code/graphify-fork — bootstrap will NOT write through it
  If you want bootstrap to update this skill, replace the symlink with a regular folder.
```

#### 3. Divergent ai-brain-starter clone detection

If your local `~/.claude/skills/ai-brain-starter` clone has commits that **aren't** on `origin/main` AND `origin/main` has commits that **aren't** on your clone (a true divergence — you've made your own commits that diverge from upstream), the bootstrap **refuses to pull** and tells you exactly how many commits diverge in each direction:

```
DIVERGENT FORK DETECTED at ~/.claude/skills/ai-brain-starter
  Your local clone has 3 commit(s) NOT on origin/main
  AND origin/main has 7 commit(s) NOT on your clone
  Refusing to pull. Your fork is preserved unchanged.
  To merge manually: cd ~/.claude/skills/ai-brain-starter && git pull --rebase
```

The bootstrap also handles two related cases more gracefully:

- **Local commits, no upstream changes** (you're ahead but not divergent): leaves your clone alone, doesn't pull
- **Behind upstream with no local commits**: stashes any uncommitted changes, then fast-forwards

#### 4. Explicit-disable preservation for `claude-mem@thedotmack`

Previously the bootstrap unconditionally set `enabledPlugins["claude-mem@thedotmack"] = True`. If an advanced user had explicitly set it to `False` (because they intentionally disabled the plugin), the bootstrap would silently re-enable it on the next run.

Now the bootstrap only sets the key if it's **absent**. If the user has it set to `False`, the bootstrap respects that choice and prints:

```
NOTE: respecting your explicit disable of claude-mem@thedotmack — leaving it off
```

### `--dry-run` mode

Both bootstrap scripts now accept a `--dry-run` flag (PowerShell: `-DryRun`) that previews **every action** the bootstrap would take, without making any changes. No files written, no installs run, no git operations performed. Just a transcript of "what would happen if you ran this for real."

```bash
bash bootstrap.sh --dry-run
```

```powershell
iex "& { $(irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1) } -DryRun"
```

The output looks like:
```
[dry-run] would: git fetch --quiet origin
[dry-run] would: git pull --quiet (fast-forward 53 commit(s))
[dry-run] would sync graphify skill from <repo> to <dest> (with backup-before-overwrite)
[dry-run] would back up: ~/.claude/settings.json → ~/.claude/settings.json.bak-2026-04-11-1530
[dry-run] would: register thedotmack marketplace + enable claude-mem@thedotmack (if not explicitly disabled)
```

This is the right way for an advanced user to inspect the bootstrap before running it on a heavily customized setup.

### Final change summary

Both scripts now end with a structured **change summary** that lists everything that happened (or would happen, in dry-run mode):

```
━━━ Change summary ━━━

  Installed (new):
    + ai-brain-starter clone

  Updated:
    ↑ ai-brain-starter clone (pulled 53 commit(s))
    ↑ graphify skill (12 new, 4 updated, 4 backed up)

  Skipped (your customizations preserved):
    ⊘ meeting-todos skill (your own fork — has .git)
    ⊘ patterns skill (symlink to /Users/you/code/patterns-fork)

  Backups created (recoverable):
    ↳ /Users/you/.claude/settings.json.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/SKILL.md.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/scripts/run.py.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/scripts/util.py.bak-2026-04-11-1530

  To restore any backup: mv <file>.bak-YYYY-MM-DD-HHMM <file>
```

After every run, the user knows exactly what changed, what was preserved, and how to undo anything they didn't expect.

### Best practices we now follow

For an installer that touches user-customized files, the relevant best practices are:

| Best practice | Status |
|---|---|
| Idempotence (re-run safe) | ✅ |
| Backup before overwrite | ✅ |
| Respect explicit user choices (e.g. disabled plugins) | ✅ |
| Detect forks of bundled components and skip them | ✅ |
| Detect symlinks before writing through | ✅ |
| Detect divergent histories before pulling | ✅ |
| `--dry-run` preview mode | ✅ |
| Final summary of every change | ✅ |
| Detailed error messages | ✅ |
| Verification block at end | ✅ |
| Custom skills outside bundled set untouched | ✅ |
| User vault never touched | ✅ |
| Recoverable from any unexpected change | ✅ |

The remaining gaps are nice-to-haves: a `--restore` mode that auto-restores from the most recent `.bak` files (not strictly needed since the file paths are obvious), atomic operations across the whole script (would require a temp directory + final swap, significant refactor), and a logging file (right now the summary is stdout only — could also write to `~/.claude/.bootstrap.log` for forensics).

### What this means for an advanced user

If you've built a heavy custom setup — your own forks of bundled skills, your own divergent ai-brain-starter, your own custom plugins, your own MCP servers, your own hand-tuned settings — running the bootstrap on top of it will:

1. **Detect everything you've customized** (forks via `.git`, symlinks via attributes, divergent clones via `git rev-list`, explicit-false plugins via JSON inspection)
2. **Skip those entirely** (not "back them up and overwrite", actually skip)
3. **Tell you in the summary exactly what was preserved and why**
4. **Update only the things that aren't customized** (and back those up too, just in case)

The bar: an advanced user with five custom forks should be able to run the bootstrap and have nothing they care about touched. The summary should confirm "5 custom things preserved, 0 things you customized were modified."

Run with `--dry-run` first if you're at all unsure. The dry run is the answer to "but what if it does something I don't expect?" — it shows you exactly what would happen with zero side effects.

---

## Older entries

For sessions 1–18 (April 8–11, 2026), see [`CHANGELOG_archive_2026Q1.md`](CHANGELOG_archive_2026Q1.md). Rotated on 2026-04-11 to keep the live changelog focused on the most recent ~5 sessions.

## [Unreleased]

### Changed
- `templates/rules/advisory-panel.md` Rule 1: confidence scoring is now internal only. Panel filters by lens-fit score (0-100) but NEVER prints the number in output. No `[confidence: N]`, no `(72)`, no score annotations. Background filter, not visible ink.
