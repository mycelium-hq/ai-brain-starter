# Migration: Compiled Truth + Timeline for CRM entries

## What changed
CRM entries now use a compiled truth + timeline pattern. New entries are created with this format automatically. Existing entries are unaffected until you migrate them.

## Why
A CRM entry that's just a list of notes forces you to scroll through history every time you need to know where things stand. The compiled truth section gives you the current state in 2-3 sentences — rewritten as things change. The timeline below it is the append-only evidence log. You get instant orientation + full history.

## How to apply to existing entries

For each person in 👤 CRM/ you interact with regularly:

1. Open their note
2. After the frontmatter `---`, write 2-3 sentences on who this person is RIGHT NOW
3. Add `**Next step:** [one specific action]`
4. Add a `---` separator
5. Add `## Timeline` heading
6. Move any existing notes or history below that heading as dated entries

**Example — before:**
```
---
type: person
relationship: investor
---
Met at NYC event. Interested in LATAM. Follow up after deck is ready.
```

**Example — after:**
```
---
type: person
relationship: investor
last_updated: 2026-04-09
---

Warm lead from NYC investor event. Interested in LATAM markets, hasn't committed. Deck feedback pending from Apr 11 meeting before next outreach.

**Next step:** Send updated deck after Apr 11 Andres meeting.

---

## Timeline

- 2026-04-09 — Met at NYC event. Expressed interest in LATAM markets.
```

You don't have to migrate all at once. Start with your top 5 active contacts.
