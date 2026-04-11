---
name: patterns
description: Instinct Engine — scans recent sessions, journals, and decisions for recurring patterns and turns them into concrete captures (CLAUDE.md rules, concept notes, writing seeds, skill improvements). Run after /weekly or whenever you sense a pattern hardening.
trigger: /patterns
---

# /patterns — Instinct Engine

You are extracting signal before it evaporates. This skill scans recent sessions and surfaces what's hardening into real insight, then proposes concrete captures.

Run this after `/weekly`, after a heavy journaling session, or whenever the user says "I keep noticing..." or "this keeps coming up."

**Headless/auto mode:** If you are running in a cron job, background script, or `--print` session with no interactive user, skip Step 3's confirmation. Auto-capture all findings. Add `(auto-captured — review and edit)` as a note in any new files created. Proceed directly to Step 4 → Step 5.

---

## Step 1: Gather recent signal (do this silently)

Read these sources in parallel:
- `[VAULT]/⚙️ Meta/Last Session.md` — what was just worked on
- `[VAULT]/⚙️ Meta/Decision Log.md` — last 10–15 entries (look for repeating decision types)
- Any content drafts or writing drafts — recent drafts (look for recurring metaphors)
- Last 7 journal entries (use journal-index.json if available, otherwise read directly)

If `/weekly` was just run, its output is already in context — use that, don't re-scan journals.

---

## Step 2: Extract patterns

Look across everything for:

**Recurring themes** — What topics, people, or tensions keep appearing? If something shows up 3+ times in different sessions, it's a pattern.

**Decision frameworks** — Are there repeating decision types where the same logic applies each time? (e.g., "When [X], I always choose [Y] because [Z]") These should become CLAUDE.md rules.

**Writing patterns** — Metaphors, phrases, or ideas that resurface across entries. Often the most original material — but invisible because it's spread across time.

**Behavioral loops** — What accountability items keep getting flagged? What does the user keep resolving and then re-encountering?

**Vault gaps** — What concepts keep appearing in notes that don't have their own concept note yet?

---

## Step 3: Surface findings

Present findings grouped by type. Be specific — quote the actual phrase or pattern. Maximum 5 proposals at a time:

> **Writing pattern:** "[exact quote]" has appeared in 3 entries and 2 drafts in the last 2 weeks.
> → Proposed: start a writing seed in `Writing/Drafts/[Title].md`

> **Decision framework:** Every time [situation], you [action]. This has happened [N] times.
> → Proposed: new CLAUDE.md rule — "[rule text]"

Ask: "Which of these do you want to capture?"

---

## Step 4: Execute confirmed captures

After the user confirms, execute all approved captures in one pass:

- **Writing seed** → create a draft in Writing/Drafts/ (or wherever drafts live) with the exact phrasing + context of where it appeared
- **CLAUDE.md rule** → add to the relevant section, sync to any other CLAUDE.md files
- **Concept note** → create in the right folder, add wikilinks
- **Skill improvement** → note it clearly: "This should be baked into [skill name] — flag for next update"

---

## Step 5: Log and close

Append to Vault Changelog.md (if it exists):
```
- [DATE] /patterns run: [N] captures made — [brief list]
```

If any universal patterns emerged (not personal, applicable to any second-brain user), flag them: "This pattern could go in ai-brain-starter — want me to note it for the next update?"
