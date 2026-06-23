# The Memory System

How to make Claude Code remember things across sessions — not just the contents of your vault, but **how you work, what you've corrected, what's load-bearing context**.

This is one of the most underrated patterns in this whole setup. CLAUDE.md is what Claude reads at the start of every session. The memory system is what Claude **writes to** when it learns something it should remember next time. Together they turn Claude from a stateless assistant into a colleague who actually accumulates context.

---

## The problem this solves

Without memory, every Claude Code session starts cold:

- You correct a mistake. Next session, Claude makes the same mistake.
- You explain that a specific teammate is your co-founder (not a direct report). Next session, Claude treats them as a generic team member.
- You discover that one of your scripts has a footgun. Next session, Claude steps on it again.
- You give nuanced feedback ("don't summarize at the end of every response, I can read the diff"). Next session, Claude summarizes.

CLAUDE.md catches the broad rules. The memory system catches the **specific accumulated knowledge** that's too narrow for CLAUDE.md but too important to keep re-learning.

---

## How it works

You create a directory at:

```
~/.claude/projects/<project-id>/memory/
```

(The `<project-id>` is the URL-encoded path of your vault — Claude Code creates this automatically the first time you run a session in a directory.)

Inside that directory, you write **one memory file per fact**, with YAML frontmatter:

```markdown
---
name: Teammate X is co-founder
description: Teammate X is co-founder, not just a team member. Works at a partner institution.
type: feedback
---

Teammate X is co-founder of the company, not just a team member. Works full-time at a partner
institution. Treat them as a peer-level decision-maker, not as a direct report.
```

Then you maintain an **index file** at `memory/MEMORY.md`:

```markdown
- [Teammate X is co-founder](feedback_teammate_x_role.md) — Co-founder, not team member
- [April 11 meeting context](project_apr11_meeting.md) — Fundraising strategy, not the main pitch meeting
- [Bilingual aliases](feedback_bilingual_aliases.md) — Spanish/English map to the same wikilink
```

`MEMORY.md` is loaded into Claude's context at session start (lines 1-200). Individual memory files are loaded on demand when their description is relevant.

---

## The 5 memory types

Use these as a discipline for what to write down. Each type has a different purpose and a different lifetime.

### 1. `user` — who you are and how you work

Information about your role, goals, responsibilities, and knowledge. Helps Claude tailor explanations to your level and frame work in terms you already understand.

**Examples:**
- "I'm a data scientist, currently focused on observability"
- "I have 10 years of Go experience but I'm new to React — frame React in terms of backend analogues"
- "I'm a non-technical founder; explain bash commands when you use them"

**When to write:** when you learn anything about the user's role, preferences, expertise level.

### 2. `feedback` — corrections and validated approaches

Guidance about how to approach work — both what to avoid and what to keep doing. **Save from corrections AND from validated wins.** If you only save corrections, Claude will avoid past mistakes but drift away from approaches you've already validated, growing overly cautious.

**Examples:**
- "Don't mock the database in tests — we got burned last quarter when mocked tests passed but the prod migration failed"
- "Stop summarizing what you just did at the end of every response, I can read the diff"
- "The single bundled PR was the right call here, splitting it would've been churn" *(validated, save it)*

**Format:** lead with the rule, then `**Why:**` (the reason — often a past incident), then `**How to apply:**` (when this kicks in). Knowing *why* lets Claude judge edge cases instead of blindly following the rule.

**When to write:** any time the user corrects an approach OR validates a non-obvious choice.

### 3. `project` — current state of ongoing work

Who's doing what, why, and by when. Project memories decay fast, so write the *why* alongside the *what* — that helps future-you judge whether the memory is still load-bearing.

**Examples:**
- "Merge freeze begins 2026-03-05 for mobile release cut. Flag any non-critical PR work scheduled after that date."
- "The auth middleware rewrite is driven by legal/compliance requirements around session token storage, not tech-debt cleanup. Scope decisions should favor compliance over ergonomics."

**Important:** convert relative dates to absolute when saving. "Thursday" → "2026-03-05". Otherwise the memory becomes uninterpretable in 2 weeks.

**When to write:** when you learn who's doing what, why, or by when — and the answer is non-obvious from the code or git history.

### 4. `reference` — pointers to external systems

Where to look for information that lives outside the project directory. Avoids re-asking "where do you track bugs?" every session.

**Examples:**
- "Pipeline bugs are tracked in the Linear project 'INGEST'"
- "grafana.internal/d/api-latency is the on-call latency dashboard. Check it when editing request-path code."
- "All marketing copy reviews happen in the #copy-review Slack channel"

**When to write:** when the user references an external system and tells you what's there.

### 5. `discovery` *(optional 5th type)* — non-obvious facts

Things you found out the hard way that shouldn't be re-learned. Bug classes, library quirks, tool gotchas, environment-specific weirdness.

**Examples:**
- "macOS iCloud demand-paging: cold reads are ~200ms/file (1000x warm). Looks exactly like a hang. Run `brctl download` first on bulk file ops."
- "NetworkX `to_json()` stores edges under the key `links`, not `edges`. Reading `edges` silently returns []."
- "Granola API `calendar_event` returns `None`, not a missing key. Use `or {}`, not `.get(key, {})`."

**When to write:** every time you debug something non-obvious where the diagnosis is the load-bearing knowledge.

---

## What NOT to put in memory

The temptation is to dump everything. Don't. Memory is precious context — every entry has a token cost on every future session start. The bar is "would re-learning this cost more time than re-loading it costs tokens?"

**Don't save:**
- **Code patterns, architecture, file paths** — these can be derived by reading the project state
- **Git history, who-changed-what** — `git log` and `git blame` are authoritative
- **Debugging solutions (the fix, not the discovery)** — the fix is in the code; the commit message has the why
- **Anything already documented in CLAUDE.md** — that file is loaded every session anyway
- **Ephemeral task state** — current to-do, in-progress work, today's plan. That belongs in TASKS.md or a plan, not memory.

**Even if the user says "save this":** if the request is "save my PR list" or "remember what we did today", push back. Ask what was *surprising* or *non-obvious* about it — that's the part worth keeping.

---

## File format

Every memory file is markdown with this frontmatter:

```markdown
---
name: Short human-readable title
description: One-line description used to decide relevance in future conversations. Be specific.
type: user | feedback | project | reference | discovery
---

Memory content goes here. For feedback and project types, structure it as:

The rule or fact in one sentence.

**Why:** The reason — often a past incident or strong preference.

**How to apply:** When this kicks in. What contexts to check it against.
```

The `description` field is critical — it's what Claude scans to decide whether to load the full memory file. Vague descriptions like "stuff about teammate X" are useless. Specific descriptions like "teammate X is co-founder, not a direct report, works at a partner institution" tell Claude exactly when to load it.

---

## File naming conventions

Use `<type>_<topic>.md` so the directory is sortable by type:

```
memory/
├── MEMORY.md                          ← index
├── user_role.md
├── user_expertise.md
├── feedback_no_summaries.md
├── feedback_database_tests.md
├── project_q2_launch.md
├── project_merge_freeze.md
├── reference_linear_project.md
├── reference_oncall_dashboard.md
├── discovery_icloud_paging.md
└── discovery_networkx_edges_key.md
```

`MEMORY.md` itself has no frontmatter — it's just an index. Each line is `- [Title](file.md) — one-line hook`. Keep entries under ~150 characters because lines after 200 are truncated when MEMORY.md is loaded into context.

---

## When to access memories

- **When memories seem relevant** based on the current task
- **When the user references prior-conversation work** ("like we did last time", "remember when we...")
- **You MUST access memory when the user explicitly asks** ("what do you remember about...", "check your notes on...")

**If the user says to ignore memory:** proceed as if MEMORY.md were empty. Don't apply remembered facts, don't cite them, don't compare against them. This is an escape hatch for when memory is wrong or stale.

---

## Memory hygiene

Memories decay — and they cost tokens on every session start. Left unchecked, MEMORY.md grows until it costs more to load than it saves.

**Hard cap: 50 entries.** Before adding a new entry, prune the oldest redundant one. If you're adding entry 51, something existing should go.

**Before adding, check:**
- Is this already in CLAUDE.md? If yes, skip — CLAUDE.md loads every session anyway; duplicating it in memory pays the cost twice.
- Is this in a rules file? Same rule — skip.
- Is this a one-time bug fix? The fix lives in the code. Skip.
- Will this still be relevant in 3 sessions? If no, skip.

**Set a quarterly habit:**
1. **Open `MEMORY.md`** and read every line.
2. **Delete what's no longer true.** Project memories especially — past launches, completed work, stale dates.
3. **Update what's drifted.** Roles change, references move, feedback evolves.
4. **Check that every linked file still exists.** Broken links waste tokens on a misleading description.
5. **Count entries.** If over 50, prune to 45. Leave room for the next quarter.

This takes ~10 minutes per quarter and is worth it. A memory file that contradicts current reality is worse than no memory at all — it actively misleads. And a bloated MEMORY.md burns thousands of tokens per session before you type a word.

---

## Memory vs CLAUDE.md vs Tasks vs Plans

There are several persistence layers in this setup. They serve different purposes:

| Layer | Lifetime | Loaded when | Best for |
|---|---|---|---|
| **CLAUDE.md** | Indefinite, broad scope | Every session start | Universal rules: tone, file structure, vault conventions, accountability rules |
| **Memory** | Indefinite, narrow scope | On-demand based on description | Specific facts: who a given teammate is, why we don't mock the DB, where Linear lives |
| **Plans** | Single conversation | When working on a multi-step implementation | Reaching alignment on approach before executing |
| **Tasks** | Single conversation or short cycle | When tracking progress through discrete steps | In-flight work for the current session |

**The key question for memory:** *will this still be useful 3 sessions from now?* If yes, memory. If only useful for the next 30 minutes, tasks or plan.

### Memory durability: memory is not the source of truth

Project-level memory (`~/.claude/projects/.../memory/`) is tied to ONE Claude account and ONE project path. If the user switches Claude accounts (personal, business, team), memories from other accounts are invisible. Memory is a convenience index for fast recall, not the canonical store.

**Rule: Never store something ONLY in memory.** Every memory should be backed by a durable file that any Claude session can read:

| What you learned | Back it up in |
|---|---|
| Personal preference or rule | Vault CLAUDE.md (Preferences section) or `rules/` files |
| Universal pattern (useful to anyone) | The repo that powers the vault setup |
| Discovery about a tool/API | The relevant runbook, rules file, or script comments |
| Project state or priority | `Current Priorities.md` or similar vault file |

When saving a memory, ask: *"If this user opens the vault from a different Claude account tomorrow, will this information be available?"* If no, also put it in a vault file.

This matters most for users who work across multiple machines, accounts, or team setups. The vault travels with them; the memory directory does not.

### The three homes: where a learning actually belongs

"Back it up in a durable file" raises the real question: *which* durable home? There are three, with different reach. Picking the wrong one is how a reusable team lesson ends up stranded where only one machine can see it.

| Home | Reach | Use it for |
|---|---|---|
| **Local agent memory** (`~/.claude/projects/<key>/memory/`, a real dir) | This machine + this Claude account ONLY. Not other accounts, not other tools (e.g. Codex), not CI, not teammates, not a retrieval runtime. | Who you are, your preferences, a quirk of THIS machine's tooling, a single repo's CI gotcha, current project state — genuinely-local facts. |
| **The team shared brain** (a git-REMOTE-backed store every account/tool/teammate clones + pulls; ingested into your retrieval runtime if you run one) | Every AI account, every tool, every teammate, CI, the runtime. | A tool-agnostic engineering / operating PRINCIPLE any teammate or any AI account would follow (a security invariant, "fix the shared source not the first consumer", "a guard's scan scope is its blind spot"). |
| **The substrate** (the repo that ships this memory system + the agent guards, activated by the installer) | Every install of the substrate — i.e. every person/tenant who runs it. | A MODEL-GENERAL agent guard (a fabrication check, a verification gate, a routing nudge) — a behavior that should hold for ANY agent, not just your team. |

**The classifier, one line:** *tool-agnostic AND a teammate or another AI account would need it → shared brain; a model-general agent guard → substrate; else → local.*

Two failure modes this prevents:

- **Team lesson trapped in local memory.** You learn a reusable engineering principle, write it to `~/.claude/.../memory/`, and it never reaches another account, Codex, your teammate, CI, or the runtime — so it can't change how the team works. A write-time guard (`hooks/warn-learning-to-tool-private-memory.py`, installed at user level) NUDGES when a learning-shaped file lands in a *real* tool-private memory dir. It never blocks — local memory is still the right home for local facts.
- **Model-general guard stuck in one person's `~/.claude`.** A guard that should protect every install lives only on the maintainer's machine. If it's model-general, it belongs in the substrate, activated by the installer and proven by a fresh-install smoke — not just `~/.claude`.

One nuance on durability vs reach: if your `~/.claude/projects/<key>/memory` dir is a SYMLINK into your vault (the installer wires this), you've solved durability ACROSS TOOLS on this machine — but a *local-only-git* vault still doesn't reach another GitHub account, CI, or a teammate. Cross-account / teammate reach needs a git-remote-backed shared brain, not just a symlink.

---

## How to actually use this

This is the workflow that compounds:

1. **Set up the directory** at `~/.claude/projects/<your-project>/memory/` with an empty `MEMORY.md`.
2. **Tell Claude about it** by adding a line to your CLAUDE.md: *"Use the memory system at `~/.claude/projects/<your-project>/memory/` to record corrections, project state, and discoveries. Read MEMORY.md at session start."*
3. **Be explicit when you correct things.** Instead of *"no, don't do it that way"*, say *"don't do it that way — save a feedback memory: [reason]"*. This makes Claude actually write the memory file instead of just acknowledging the correction.
4. **Quarterly memory hygiene.** Set a calendar reminder.

After ~20 sessions you'll notice Claude stops making the same mistakes. After ~50 sessions you'll notice it remembers nuances about how you work that you don't even remember telling it. That's the system working.
