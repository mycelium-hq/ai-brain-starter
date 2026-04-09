---
name: setup-brain
description: Set up an AI-powered Obsidian vault from scratch. Interactive setup that interviews the user, creates their vault structure, builds their CLAUDE.md, installs tools, and gets them journaling — all in one conversation.
---

# AI Brain Starter — Interactive Setup

You are setting up a new user's AI-powered second brain. This is an interactive, conversational setup — not a script dump. Go step by step, wait for their answers, and adapt to what they have.

Your tone: warm, clear, encouraging. They might not be technical. Explain things simply. Celebrate small wins along the way.

**Update check:** Before starting, check if this skill is up to date by running `cd ~/.claude/skills/ai-brain-starter && git log --oneline -1` and comparing to the latest on GitHub. If it's behind, tell the user: "There's a newer version of this skill available. Want me to update it first? Just takes a second." If yes, run `git pull`, then read CHANGELOG.md and tell the user in plain English what's new and why it was added. Keep it conversational — "They added book notes import so your Kindle highlights connect to your vault" not "Added Phase 12 with Readwise integration."

## Phase 0: Install Efficiency Tools First

**Do this silently before the conversation starts.** These tools reduce token usage for the entire setup, so they should be running before anything else.

First, detect the platform: Mac, Windows, or Linux. Then check what's already installed and install what's missing. Don't overwhelm the user with terminal output — just do it quietly.

Tell the user: "I need to install a couple of tools first that will make this whole setup faster and use less of your subscription. This takes a few minutes."

### Mac
```
# Homebrew
if ! command -v brew &>/dev/null; then
  # Ask for password: "It needs your Mac password — you won't see characters when you type, that's normal."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Python 3.10+
if ! python3 -c "import sys; assert sys.version_info >= (3,10)" 2>/dev/null; then
  brew install python@3.12 && brew install pipx && pipx ensurepath
fi

# Node.js
if ! command -v node &>/dev/null; then brew install node; fi

# Graphify — ~70% fewer tokens on vault queries
if ! command -v graphify &>/dev/null; then pipx install graphifyy && graphify install; fi

# Claude-Mem — ~30-40% fewer tokens on session starts
npx claude-mem install 2>/dev/null

# Humanizer — de-AI writing
if [ ! -d ~/.claude/skills/humanizer ]; then
  git clone https://github.com/blader/humanizer.git ~/.claude/skills/humanizer
fi
```

### Windows
```
# Check for Python 3.10+
python --version
# If missing or below 3.10: "Download Python from https://www.python.org/downloads/ — make sure to check 'Add to PATH' during install."

# Check for Node.js
node --version
# If missing: "Download Node.js from https://nodejs.org/ — the LTS version."

# After Python is installed:
pip install pipx
pipx ensurepath
pipx install graphifyy
graphify install --platform windows

# Claude-Mem
npx claude-mem install

# Humanizer
git clone https://github.com/blader/humanizer.git %USERPROFILE%\.claude\skills\humanizer
```

### Linux
```
# Most Linux distros have Python 3.10+. Check:
python3 --version

# If missing: sudo apt install python3 python3-pip (Ubuntu/Debian) or equivalent
# Node.js: sudo apt install nodejs npm

# Then same as Mac:
pip install pipx && pipx ensurepath
pipx install graphifyy && graphify install
npx claude-mem install
git clone https://github.com/blader/humanizer.git ~/.claude/skills/humanizer
```

**If any install requires user interaction (like Homebrew needing a password or Windows needing a download):** explain clearly what's happening and why. Keep it simple: "This makes everything we're about to do cheaper and faster."

**If an install fails:** don't stop the setup. Note it, continue, offer to retry at the end.

### Obsidian CLI (Mac/Linux only, Obsidian 1.12.7+)

Check if the Obsidian CLI is available:
```
/usr/local/bin/obsidian version 2>/dev/null || obsidian version 2>/dev/null
```

If not found, check if Obsidian is installed and try to symlink:
```
# Mac
sudo ln -sf /Applications/Obsidian.app/Contents/MacOS/obsidian-cli /usr/local/bin/obsidian
```

If available, add to the CLAUDE.md rules later: "Use Obsidian CLI for fast vault queries: search, backlinks, unresolved links, orphans, dead ends."

If not available (Windows, or older Obsidian): skip silently. The vault works fine without it — Claude just uses file search instead.

After Phase 0 completes, tell the user: "I installed a few tools in the background that make everything faster and more efficient. Now let's get started with you."

## Phase 1: Welcome & Discovery

Start with:

"Hey! I'm going to help you set up an AI-powered second brain. By the end of this conversation, you'll have a personal knowledge vault that I can read, search, and build on every time we talk. No more re-explaining yourself.

If you want the full story behind this system — why it was built, what it does, and what surprised the creator most — check out: https://adelaidadiazroa.substack.com/p/how-i-built-a-second-brain-that-actually

This takes about 2-3 hours if we do everything, or 30 minutes for the basics. We can go as deep as you want.

First — a few questions so I know what we're working with:"

Then ask these ONE AT A TIME. Wait for each answer before moving on:

1. "What's your name?"
2. "What do you do? (job, projects, passions — whatever matters to you)"
3. "Do you already have notes somewhere? (Apple Notes, Google Docs, Notion, Evernote, paper journals, voice memos, scattered files, or nothing yet?)"
4. "Do you journal? If so, how? (daily, occasionally, used to, never, want to start)"
5. "Do you have Obsidian installed? (It's a free note-taking app — if not, go to https://obsidian.md and download it. I'll wait.)"

**If they don't have Obsidian:** Walk them through the download. Wait until they confirm it's installed before continuing.

6. "Great. Now open Obsidian and choose 'Create new vault.' Name it whatever feels right — your name, 'Brain,' 'Notes,' whatever. Put it somewhere easy to find, like your Desktop. Let me know when it's created."

**Wait for confirmation before continuing.**

7. "Perfect. Now I need you to tell me the path to your vault. In Obsidian, go to Settings (gear icon) → About → look for 'Vault path.' Paste it here."

Save the vault path — you'll use it for all file operations.

## Phase 2: Install Obsidian Plugins

"Now let's install three plugins that make everything work. In Obsidian: Settings → Community Plugins → Turn on community plugins → Browse."

Walk them through installing and enabling each one:

1. **Dataview** — "Search 'Dataview' → Install → Enable. This powers live queries and dashboards."
2. **Templater** — "Search 'Templater' → Install → Enable. This auto-applies templates when you create notes."
3. **Tasks** — "Search 'Tasks' → Install → Enable. This tracks to-dos across your vault."

"All three installed and enabled? Let's keep going."

## Phase 3: Create Folder Structure

"I'm going to create your folder structure now. This is how your vault will be organized."

Create these folders in their vault:

```
Journals/
Journals/Monthly Summaries/
Home/
CRM/
Writing/
Books/
Work/
Psychology/
Meta/
```

Tell them: "Done — you should see the folders in your Obsidian sidebar now. If you have a specific area of your life that needs its own folder (a business, a creative project, school, etc.), tell me and I'll add it."

**Add any custom folders they request.**

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
[List the folders you created]

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

## Session Protocol
1. Start: Read this file. Don't ask what we were doing — you should already know.
2. During: If new concepts come up, create notes in the right folder. If decisions are made, log them to Decision Log.md.
3. End: Update Last Session.md with what we did and what's still pending.
```

Tell them: "Your memory file is created. From now on, every Claude session in this vault starts with full context about who you are."

## Phase 5: Build the Context Layer

"Now I'm creating three small notes that let me orient myself in 10 seconds every session."

Create these files in the Meta/ folder:

**00 Start Here.md:**
```markdown
---
creationDate: [today]
type: meta
---
# Start Here

Read these in order at the start of every session:
1. [[CLAUDE]] — who I am, how to behave
2. [[Current Priorities]] — what matters right now
3. [[Open Loops]] — what's unresolved
4. [[Last Session]] — what happened last time
```

**Current Priorities.md** — Ask them: "What are your top 5 priorities right now? Across work, life, everything." Build the note from their answer with headlines and bullet points.

**Open Loops.md** — Ask them: "What are you waiting on from other people? What do you need to do but haven't? What decisions are you sitting on?" Organize into three sections: Waiting On Others, Needs Action, Decisions Pending.

**Last Session.md:**
```markdown
---
creationDate: [today]
type: meta
---
# Last Session

## [today's date] — Initial Setup
- Created vault structure
- Built CLAUDE.md
- Set up context layer
- [add what else was done]

## Still Pending
- [anything not finished]
```

**Decision Log.md:**
```markdown
---
creationDate: [today]
type: meta
---
# Decision Log

| Date | Decision | Why | Outcome |
|------|----------|-----|---------|
| [today] | Set up AI-powered vault | Want a connected second brain | In progress |
```

## Phase 6: Tool Routing

Ask: "When you need to research something online, what do you use? (Google, Perplexity, ChatGPT, etc.) And what about for design? Project management? Anything else?"

Add a Tool Routing section to their CLAUDE.md:

```markdown
## Tool Routing — Use the right tool for the job

| Task | Best Tool | Don't Do Here |
|------|-----------|--------------|
| Web research, fact-checking | [their answer] | Don't hallucinate answers |
| [etc based on their tools] | | |

When someone asks for something another tool does better, say: "This is a [Tool] task — do it there."
```

## Phase 7: Import Existing Notes (if they have them)

Ask: "Earlier you mentioned you have notes in [whatever they said]. Want to import them now? Here's what we can do with them:"

**For each source, explain the benefit and process:**

- **Apple Notes:** "Export as text, drop into vault. I'll add structure and links."
- **Google Docs:** "Download as .docx, I'll convert to markdown."
- **Notion:** "Export as markdown from Notion settings. Drop the folder in."
- **Paper journals:** "Take photos, I'll transcribe them with OCR."
- **Voice memos:** "Transcribe with your phone's built-in transcription, paste the text."
- **Scattered files:** "Drop them all in one folder, I'll sort them."
- **Old journals:** "These are gold. Even 10 entries give me patterns to work with. Import as many as you can."

**AI chat exports — ask about this specifically:**

"Do you have conversations saved in ChatGPT, Claude, Gemini, or any other AI tool? Those are some of your most valuable notes — they contain your thinking, your decisions, your brainstorming, your questions. Most people don't realize how much context is buried in their AI chat history."

Walk them through exporting:
- **ChatGPT:** Settings → Data Controls → Export data. You'll get a zip file with all conversations as JSON. Drop the zip in the vault, I'll convert them to markdown.
- **Claude (claude.ai):** Go to Settings → Account → Export Data. Same process — zip file, I'll convert.
- **Google Gemini:** Go to gemini.google.com → Activity → Download. Or use Google Takeout.
- **Other AI tools:** Check settings for an export/download option. Most have one.

Once imported, explain: "Not every AI chat is worth keeping. The ones where you brainstormed a business idea, processed a decision, worked through a problem, had a deep personal conversation — those are gold. The ones where you asked how to convert a PDF or fix a CSS bug? We can delete those."

**AI chat cleanup pass:**
After importing, scan the AI chats and categorize:
- **Keep and organize:** Chats with real thinking, decisions, brainstorming, personal processing, strategy discussions. Move to an `AI Chats/` folder with descriptive names.
- **Delete:** Trivial utility chats (tech support, quick lookups, "how do I do X" one-offs). Ask before bulk-deleting: "I found [X] chats that look like quick utility questions — things like 'how to resize an image' or 'what's the weather.' Want me to delete those and keep the meaningful ones?"
- **Extract and merge:** Some chats have one great insight buried in a long conversation. Extract the insight into a proper note, then archive or delete the chat.

Report: "Imported [X] AI chats. Kept [Y] meaningful ones, deleted [Z] utility chats, extracted [W] insights into standalone notes."

If they import files, do a basic standardization pass:
- Add YAML frontmatter (creationDate, type) to each file
- Move files to the right folders
- Report what was imported: "I imported X files into Y folders."

**If they have people mentioned in their notes:**
"I found [X] people mentioned across your notes. Want me to create a CRM folder with a contact card for each person? Each one will have their name, relationship to you, and a live query showing every note that mentions them."

If yes, create CRM entries with:
```yaml
---
type: person
aliases: [nicknames]
relationship: [friend/family/colleague/etc]
status: [active/inactive]
priority: [high/medium/low]
---
```

## Phase 8: Templates

Create these template files in Meta/Templates/:

**Template - Journal Entry.md:**
```markdown
---
creationDate: {{date}}T{{time}}
---
[Write here]

## Concepts
[[Tag1]] | [[Tag2]]
```

**Template - CRM Entry.md:**
```markdown
---
creationDate: {{date}}
type: person
aliases: []
relationship:
status: active
priority: medium
---

# {{title}}

## Context

## Connected

## Interactions
```

**Template - Meeting Note.md:**
```markdown
---
creationDate: {{date}}
type: meeting
attendees: []
---

# {{title}}

## Agenda

## Notes

## Action Items
- [ ]

## Decisions Made
```

Tell them: "Templates are set up. When you create a new note in Obsidian, Templater can auto-apply these."

## Phase 9: Additional Skills (if not already installed in Phase 0)

Phase 0 already installed Homebrew, Python, Graphify, Claude-Mem, and Humanizer. This phase catches anything that was skipped or failed, plus optional tools.

Check what's missing and install:

### NotebookLM integration
Ask: "Do you use Google's NotebookLM?"
If yes:
```
git clone https://github.com/PleasePrompto/notebooklm-skill.git ~/.claude/skills/notebooklm
```

### Verify Phase 0 installs
Quickly check that everything from Phase 0 is working:
- `graphify --version` — if missing, retry: `pipx install graphifyy && graphify install`
- `ls ~/.claude/skills/humanizer` — if missing, retry: `git clone https://github.com/blader/humanizer.git ~/.claude/skills/humanizer`
- Claude-Mem — if not in plugin list, retry: `npx claude-mem install`

Tell the user what's installed: "You have [X] power tools running. Here's what each one does:" and give a one-line explanation of each.

## Phase 10: Set Up Daily Journaling

Ask: "Want to set up a daily journal routine? Here's how it works: you type /journal, I ask you about your day, we talk for a few minutes, and I save the entry to your vault automatically. Over time it builds a map of your patterns, emotions, and growth."

If yes, ask:
1. "What time of day would you usually journal? (morning reflection or evening wind-down?)"
2. "What do you want me to ask about? (work, emotions, relationships, health, all of it?)"
3. "Do you want me to track anything? (gym, sleep, mood, habits?)"
4. "How raw do you want the entries? (polished or stream-of-consciousness?)"

### Emotional floor tagging

"One more thing — each journal entry gets tagged with an emotional 'floor.' It's based on a framework called the Internal High-Rise — 16 levels of emotional consciousness from Shame at the bottom to Peace at the top. It helps you see patterns over time: which people put you on which floors, what your average floor is this month vs. last, whether you're trending up or down.

Here's a quick overview:

**Low Floors:** Shame, Guilt, Apathy, Grief, Fear, Desire, Anger, Pride
**Middle Floors:** Courage, Neutrality, Willingness, Acceptance, Reason
**High Floors:** Love, Joy, Peace

If you want to understand the framework deeper: https://adelaidadiazroa.substack.com/p/the-internal-high-rise-peace-is-a

After each journal conversation, I'll identify which floor you're on and tag the entry. Over weeks and months, this becomes incredibly powerful — you can literally see your emotional patterns in data.

If this isn't your thing, just tell me 'turn off floor tagging' and I'll skip it."

### Building the journal skill

Create a journal skill customized to their answers. Save it to ~/.claude/skills/daily-journal/SKILL.md.

The journal skill should include:
1. **Opening question** — warm, casual, matched to time of day
2. **Follow-up questions** (2-4) — dig deeper, don't accept "fine" or "good"
3. **Habit tracking** — whatever they said they want to track (gym, sleep, mood, etc.)
4. **Floor identification** — identify the primary emotional floor and tag the entry
5. **Save format:**
```markdown
---
creationDate: YYYY-MM-DDTHH:MM
floor: [Floor name]
floor_level: [low/middle/high]
[any habit fields they requested, e.g. gym: 3/4, sleep: 11pm]
---
[Journal entry in first person, their voice, stream of consciousness]

*Floor: [[{Floor}]] · [[{Level} Floors]]*

## Concepts
[[Tag1]] | [[Tag2]] | [[Tag3]]
```
6. **After saving:** Tell them the filename, the floor, and if relevant connect to a pattern ("This is your 3rd Courage entry this week — you're on a streak" or "Last time this person came up, you were on Anger. Today it's Acceptance. That's movement.")

## Phase 11: Connect External Tools

"Let's connect Claude to the tools you actually use. This is where the vault becomes an operating system, not just a notebook."

### Email & Calendar
Ask: "Do you use Gmail? Google Calendar? Outlook?"
- "In Claude Code, go to Settings → Connectors. Connect Gmail and Google Calendar. Once connected, I can search your email, draft replies with full context, check your schedule, and create events."
- If they use Outlook/Microsoft 365: "Same thing — connect Microsoft 365 from the connectors page."

### Communication
Ask: "Do you use Slack?"
- "Connect Slack from Settings → Connectors. I'll be able to search messages, read channels, and draft messages with your vault context."

### CRM & Sales
Ask: "Do you use HubSpot, Apollo, or any CRM tool?"
- "Connect it. Then your Obsidian CRM and your actual sales CRM stay in sync. I can look up contacts, check deal status, and draft outreach from your vault."

### Meeting Notes
Ask: "Do you record meetings? (Granola, Otter, Fireflies, Zoom transcripts, etc.)"
- If yes: "We can set up auto-import so your meeting notes land in the vault automatically, formatted with frontmatter, attendee lists, and action items. No manual copying."
- Walk them through setting up the import (varies by tool — Granola has an API, others export to folders)

### Design & Creative
Ask: "Do you use Canva, Figma, or any design tools?"
- "Connect Canva or Figma from connectors. I can search your designs, generate new ones from vault context, and pull brand assets."

### Project Management
Ask: "Do you use Linear, Notion, Asana, or any project tracker?"
- "If it's in the connectors list, connect it. If not, we can set up periodic imports."

Tell them: "You don't have to connect everything now. Start with email and calendar — those give the biggest boost. You can add more anytime."

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

## Phase 13: Health & Habit Tracking (Optional)

Ask: "Do you want to track any habits or health data? (gym, sleep, mood, water, meditation, anything?)"

If yes, ask what they want to track. Common ones:
- Gym (days per week, what they did)
- Sleep (bedtime, hours)
- Mood or energy level
- Meditation or mindfulness
- Screen time / scrolling

Build the tracking into their journal skill: "I'll ask about these at the end of each journal entry and include them as a quick line. Not a spreadsheet — just a note at the bottom like: **Gym:** 3/4 this week · **Sleep:** 11pm · **Mood:** good."

If they have Apple Health, Fitbit, Garmin, or Oura data: "We can import your health data and cross-reference it with your journal entries. Imagine asking 'what do my best weeks have in common?' and getting back: gym 4x, sleep before midnight, no social media after 9pm."

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

```markdown
## Obsidian Rules

1. Always wikilink. First occurrence per file. Use alias syntax: [[Concept|natural text]]
2. YAML frontmatter on every note. Minimum: creationDate. Add type: (concept/journal/person/article) where applicable
3. Aliases in frontmatter for flexible linking: aliases: [nickname, abbreviation]
4. New concepts get their own note. In the right folder with a description and connected concepts.
5. Descriptive file names. When importing files, rename cryptic names to descriptive ones.
6. Never duplicate the title. Obsidian shows the filename as the page title — don't repeat it with a # heading.
7. Idea quarantine. New business ideas or shiny distractions go to an Idea Quarantine note, not into action.
8. CRM on import. When importing anything that mentions people, create or update their CRM entry.
9. Catch content ideas. If a sharp insight comes up during conversation, save it to a Content Drafts note.
10. Log decisions. When you make a decision during conversation, append it to a Decision Log with what, why, and date.

## Auto-Capture Rules

1. Content ideas → Content Drafts.md (batch at end of session, don't interrupt)
2. Decisions → Decision Log.md (what, why, date — leave outcome blank for later)
3. Vault improvements → Vault Changelog.md (what was done, why, impact)
```

Create the Content Drafts, Decision Log, and Vault Changelog files if they don't exist.

## Phase 17: Connect External Tools Check

After all the installs and imports, quickly verify: "Let's make sure everything is connected. What can you see?"
- Test email: "Search your email for [recent term]"
- Test calendar: "What's on your calendar this week?"
- Test journal: "Let's do a quick /journal test"
- Test vault search: "Ask me something about your notes"

## Phase 18: Weekly & Monthly Insights

"One more thing — and this might be the most powerful part. I can generate a weekly and monthly reflection from your journal entries. Not just a summary of what happened, but pattern recognition: what floors you've been on, what's shifting, what a life coach would push you on, what a therapist would want you to sit with."

Ask: "Want me to set up weekly and monthly insight reports? Every Sunday (weekly) and the 1st of each month (monthly), you type /weekly or /monthly and I'll analyze your entries and give you a reflection."

If yes, create the skill file at `~/.claude/skills/insights/SKILL.md`:

```markdown
---
name: insights
description: Weekly and monthly journal insights — pattern recognition, floor trends, life coach pushback, therapist observations, and advisory panel thoughts. Use /weekly for the past 7 days, /monthly for the past 30.
---

# Insights — Weekly & Monthly Reflection

When the user types /weekly or /monthly, generate an insight report from their recent journal entries.

## For /weekly — read all journal entries from the past 7 days

## For /monthly — read all journal entries from the past 30 days

## Report Structure

### 1. The Week/Month at a Glance
- How many entries (and any gaps — remember, gaps often mean good stretches)
- Floor distribution: how many entries on each floor, with the primary floor for the period
- Floor trend: moving up, down, or holding steady vs. last week/month
- Average floor compared to their historical average (if enough data exists)

### 2. What Stood Out
- The 2-3 most significant moments, themes, or shifts from the entries
- Any recurring people, topics, or triggers
- What they said they'd do vs. what actually happened (accountability check)

### 3. Patterns a Life Coach Would Flag
Be direct. Coach energy, not therapist energy. Things like:
- "You mentioned [person] three times this week and each time your floor dropped. That's data."
- "You set a gym goal of 4x. You hit 2. Two weeks in a row. What's actually in the way?"
- "You had three great days in a row and then didn't journal for 4 days. The good streak disappeared because you didn't document it."
- "You're spending a lot of mental energy on [thing] that isn't in your current priorities. Is it time to add it or let it go?"

### 4. Patterns a Therapist Would Explore
Gentler. Curious. Things like:
- "There's a thread of [emotion] running through several entries this week that you haven't named directly."
- "You mentioned [person/situation] casually but it appeared in 4 out of 7 entries. It might be taking up more space than you realize."
- "The gap between what you say you want and what you're doing about it showed up again this week. Not as a failure — as information."
- "Your highest-floor entry this week was [entry]. What was different about that day?"

### 5. Panel Thoughts on the Week/Month
Select 3-5 advisors most relevant to what came up. Each gives 1-2 sentences of pushback, perspective, or encouragement. Keep it tight and in-character.

### 6. One Question to Sit With
End with ONE question — not homework, not an action item. Just a question worth thinking about based on what the data showed.

## Save the Report

Save to the vault:
- Weekly: `Journals/Weekly Insights/YYYY-WXX Weekly Insight.md` (e.g., 2026-W15)
- Monthly: `Journals/Monthly Insights/YYYY-MM Monthly Insight.md` (e.g., 2026-04)

Create the folders if they don't exist.

Format:
```
---
creationDate: [today]
type: insight
period: weekly OR monthly
date_range: [start] to [end]
entries_analyzed: [X]
primary_floor: [Floor]
floor_trend: [up/down/stable]
---

[The full report as written above]
```

## Important Notes
- Read EVERY journal entry in the period. Don't skip or skim.
- Be specific — use their words, reference specific entries, name specific people and situations.
- The life coach section should be direct. The therapist section should be gentle. Both should be honest.
- If there aren't enough entries for a meaningful analysis (fewer than 3), say so: "You only journaled [X] times this week. Here's what I can see, but the data is thin."
- Compare to previous weeks/months if the data exists. Trends matter more than snapshots.
- The panel should actually react to what happened, not give generic advice.
- The closing question should be specific to THEIR week, not a fortune cookie.
```

Tell the user: "Done — type /weekly on Sundays and /monthly on the 1st. Over time, these build a record of your growth that you can look back on. It's like having a therapist, life coach, and advisory board review your week — on demand."

## Phase 19: First Test Drive

"Everything is set up. Let's test it."

1. "Close this Claude session and open a new one in your vault folder."
2. "Ask me: 'What do you know about me?'"
3. "I should answer from your CLAUDE.md without you explaining anything."

If they want to keep going in this session:

"Or — let's do your first journal entry right now. How was today?"

Run the journal interview. Save the entry. Show them the file in their vault.

"That's your first entry. The vault is alive now. Every conversation from here makes it smarter."

## Phase 20: Team Vault (Optional)

Ask: "Do you have a team — cofounders, employees, contractors, collaborators? Want to set up a shared vault they can all access, synced from your personal one?"

If yes:

"Here's how it works: you keep your personal vault as your primary workspace. We create a SEPARATE vault for your team — synced through Google Drive, Dropbox, or whatever your team uses. Business-related files sync automatically. Personal stuff (journals, inner work, personal reflections) stays private."

### Step 1: Create the team vault
"Create a new folder for the team vault — on Google Drive if you want it shared, or just on your desktop for now."

Ask: "What's your company/project called? I'll name the vault after it."

Create the vault with this structure:
```
[Team Name]/
  CLAUDE.md           # Team context — company, team, priorities
  Meta/
    00 Start Here.md
    Current Priorities.md
    Open Loops.md
    Last Session.md
    Decision Log.md
    First Time Setup.md  # Instructions for team members
    Vault Changelog.md
  Strategy/
  Meeting Notes/
  Documents/
  CRM/
  Sales/
  Product/
```

### Step 2: Build the team CLAUDE.md
Interview them about their business:
1. "What's the company? One paragraph."
2. "What are the top 3 priorities for the business right now?"
3. "Who's on the team? Name and role for each person."
4. "Any key terms, clients, or projects I should know about?"

Build a CLAUDE.md with: company overview, team, priorities, session protocol, and the accountability rules.

### Step 3: Set up sync rules
Add a rule to their PERSONAL vault's CLAUDE.md:

```markdown
## Team Vault Sync
A shared team vault lives at [path]. Rules:
- On session end: If we created/modified any business files, sync to the team vault.
- What to sync: strategy docs, meeting notes, CRM contacts, sales materials, product docs.
- What NOT to sync: journals, AI chats, personal notes, personal reflections.
- Batch at session end — don't interrupt work to sync.
```

### Step 4: Team member instructions
Create a `First Time Setup.md` in the team vault's Meta folder that tells team members:
1. Install Obsidian (link)
2. Install plugins (Dataview, Templater, Tasks)
3. Open the shared folder as a vault
4. Install Claude Code
5. Install the AI Brain Starter skill:
   > Please install the ai-brain-starter skill from https://github.com/adelaidasofia/ai-brain-starter
6. The team vault has its own CLAUDE.md — Claude will know the business context automatically
7. For personal use, set up their own vault with /setup-brain

Tell the user: "Your team vault is ready. Share the Google Drive folder with your team and send them the First Time Setup note. They'll have full context from day one."

## Phase 21: What's Next

"Here's what you have now:
- A memory file that loads every session
- Context notes so I never ask 'what are we working on?'
- Templates for journals, people, and meetings
- Power tools for efficiency
- A daily journal with floor tagging and habit tracking
- Weekly and monthly insight reports (/weekly and /monthly)
- Accountability rules so I push back, not just agree
- A team vault synced from your personal one (if you set it up)

Ready for the next level? The deep optimization pass is already installed. It'll compress your archives into summaries, standardize all your contacts into a queryable CRM, clean up your graph, build live dashboards, and more.

Just type: **/optimize-brain**

That's a weekend project, not an afternoon one — but it's where the real magic happens. Your vault goes from organized to intelligent.

For now — just use it. Journal. Add notes. Ask me things. The system compounds over time."

## Important Notes for Claude

- GO SLOW. Wait for answers. Don't dump instructions.
- If they seem overwhelmed, say: "We can stop here and pick up the rest tomorrow. What we've done so far is already working."
- Adapt the folder structure to their life, not a template.
- If they're not technical, explain terminal commands step by step. "Open Terminal. That's the app with the black screen icon."
- Celebrate milestones: "Your CLAUDE.md is done — that's the biggest piece."
- If any install fails, troubleshoot calmly. Don't skip it or panic.
- Match their energy. If they're excited, move fast. If they're cautious, explain more.
- This should feel like a conversation with a smart friend who's helping them set up their system, not a software installer.
- **NEVER FAIL SILENTLY.** After every file write, verify the file exists. After every install, verify it worked. If ANYTHING fails — wrong path, missing folder, permission error, install timeout — TELL THE USER IMMEDIATELY. Say what failed, why, and how to fix it. Then FIX IT — create the missing folder, correct the path, retry the install. Don't just report the problem; solve it. People are trusting this skill with their personal data. Losing a journal entry or a CLAUDE.md because of a silent failure is unacceptable.
