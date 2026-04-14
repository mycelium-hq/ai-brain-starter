# Phases 12-17: Imports, Taxonomy, Backup, and Obsidian Rules

---

## Phase 12: Import Book Notes & Highlights

Ask: "Do you read books and highlight? (Kindle, Apple Books, Readwise, physical books with notes?)"

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

## Phase 13: Health Data Import (Optional)

**Note:** Basic habit tracking (gym, sleep, mood, scrolling) is already built into the journal skill from Phase 10. This phase is ONLY for importing external health data sources.

Ask: "Do you use any health tracking devices or apps? (Apple Health, Fitbit, Garmin, Oura, Whoop?)"

If yes: "We can import your health data and cross-reference it with your journal entries. Imagine asking 'what do my best weeks have in common?' and getting back: gym 4x, sleep before midnight, no social media after 9pm. The habit tracking from your journal gives you the subjective data — this gives you the objective data."

Walk through their specific source:
- **Apple Health:** Export via Apple Health app → Share → Export All Health Data. Creates a zip with XML. We can parse steps, sleep, heart rate, workouts into YAML frontmatter on journal entries.
- **Fitbit / Garmin / Oura / Whoop:** Check if they have API access or export options. Some have Obsidian community plugins.

If they don't have any health devices, skip this phase entirely — Phase 10 already handles the habit tracking.

## Phase 14: Build Your Concept Taxonomy

Ask: "Do you have a framework you think about life through? (Values, principles, categories, a personal philosophy?) Or do you want to build one?"

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

## Phase 15: Backup & Sync Setup

Ask: "How do you want to back up your vault? (Google Drive, iCloud, Dropbox, Git, or just local?)"

**Important:** "Your vault is just a folder of files. If that folder disappears, everything is gone. Let's make sure it's backed up."

Options:
- **Google Drive / Dropbox / iCloud:** "Move your vault folder into your cloud sync folder. It'll back up automatically. This also lets you access it from multiple devices."
- **Git:** "If you're comfortable with git, we can initialize a repo and push to GitHub (private). This gives you version history — you can undo any change."
- **Just local:** "At minimum, set a reminder to copy the vault folder to an external drive once a week."

If they want to share the vault with a team: "Google Drive is the best option for team vaults. Everyone installs Google Drive for Desktop, opens the vault in Obsidian, and the files sync. I can help you set up a separate team vault later."

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

