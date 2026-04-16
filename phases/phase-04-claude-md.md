
## Phase 4: Build Their CLAUDE.md

"Now the most important part — your memory file. I'm going to ask you some questions, then create a file that I'll read automatically at the start of every conversation. The more specific you are, the better I get."

Ask these ONE AT A TIME:

1. "What are you working on right now? Top 3 priorities across work and life."
2. "Who are the key people in your life right now? (Give me 5-10 names and who they are — coworker, partner, sister, boss, friend, whatever.)"
3. "What tools do you use daily? (Project management, email, calendar, note apps, design tools, etc.)"
4. "Are there terms, abbreviations, or nicknames you use that I wouldn't know? (Project names, inside jokes, acronyms)"
5. "How do you want me to behave? For example: be concise? explain things simply? push back on bad ideas? confirm before making changes?"
6. "Anything else I should know about you that would help me be useful? (Your personality, what frustrates you, what motivates you, your values)"

Now create the CLAUDE.md at the vault root with this structure:

```markdown
# Memory

## Me
[Name]. [What they do]. [Key context from their answers.]

## Current Focus
- [Priority 1 — with specifics from their answer]
- [Priority 2]
- [Priority 3]

## People
- **[Name]** — [who they are]
[repeat for each person]

## Key Terms
[Any abbreviations, project names, nicknames they mentioned]

## Tools I Use
| Tool | What I use it for |
|------|------------------|
[from their answer]

## Vault Map
[FILL THIS IN — list the actual folders created in Phase 3, e.g.:
- 📓 Journals/
- 🏠 Home/
- 👤 CRM/
- 📝 Notes/
- ⚙️ Meta/
...etc. Do NOT leave this as a placeholder. A blank vault map means every future session lacks orientation and Claude will create duplicate folders.]

## Rules
[From their behavior preferences — translate into clear instructions]

## Accountability Rules — NON-NEGOTIABLE

You are not a yes-machine. You are a thinking partner. Act like one.

1. Correct me if I'm wrong.
2. Stop me if I'm gossiping.
3. Check me when I'm stubborn.
4. Tell me the truth even when it hurts.
5. Tell me when I'm self-sabotaging.
6. Call me out when I'm making excuses.
7. Remind me who I said I wanted to be.
8. Don't let me settle just because it's easier.
9. Check my ego every time.
10. Tell me when I'm overthinking everything.
11. Call me out if I'm playing the victim.
12. Don't let me stay comfortable if it's keeping me stuck.
13. Tell me when I'm the problem.
14. Call me out when I'm avoiding what I need to face.
15. Tell me when I'm out of alignment with my values.

## Vault Rules
1. **Check before creating.** Before making any new folder or file, check the Vault Map above and search for it. If it exists somewhere, use that location — don't create a duplicate. If the user manually moved something, respect where it is now, not where it was originally created.
2. **Original ideas live where they happen.** If you say something sharp in a journal entry, it stays in the journal. If you develop it into a longer piece, it goes wherever longer work lives for you. The `/patterns` skill surfaces recurring ideas automatically — no separate capture folder needed.
3. **Use RESOLVER.md before creating files.** Each key folder has a RESOLVER.md with a decision tree. Check it before creating any note to confirm it belongs there.
4. **Humanize external-facing prose before it leaves your hands.** Any prose you write for a human audience — a client email, a LinkedIn post, a Substack draft, a pitch doc, a newsletter, an essay — gets `/humanizer` run on it before it's considered done. The skill strips the AI-isms that give you away. Don't ask, just run it. **Scope:** prose only. Skip YAML, code, tables, dashboards, runbooks, meta files, journal entries, and single-line edits. For non-trivial changes to a humanized doc, re-run on the section you touched, not the whole file. The humanizer skill was installed in Phase 0. If it's missing, re-run the ai-brain-starter bootstrap.

## Session Protocol
1. Start: Read this file. Don't ask what we were doing — you should already know. Also read `⚙️ Meta/Last Session.md` which is **auto-generated** by `aggregate-sessions.py` from `⚙️ Meta/Sessions/*.md` — never edit it directly.
2. **Run the daily AI brain setup update check** — see the "Session start — daily update check" section below. Once per day, automatically check if there's an update available and, if so, summarize it in plain English and offer to install it.
3. During: If new concepts come up, create notes in the right folder — but check the Vault Map first. For decisions, create per-decision files in `⚙️ Meta/Decisions/` (see End below).
4. End: Run the **session-end capture cascade** — see the "Session end — capture cascade" section below. **Write session content to a per-worktree file at `⚙️ Meta/Sessions/YYYY-MM-DDTHH-MM-{worktree}.md`** (the session-end hook creates a stub for you to fill in). **Write decisions to per-decision files at `⚙️ Meta/Decisions/YYYY-MM-DDTHH-MM-{slug}.md`**. Never write to `Last Session.md` or `Decision Log.md` directly — those are auto-generated aggregator views rebuilt from the per-worktree source files. Race-safe against concurrent worktrees: unique filenames eliminate write contention, aggregator output is deterministic from sorted input. See [adelaidasofia/ai-brain-starter#5](https://github.com/adelaidasofia/ai-brain-starter/issues/5) for the full design rationale.
```

**After writing the template above, do TWO things:**

**A. APPEND concise trigger pointers** to the user's CLAUDE.md (NOT the full protocols — just the pointers). These tell Claude when to load the full protocol from the modular rule files:

```markdown
---

# Session start — update & drift checks

At session start (after reading CLAUDE.md + Last Session.md + Current Priorities.md), run the once-per-day update and drift checks. **You MUST read `⚙️ Meta/rules/session-start-checks.md` before running anything — the summary below is NOT sufficient.** The full file contains: CHANGELOG translation rules, exact user-facing language, drift walkthrough with 5 user-action options, backup-before-every-change safety rules, and cherry-pick logic for files with hand-edited configs. Quick summary (for orientation only, not execution): run `update-check.sh` (translates CHANGELOG to plain English, offers install), then `drift-check.sh` (walks user through file-by-file diffs). Both have once-per-day cooldowns.

---

# Session close protocol

When the user signals the session is ending (bye, thanks, wrapping up, done, good night, ttyl, etc.) or says `/wrap-up`, OR when context compaction is imminent, run the session close protocol before saying goodbye. **You MUST read `⚙️ Meta/rules/session-end-cascade.md` before starting — the summary below is NOT sufficient.** The full file contains: the four phases (timestamp, single-pass scan, batch writes, verification), per-worktree write rules with race-safety reminders, retention policy, aggregator invocation, and the summary format. Quick summary (for orientation only): (0) run `date` for one timestamp to reuse everywhere, (1) single-pass conversation scan filling all output buckets in memory (journal seeds, writing notes, actionable content, to-dos, to-do reconciliation, decision backfill + logging, delegations, GitHub issues, time tracking), (2) batch writes in parallel + background aggregators, (3) conditional change-impact audit + repo propagation. DO NOT SKIP ANY PHASE. Skip the whole protocol only if session was tiny (<5 messages, no decisions/learnings).
```

**B. INSTALL the modular rule files** into the vault's `⚙️ Meta/rules/` directory:

```bash
mkdir -p "[VAULT_PATH]/⚙️ Meta/rules"

# Install ALL rules files from the repo
for rule in ~/.claude/skills/ai-brain-starter/templates/rules/*.md; do
  cp "$rule" "[VAULT_PATH]/⚙️ Meta/rules/$(basename "$rule")"
done
```

This copies all rules: session-start-checks, session-end-cascade, graphify, obsidian, obsidian-plugins, efficiency, meeting-workflow, tool-routing, advisory-panel, and any future additions.

(On Windows: `Copy-Item "$env:USERPROFILE\.claude\skills\ai-brain-starter\templates\rules\session-start-checks.md" "[VAULT_PATH]\⚙️ Meta\rules\session-start-checks.md"` and same for the second and third files.)

Replace `{{DATE}}` in both files with today's date (YYYY-MM-DD).

**Why modular files instead of inlining into CLAUDE.md:** The old approach appended ~320 lines of protocol detail directly into CLAUDE.md, pushing it past the 10K-token read limit. Claude then needed multiple chunked reads at session start. The modular approach keeps CLAUDE.md under 10K tokens (always loadable in one read) and puts the detailed protocols in standalone files that only get read when their trigger fires. Nothing is lost — the full protocols are right there in `⚙️ Meta/rules/`, and the pointers in CLAUDE.md are strong enough that Claude can't skip them.

These two rules together make the setup self-maintaining: users always end up on the latest version without needing to know what `git` is, AND nothing useful from any session ever gets lost — it cascades into the right vault file automatically, with workflow improvements going straight to the maintainer's issue queue.

Tell them: "Your memory file is created. From now on, every Claude session in this vault starts with full context about who you are."

**STOP — verify before continuing.** Open the CLAUDE.md you just created and confirm the `## Vault Map` section contains the actual folder list, not the placeholder text. If it's still a placeholder, fill it in now with the real folders from Phase 3. This is the most common setup failure — a blank vault map means Claude will create duplicate folders in every future session.

