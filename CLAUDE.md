# ai-brain-starter — Claude Instructions

## Public repo rules — NEVER HARDCODE PERSONAL CONTEXT

This is a **public repo** that strangers fork to build their own vaults. The whole point is that it must work for people who are NOT the maintainer and are NOT on her team.

**Before writing or editing ANY file in this repo, scan for and remove:**
- Personal names (the maintainer, her co-founders, her team, her advisors, her family)
- Company names she's affiliated with
- Personal vault paths (`Adelaida Notes`, `🚀 Onde Team`, emoji folders specific to her structure)
- Personal frameworks she invented (e.g. her floor framework, her panel of advisors)
- Specific cities, countries, or geographies that aren't universal
- Substack URLs and personal blog links other than what already exists in the README/SKILL.md welcome message
- Real meeting names, real decision content, real strategic context
- Anecdotes that name real people or real situations

**When you need to illustrate a pattern with an example, invent a fictional one.** Generic placeholders ("a Google Drive shared folder", "a team member", "a co-founder") are always preferred over real names. If a fictional example would be confusing without context, use a clearly-marked one (`# Example only — replace with your own`).

**Existing files that pre-date this rule may have personal references** (the README mentions "Adelaida Diaz-Roa" in the Background section as legitimate attribution; the LICENSE has her copyright; the CHANGELOG narrates the actual history of the repo's development). Don't touch those — they're load-bearing context. The rule applies to **new** content you add.

**The narrative CHANGELOG is the one place narrative context is OK** because it's a historical record of what shipped when. But even there, prefer "the maintainer" or "a team member" over names when possible.

If you catch yourself writing "this is what [name] does," stop. Rewrite it as a generic pattern. The repo is for strangers, not for the maintainer's team.

## Repo structure rules

**Before creating any new file or folder, always check what already exists:**

1. Run `ls` on the root to see top-level structure
2. Grep for the concept in `SKILL.md` — most skills (journal, insights, accountability, etc.) are embedded as **generated templates inside the main SKILL.md**, not standalone files
3. The only standalone skill folder in this repo is `meeting-todos/` — everything else lives inside `SKILL.md`

**The pattern:** `SKILL.md` contains the full setup flow that *generates* skills into the user's `~/.claude/skills/` directory at runtime. Adding a new skill means editing the right Phase inside `SKILL.md`, not creating a new folder.

## Current standalone sub-skills
- `skills/meeting-todos/SKILL.md` — extract action items from meeting notes
- `skills/patterns/SKILL.md` — Instinct Engine for pattern extraction
- `skills/graphify/SKILL.md` (+ scripts + RUNBOOK.md) — knowledge graph builder
- Everything else (journal, insights, onde-weekly, etc.) → embedded in `SKILL.md`

## Reference docs (for users, not embedded in SKILL.md)
- `docs/POWER_TOOLS.md` — catalog of every third-party skill, MCP server, Obsidian plugin this setup uses, with attribution and install commands
- `docs/MEMORY_SYSTEM.md` — typed-memory pattern for persistent cross-session knowledge
- `templates/dataview-queries.md` — reusable Dataview query library
- `templates/Decision Log.md` — template for tracking decisions over time
- `scripts/build-journal-index.py` — index builder for `/insights`-style skills
- `skills/graphify/RUNBOOK.md` — production playbook for big graphify runs
