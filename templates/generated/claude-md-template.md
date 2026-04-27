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
3. **Check `⚙️ Meta/Folder Resolvers/` before creating files in key folders.** One resolver file per key folder (named for the folder it describes). Each has a decision tree. Check it before creating any note to confirm it belongs there.
4. **Humanize external-facing prose before it leaves your hands.** Any prose you write for a human audience — a client email, a LinkedIn post, a Substack draft, a pitch doc, a newsletter, an essay — gets `/humanizer` run on it before it's considered done. The skill strips the AI-isms that give you away. Don't ask, just run it. **Scope:** prose only. Skip YAML, code, tables, dashboards, runbooks, meta files, journal entries, and single-line edits. For non-trivial changes to a humanized doc, re-run on the section you touched, not the whole file. The humanizer skill was installed in Phase 0 — if it's missing, re-run `git clone https://github.com/adelaidasofia/humanizer.git ~/.claude/skills/humanizer`.

5. **Canonical Facts is source of truth for external numeric claims.** If your vault publishes externally-facing material that contains numbers (pitch deck, sales one-pager, investor memo, press release, marketing site), maintain a single `Canonical Facts.md` file under the relevant workstream folder. Every number, source, and attribution that appears in external material lives there with a tier-1 primary source, year, URL, and access date. Any downstream file that cites a number must trace back to Canonical Facts. Drift between Canonical Facts and any external asset is a stop-ship defect before the asset ships. See `for-teams/team-workflows.md` section 5 for the full pattern.
6. **Playbook-to-task wiring.** If you create or substantially rebuild a step-by-step instructions document for a contractor or team member (e.g. `Instructions for [Name] - [task].md`), you MUST in the SAME session add or update a matching task in the team to-do file that links to the playbook with a wikilink and carries owner, area, priority, and due date. A playbook without a live owning task is invisible work: the owner never sees it and never executes. Session close runs an orphan-playbook scan and blocks if any playbook modified this session is unreferenced. See `for-teams/team-workflows.md` section 6 for the full pattern.

7. **No orphan action items in source notes.** Any "Action items," "To-dos," "Next steps," or similar list inside a meeting note, class note, book note, podcast note, or transcript MUST be filed to your canonical to-do file in the SAME session. Items left in source notes never surface in any Dataview view, calendar block, or weekly review. They die where they were captured. The source note can keep the list as a record, but annotate "Filed to [your-todo-file] on YYYY-MM-DD" at the top of that section so a future reader knows the items are tracked. When a captured task is something a teammate could execute, file it under their owner field on the team to-do, not just yours. The `meeting-todos` skill installed in Phase 0 handles this for meeting transcripts; the same logic applies to any note type with an action-items section.

## Git in this vault (if git-tracked)

If this vault is under git for local snapshots:

1. **Never run `git add -A`, `git add .`, or unscoped `git status`.** Obsidian vaults grow to 10,000+ files between journals, attachments, and plugin caches (`.smart-env/`, `.obsidian/workspace*`). A full-tree git walk takes minutes of CPU and blocks every follow-up command. Always pass explicit paths: `git add "path/to/file.md" "path/to/another.md"`.
2. **Check the remote before pushing.** Run `git remote -v`. If empty, this is a local snapshot repo (rollback-only, no push). If remote exists, standard push rules apply.
3. **During session close, stage only the paths the session touched.** Session file, decision files, edited rule files, to-do edits. Not the whole tree.

## Session Protocol
1. Start: Read this file and `⚙️ Meta/Last Session.md` (auto-generated, never edit directly). Load graph reports CONDITIONALLY based on first message topic: personal/journal/writing topics — primary graph; work/business topics — work graph; cross-domain or unclear — both. If you have a graph-query MCP registered, use it for targeted lookups instead of reading the full GRAPH_REPORT.md. Run the daily AI brain update check (see below).
2. **Run the daily AI brain setup update check** — see the "Session start — daily update check" section below. Once per day, automatically check if there's an update available and, if so, summarize it in plain English and offer to install it.
3. During: Before giving strategic advice or analysis on topics where the vault graph is relevant, confirm you have read or queried the relevant graph this session. Memory and CLAUDE.md are fast-recall indexes, not substitutes for graph depth on substantive questions. If new concepts come up, create notes in the right folder. For decisions, create per-decision files in `⚙️ Meta/Decisions/`. If the session exceeds 30 back-and-forth exchanges with the original task still open, flag it: "This session is running long. Want to compress and continue, or wrap up fresh?"
4. End: Run the **session-end capture cascade** — see the "Session end — capture cascade" section below. **Write session content to a per-worktree file at `⚙️ Meta/Sessions/YYYY-MM-DDTHH-MM-{worktree}.md`** (the session-end hook creates a stub for you to fill in). **Write decisions to per-decision files at `⚙️ Meta/Decisions/YYYY-MM-DDTHH-MM-{slug}.md`**. Never write to `Last Session.md` or `Decision Log.md` directly — those are auto-generated aggregator views rebuilt from the per-worktree source files. Race-safe against concurrent worktrees: unique filenames eliminate write contention, aggregator output is deterministic from sorted input. See [adelaidasofia/ai-brain-starter#5](https://github.com/adelaidasofia/ai-brain-starter/issues/5) for the full design rationale.
