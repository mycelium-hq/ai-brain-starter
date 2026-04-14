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
4. **Humanize external-facing prose before it leaves your hands.** Any prose you write for a human audience — a client email, a LinkedIn post, a Substack draft, a pitch doc, a newsletter, an essay — gets `/humanizer` run on it before it's considered done. The skill strips the AI-isms that give you away. Don't ask, just run it. **Scope:** prose only. Skip YAML, code, tables, dashboards, runbooks, meta files, journal entries, and single-line edits. For non-trivial changes to a humanized doc, re-run on the section you touched, not the whole file. The humanizer skill was installed in Phase 0 — if it's missing, re-run `git clone https://github.com/adelaidasofia/humanizer.git ~/.claude/skills/humanizer`.

## Session Protocol
1. Start: Read this file. Don't ask what we were doing — you should already know. Also read `⚙️ Meta/Last Session.md` which is **auto-generated** by `aggregate-sessions.py` from `⚙️ Meta/Sessions/*.md` — never edit it directly.
2. **Run the daily AI brain setup update check** — see the "Session start — daily update check" section below. Once per day, automatically check if there's an update available and, if so, summarize it in plain English and offer to install it.
3. During: If new concepts come up, create notes in the right folder — but check the Vault Map first. For decisions, create per-decision files in `⚙️ Meta/Decisions/` (see End below).
4. End: Run the **session-end capture cascade** — see the "Session end — capture cascade" section below. **Write session content to a per-worktree file at `⚙️ Meta/Sessions/YYYY-MM-DDTHH-MM-{worktree}.md`** (the session-end hook creates a stub for you to fill in). **Write decisions to per-decision files at `⚙️ Meta/Decisions/YYYY-MM-DDTHH-MM-{slug}.md`**. Never write to `Last Session.md` or `Decision Log.md` directly — those are auto-generated aggregator views rebuilt from the per-worktree source files. Race-safe against concurrent worktrees: unique filenames eliminate write contention, aggregator output is deterministic from sorted input. See [adelaidasofia/ai-brain-starter#5](https://github.com/adelaidasofia/ai-brain-starter/issues/5) for the full design rationale.
