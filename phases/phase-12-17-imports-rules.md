# Phases 12-17: Imports, Taxonomy, Backup, and Obsidian Rules

**Run every phase in this file. Ask each phase's question explicitly.** Do NOT skip a phase because the user didn't mention the topic earlier — most users have no idea these features exist until you ask. Banned framings: "Skip — you didn't mention books / wearables / a framework / a backup tool." Always ask. Then skip only if their explicit answer is no.

---

## Phase 12: Import Book Notes & Highlights

**MANDATORY ASK — do NOT skip because they didn't bring up books earlier.** Ask now:

"Do you read books and highlight? (Kindle, Apple Books, Readwise, physical books with margin notes?)"

If yes, explain: "Your book highlights are some of the most valuable notes you have — they're the ideas that resonated enough to mark. Let's get them in."

Walk through each source:
- **Kindle:** "Go to read.amazon.com → Notes & Highlights → export. Or if you use Readwise, it's even easier."
- **Readwise:** "Export as markdown — Readwise has an Obsidian plugin that syncs automatically. Install it from Community Plugins."
- **Apple Books:** "This one's harder. You can copy highlights manually, or use a tool like Bookfusion to export."
- **Physical books:** "Take photos of your margin notes. I can transcribe them."
- **PDF annotations:** "Drop the PDFs in the vault. I can extract highlighted text and annotations."

After import:
- Create a `Books/` folder if it doesn't exist
- One note per book with: title, author, key highlights, personal reflections
- Add wikilinks to concepts that match existing vault notes
- "Your reading and your thinking are now connected. When you write about a topic, your book highlights surface as context."

## Phase 13: Health Data Import (devices + labs)

**MANDATORY ASK — never assume.** Do NOT skip this phase because the user didn't mention health earlier. Most people who own a wearable or have had recent lab work don't think to bring it up during a vault setup. Ask BOTH halves explicitly:

### 13a. Wearables

"Do you wear or use any of these? Apple Watch / Apple Health, Oura Ring, Fitbit, Garmin, Whoop, or any other health-tracking device or app?"

Wait for their answer. If they say yes (even to one), continue. If they say "no, none of these," move to 13b.

If yes: "We can import your health data and cross-reference it with your journal entries. Imagine asking 'what do my best weeks have in common?' and getting back: gym 4x, sleep before midnight, HRV above 40, no social media after 9pm. The habit tracking from your journal gives you the subjective data — this gives you the objective data."

Then walk through their specific source. If they have the `health-setup` skill installed (from the ai-brain-starter bundle), invoke it via the Skill tool to handle wearable wiring end-to-end. Otherwise:

- **Apple Watch / Apple Health:** Export via Apple Health app → Share → Export All Health Data. Creates a zip with XML. The `ingest-health` skill (also bundled) imports it into a local DuckDB. Three modes: XML export.zip, Simple Health Export CSV folder, Health Auto Export TCP-live.
- **Oura Ring:** Personal Access Token from cloud.ouraring.com → set `OURA_TOKEN` env var. The `health-setup` skill wires this end-to-end.
- **Fitbit / Garmin / Whoop:** each has its own auth dance. `health-setup` skill handles each one.
- **Apple Watch without export hassle:** Health Auto Export iOS app pushes live data via TCP. Walk them through it.

After import, the `health-context` skill (auto-fires on journal entries) pairs body data with Floor tags — so a "Floor: Joy" entry with "HRV 22, RHR 78, sleep 5h 12m" gets the parasympathetic-state caveat automatically.

### 13b. Lab tests + health reports

ASK regardless of the wearables answer — devices and labs are different surfaces, and someone with no wearable may still have rich annual bloodwork. Phrasing matters: don't say "medical records" (intimidating); say "lab tests or any health reports."

"Have you had any recent lab tests, bloodwork, hormone panels, or other health reports in the last year or two? PDFs, images of paper results, anything? Even one set of bloodwork is enough to start."

If they say yes: "Save the PDFs or photos in your vault under `🏠 Home/Health/Labs/` (create the folder if it doesn't exist). When you mention symptoms, energy, mood, or anything body-related in journals, I'll cross-reference. For PDF lab panels, the `parse-mcp interpret` tool extracts the structured values and writes a markdown summary next to the original. You can also just drop them in and ask me 'what's in here?' when we're back in a session."

Walk through one if they have it handy right now: "Want to drop one in now? I'll show you the flow once so you know how it works."

If they say no: "Cool. If you do bloodwork later — annual physical, perimenopause panel, fertility screen, whatever — drop the PDFs in `🏠 Home/Health/Labs/` and I'll know what to do."

If they explicitly said no to BOTH wearables and labs, skip the rest of Phase 13 silently — Phase 10's habit tracking covers the subjective side. Otherwise, the body track in journals is now wired.

## Phase 14: Build Your Concept Taxonomy

**MANDATORY ASK** — concept notes are how the vault stops being a filing cabinet. Always run this phase.

Ask: "Do you have a framework you think about life through? (Values, principles, categories, a personal philosophy?) Or do you want to build one from the themes already in your writing?"

Not everyone has a framework like the High-Rise. But everyone has recurring themes. Help them identify theirs:

"Let me scan what you've already written — journals, notes, whatever's in the vault — and pull out the themes that keep coming up."

Scan for recurring concepts across their notes. Report the top 15-20 themes.

Then ask: "These are the ideas your brain keeps returning to. Want me to create a concept note for each one? Each note becomes a hub — everything you've ever written about that topic links through it."

For each concept note:
```markdown
---
creationDate: [today]
type: concept
---

[Brief description of what this concept means to them]

## Connected
[[Related Concept 1]] | [[Related Concept 2]] | [[Related Concept 3]]

## All entries mentioning this concept
[Dataview query pulling all files that link to this note]
```

This is what turns a vault from a filing system into a thinking system. The concepts are the nodes. The links are the edges. The graph becomes navigable.

## Phase 15: Backup confirmation (one sentence, then move on)

**The vault lives on the Desktop. That's the canonical home — set in Phase 1 step 7 ("Put it somewhere easy to find, like your Desktop") and it stays that way.** Do NOT ask the user to pick a backup mechanism. Do NOT push them to move the vault into iCloud / Google Drive / Dropbox. Their normal backup habits (Time Machine, external drive, cloud sync at the OS level, whatever they already do) cover the vault — it's just a folder of markdown files.

One sentence acknowledgment, then move on. In their PRIMARY_LANGUAGE.

**EN:** "One thing to mention: your vault is a folder of markdown files. Whatever you normally use to back up your computer (Time Machine, an external drive, a cloud sync, whatever) already covers it. No special backup setup needed. Moving on."

**ES:** "Una cosa: tu vault es una carpeta con archivos markdown. Lo que sea que normalmente uses para hacer copias de seguridad de tu computador (Time Machine, un disco externo, una sync en la nube, lo que sea) ya lo cubre. No hace falta una configuración especial. Sigamos."

That's it. Do NOT recommend a specific backup tool, do NOT surface a five-option menu, do NOT trigger an alarm because the vault lives on Desktop. Desktop is correct.

Team-vault sharing is handled separately in Phase 20.

## Phase 16: Add Obsidian Power Rules to CLAUDE.md

"Last thing — let me add some rules to your memory file that make every future session smarter."

Add these to their CLAUDE.md under a new section:


**Obsidian Rules template:** Read the full template from `templates/generated/obsidian-rules-template.md` and append it to the user's CLAUDE.md.


Create the Content Drafts, Decision Log, and Vault Changelog files if they don't exist.

### Build the Wikilink Reference

After all rules are added, build a Wikilink Reference file that lists every linkable note in the vault. This helps Claude (and the user) know what can be wikilinked when writing new content.

Create `[VAULT_PATH]/⚙️ Meta/Wikilink Reference.md`:

```markdown
---
creationDate: [today]
type: meta
---
# Wikilink Reference

*All linkable notes and their aliases. Check this before adding wikilinks to new content. Update when new concept notes are created.*

Total: [count] notes

## By Folder
[For each folder, list all .md files with their aliases from frontmatter]
```

To build it, scan every .md file in the vault, extract the filename and any `aliases:` from YAML frontmatter, and list them organized by folder. This becomes the reference Claude checks before wikilinking new content — ensuring links go to real notes, not broken references.

## Phase 17: Connect External Tools Check

After all the installs and imports, quickly verify: "Let's make sure everything is connected. What can you see?"
- Test email: "Search your email for [recent term]"
- Test calendar: "What's on your calendar this week?"
- Test journal: "Let's do a quick /journal test"
- Test vault search: "Ask me something about your notes"

