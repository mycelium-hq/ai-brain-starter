---
type: rule
purpose: Full protocol for processing meeting notes -- discovery, source hierarchy, enrichment cascade
trigger: "I just had a meeting", "pull meeting notes", "pull the transcript", "[name] meeting is done"
---

# Meeting workflow -- "I just had a meeting" trigger

When the user says any variation of **"I just had a meeting"**, **"pull meeting notes"**, **"pull the transcript"**, **"[name] meeting is done"**, or similar, run the full meeting workflow automatically. Do NOT ask for clarification -- do the work.

## Step 1 -- Find it

Meetings produce up to three artifacts. Check for all in parallel:

1. **AI-generated transcript** (source of truth, verbatim timestamped). Check your meeting recording service (Google Meet with Gemini, Otter.ai, Fireflies, etc.) for a recent transcript. Search by meeting name, date, or participant.
2. **Meeting notes app** (Granola, Notion, or similar): check your meeting notes folder for files modified in the last 24 hours.
3. **User's in-conversation mentions**: use the meeting name/person to scope the search.

Surface every candidate. Do not pick one and ignore the others.

## Step 2 -- Move it into the vault and read it

**Source hierarchy: verbatim transcript if it exists, else processed notes. Not both.**

- **Verbatim transcript** (e.g., Gemini, Otter.ai) = timestamped, complete. Source of truth.
- **Meeting notes app** (e.g., Granola) = post-processed summary + action items + partial transcript. Useful artifact but redundant when a full transcript exists.

**How to get the content:**
1. **If a full transcript exists**: fetch it via your transcript service's API or MCP tool. Read the entire document.
2. **If no transcript exists** (in-person meetings, phone calls): read the meeting notes file fully from the vault. Exhaustive read, subagent if needed.
3. **If neither exists**: tell the user immediately. Don't invent a meeting note from chat context alone.
4. **Never skim.** If you do have to skim, say so out loud before baking anything into downstream files.

The subagent, when dispatched, must return: verbatim quotes, section-by-section feedback, every decision, every action item with owner, every number/name/source, meta-observations.

### Meeting notes app handling

Whether or not you read the meeting notes app file, it still gets:
- **Filed** in your designated meeting notes folder (verify it landed in the right folder).
- **Wikilinked** from the enriched meeting note header.
- **Left alone structurally.** The enriched meeting note (built from the transcript) is the canonical record; the notes app file is the raw artifact.

If the enriched meeting note and the notes app file are the same file, rename or merge cleanly: keep the metadata and overwrite the body with the transcript-sourced enrichment. Announce the merge.

## Step 3 -- Full meeting-day playbook (run all of it, in order)

After reading the transcript(s) fully, run the complete cascade without asking:

1. **Enrich the meeting note in place** -- TL;DR at top, decisions table, section-by-section action items, verbatim quotes (preserve original language), meta-observations. Wikilink every named person to their CRM file. Wikilink every canonical doc the meeting touches.
2. **Cascade to canonical docs** -- Update any strategy docs, vision docs, target lists, team rules, or other living documents that the meeting changed. After adding any new rule, run a **rule-consistency scan**: grep surrounding prose for contradictions and fix before saving.
3. **Update Decision Log** -- one entry per high-stakes decision with What / Why / Floor / Stakes / Speed, outcome and pattern blank.
4. **Update the CRM contact file** -- read 2 adjacent CRM files first to confirm the pattern. Keep any dataview blocks intact. Add a meeting notes section with an explicit wikilink to today's note. Update `last_interaction` and `next_step` in frontmatter. Never rewrite the file structure.
5. **Update to-dos -- team first, then personal** -- Business items go to your team to-do file. Personal items (journal follow-ups, writing, personal finance, logistics) go to your personal to-do file. Never duplicate. When ambiguous, default to personal.
6. **Humanizer pass** on any external-facing prose written (pitch narratives, positioning, email drafts). Run pre-flight, load voice calibration, rule-consistency scan.
7. **Verify with backlinks** -- open the CRM file. Confirm the meeting note shows under meeting notes AND in any dataview blocks. Open the personal to-do file. Confirm any team embeds render. If either is broken, something drifted from the pattern -- fix it.
8. **Report what was done** -- at the end, summarize every file changed, flag anything the user should eyeball, and state which sources were read (transcript / notes app / both) with byte counts or quote counts as evidence of completeness.
