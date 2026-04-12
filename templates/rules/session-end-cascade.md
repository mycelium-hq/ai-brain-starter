---
creationDate: {{DATE}}
type: rule
purpose: Full protocol for capturing all session context before ending
trigger: User signals session end (bye, thanks, wrapping up, done, good night, ttyl, etc.) or /wrap-up
---

# Session end — capture cascade (don't lose context)

When the user signals the session is ending, run this capture cascade **before** saying goodbye. The point: **nothing useful from the conversation gets lost.** Every personal insight, every team decision, every workflow improvement gets written to the right place in the right vault.

## Closing signals to listen for

Fire the cascade automatically when the user says any natural close:

- "ok bye" / "thanks, that's all" / "we're done" / "I'm done"
- "good night" / "talk later" / "catch you tomorrow"
- "let's stop here" / "wrapping up" / "that's enough for today"
- "ttyl" / "later" / "cya"
- Or any equivalent phrase in their primary language

The user can also trigger it manually with `/wrap-up`.

**Skip the cascade if the session was tiny** — fewer than 5 user messages, or under ~1000 tokens of substantive conversation, or "just chatted" with no decisions, no information, no learnings. Don't make a 5-minute closing ceremony out of a 30-second hello-goodbye.

## The cascade — run all of it, in order

### Step 1 — Scan the conversation

Look back through the session and identify everything worth preserving. Categorize each item into one of these buckets:

- **Decisions** — anything they decided during the session, even small ones
- **Personal context** — feelings, goals, life events, relationships
- **Team / business context** — strategic decisions, customer info, sales pipeline updates, roadmap changes
- **New facts** — things they told you about people, projects, tools, places
- **Workflow learnings** — patterns that worked well, friction points, edge cases
- **Ideas** — things to write about, things to build, things to explore later
- **Improvements to the AI brain setup itself** — friction, missing features, bugs

### Step 2 — Decide where each item goes

| Type | Destination |
|---|---|
| **Personal** (feelings, life, relationships, goals) | Personal vault: `⚙️ Meta/Sessions/YYYY-MM-DDTHH-MM-{worktree}.md` (always); `⚙️ Meta/Decisions/YYYY-MM-DDTHH-MM-{slug}.md` if a decision |
| **Team / business** (work, strategy, customers) | Team vault if one exists: same per-worktree pattern |
| **Improvements to the AI brain setup** | File a GitHub issue (see Step 4) |
| **Anything ambiguous** | Personal vault session file with a note flagging it for review |

**Per-worktree writes (race-safety).** Write to `⚙️ Meta/Sessions/{timestamp}-{worktree}.md` and `⚙️ Meta/Decisions/{timestamp}-{slug}.md`, never to `Last Session.md` or `Decision Log.md` directly. Decisions need frontmatter `type: decision, worktree, decision_date, floor, stakes, speed, outcome, pattern`. The session-end hook runs the aggregators automatically.

**For users with both a personal vault AND a team vault:** always cascade to BOTH. Personal stuff goes to the personal vault, team stuff goes to the team vault. Never let personal stuff leak into the team vault. When ambiguous, default to personal.

### Step 3 — Write to the vault(s)

Use the file paths in CLAUDE.md's vault map. Don't ask the user where things go — figure it out from the existing structure.

For each write:
- **Don't overwrite**, append. Use markdown headings to keep entries chronological.
- **Use the date format** the rest of the file uses.
- **Include enough context** that the entry makes sense in 6 months.
- **Wikilink** people, projects, and concepts.

### Step 4 — File improvement ideas as GitHub issues

For anything in the "Improvements to the AI brain setup" bucket, **draft a GitHub issue and offer to file it.**

**Draft format:**

```markdown
**What happened:** [one-line description]

**Context:** [what we were doing — 2-3 sentences]

**Suggested fix:** [if you have one]

**Reported by:** [user's name from CLAUDE.md]
**Session:** [today's date]
```

Show the draft and ask: *"I want to send this to the maintainer so they can fix it for everyone. Want me to file it?"*

If yes: `gh issue create --repo <MAINTAINER_REPO or adelaidasofia/ai-brain-starter> --title "..." --body "..."`

If no: save to `<vault>/💡 Improvement Ideas.md`.

### Step 5 — Run the aggregators

```bash
VAULT_ROOT="<absolute vault path>" python3 "<vault>/⚙️ Meta/scripts/aggregate-sessions.py"
VAULT_ROOT="<absolute vault path>" python3 "<vault>/⚙️ Meta/scripts/aggregate-decisions.py"
```

Only needed if you wrote files after the session-end hook fired.

### Step 6 — Confirm with the user

In plain language, tell them what was saved and where. Then say goodbye in their primary language.

## What NOT to do

- **Don't ask the user what to save.** Scan the conversation, decide, and do it.
- **Don't make it long.** ~30 seconds of work, 1-3 short messages.
- **Don't write to the team vault if it's personal content.**
- **Don't file empty or trivial GitHub issues.**
- **Don't fail silently.** If something breaks, TELL THE USER.

## Why this rule matters

Without this rule, every session ends with valuable context evaporating. The cascade is the safety net.
