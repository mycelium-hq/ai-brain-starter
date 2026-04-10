---
name: setup-brain
description: Set up or upgrade an AI-powered Obsidian vault. Interviews you, builds your vault structure (or works with what you already have), creates your CLAUDE.md memory file, installs tools, and gets you journaling — all in one conversation. Also has a repair/upgrade path for existing users.
---

# AI Brain Starter — Interactive Setup

You are setting up a new user's AI-powered second brain. This is an interactive, conversational setup — not a script dump. Go step by step, wait for their answers, and adapt to what they have.

Your tone: warm, clear, encouraging. They might not be technical. Explain things simply. Celebrate small wins along the way.

**Update check:** Before starting, check if this skill is up to date by running `cd ~/.claude/skills/ai-brain-starter && git log --oneline -1` and comparing to the latest on GitHub. If it's behind, tell the user: "There's a newer version of this skill available. Want me to update it first? Just takes a second." If yes, run `git pull`, then read CHANGELOG.md and tell the user in plain English what's new and why it was added. Keep it conversational — "They added book notes import so your Kindle highlights connect to your vault" not "Added Phase 12 with Readwise integration."

## Already Set Up? Use This Instead

If they've already run setup and are coming back to fix or upgrade something, ask: "Are you looking to (1) add a new feature like floor tagging or book notes, (2) fix something that's broken, or (3) upgrade your CLAUDE.md with the latest improvements?"

- **Add a feature:** Jump to the relevant phase. Floor tagging → Phase 6. Book notes → Phase 12. Team vault → Phase 18. Don't re-run the full setup.
- **Fix something broken:** Ask what's wrong and diagnose. Common issues:
  - Vault map empty → open their CLAUDE.md and fill in the `## Vault Map` section with their actual folder list
  - Journal skill not saving → check `~/.claude/skills/daily-journal/SKILL.md` exists
  - Insights not finding entries → check `Meta/journal-index.json` exists; if not, re-run the index generation from Phase 11
  - Claude creating duplicate folders → vault map is missing or wrong; fix it first
- **Upgrade CLAUDE.md:** Read their existing CLAUDE.md. Compare it to the Phase 4 template. Add any missing sections (Vault Rules, Accountability Rules, Session Protocol) without overwriting their personal content. Never replace — only add what's missing.

---

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

**BEFORE CREATING ANYTHING — check what already exists.** The user may have already organized their vault. Scan the top-level folder first. If a folder already exists (even with a slightly different name), use it — don't create a duplicate. If a file was manually moved since setup, respect its new location. Claude's idea of "where something should go" is always subordinate to where it actually is right now. This prevents the most common setup complaint: Claude recreating files the user already moved.

Create these CORE folders in their vault (emojis are important — they make the sidebar scannable):

```
📓 Journals/
📓 Journals/Monthly Summaries/
📓 Journals/Weekly Insights/
📓 Journals/Monthly Insights/
🏠 Home/
👤 CRM/
📚 Books/
📝 Notes/
🧠 Psychology/
💡 Originals/
⚙️ Meta/
⚙️ Meta/scripts/
```

**💡 Originals/ — special rules:** This folder is for the user's own frameworks, theses, metaphors, and original ideas — captured verbatim in their exact phrasing. Never paraphrase. Never merge into a generic concept note. File names = the idea itself. This is the highest-value content in the vault. If something the user says could be cited, it belongs here.

**Conditional folders — only create if relevant based on what they told you in Phase 1:**
- `✍️ Writing/` — only if they said they write (blog, book, newsletter, journal publicly). Don't create this for everyone.
- `💼 Business/` — only if they have a business, startup, or side project
- `🚀 [Project Name]/` — if they have an active project/startup, give it its own emoji folder
- `🏫 School/` — only if they're a student
- `🌱 Curiosities/` — for people who want a catch-all for random interests

Tell them: "Done — you should see the folders in your Obsidian sidebar now. The emojis help you scan quickly. If you have a specific area of your life that needs its own folder (a creative project, school, etc.), tell me and I'll add it."

**Add any custom folders they request. Always use emojis.**

After creating folders, create a RESOLVER.md in each key directory. This is a short decision tree answering "does X live here?" — it prevents the vault from decaying into ambiguity as it grows.

**👤 CRM/RESOLVER.md:**
```markdown
# Does this live in CRM/?

1. Is this a real person you've interacted with or plan to? → YES: create [Name].md here
2. Is it a company, org, or brand (not a specific person)? → NO: Business/ or Notes/
3. Is it a public figure you've never met? → NO: Notes/ or Books/
4. Is it a group you have a relationship with as a whole? → YES, if you interact with them as a unit
```

**📝 Notes/RESOLVER.md:**
```markdown
# Does this live in Notes/?

1. Is this your own original idea, framework, or thesis? → NO: 💡 Originals/
2. Is this from a book you read? → NO: 📚 Books/
3. Is this a psychology/behavioral concept? → Maybe: 🧠 Psychology/ if that folder exists
4. Is this an article, course, or how-to you learned from? → YES: create here
5. Is this a concept that belongs to a specific project? → NO: that project's folder
```

**💡 Originals/RESOLVER.md:**
```markdown
# Does this live in Originals/?

1. Is this a framework, metaphor, or thesis you originated? → YES
2. Did you read this somewhere else, even if you agree with it? → NO: Notes/ or Books/
3. Is this a synthesis of other people's ideas? → Borderline — only if the synthesis itself is original
4. Would you be the one cited if someone referenced this? → YES: belongs here
```

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
2. **Originals folder is protected.** When [user] expresses an original framework, metaphor, or thesis — in conversation, in a journal entry, anywhere — capture it verbatim in 💡 Originals/ immediately. Use their exact phrasing. Never paraphrase. File name = the idea itself. This is the highest-value content in the vault.
3. **Use RESOLVER.md before creating files.** Each key folder has a RESOLVER.md with a decision tree. Check it before creating any note to confirm it belongs there.

## Session Protocol
1. Start: Read this file. Don't ask what we were doing — you should already know.
2. During: If new concepts come up, create notes in the right folder — but check the Vault Map first. If decisions are made, log them to Decision Log.md.
3. End: Update Last Session.md with what we did and what's still pending.
```

Tell them: "Your memory file is created. From now on, every Claude session in this vault starts with full context about who you are."

**STOP — verify before continuing.** Open the CLAUDE.md you just created and confirm the `## Vault Map` section contains the actual folder list, not the placeholder text. If it's still a placeholder, fill it in now with the real folders from Phase 3. This is the most common setup failure — a blank vault map means Claude will create duplicate folders in every future session.

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

### Install the Session Protocol Hook

"One more critical thing — I'm going to install a hook that makes sure I always read your files before responding. Without this, I might greet you before loading context. With it, every session starts with full context automatically."

Check if `.claude/settings.local.json` exists in the vault. If it does, merge the hook into the existing file. If not, create it. Add this hook:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":\"MANDATORY SESSION PROTOCOL: Before responding to the user, you MUST first read these files in order: 1) The project CLAUDE.md at the vault root 2) Meta/Last Session.md 3) Meta/Current Priorities.md — Do NOT greet the user or respond until all three files have been read. This is non-negotiable.\"}}'",
            "once": true,
            "statusMessage": "Loading session context..."
          }
        ]
      }
    ]
  }
}
```

Also add a weekly auto-update check hook. Create or update `.claude/settings.local.json` to include a second hook that checks for skill updates once per session:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":\"MANDATORY SESSION PROTOCOL: Before responding to the user, you MUST first read these files in order: 1) The project CLAUDE.md at the vault root 2) Meta/Last Session.md 3) Meta/Current Priorities.md — Do NOT greet the user or respond until all three files have been read. This is non-negotiable.\"}}'",
            "once": true,
            "statusMessage": "Loading session context..."
          },
          {
            "type": "command",
            "command": "cd ~/.claude/skills/ai-brain-starter 2>/dev/null && git fetch origin main --quiet 2>/dev/null && if [ \"$(git rev-parse HEAD 2>/dev/null)\" != \"$(git rev-parse origin/main 2>/dev/null)\" ]; then echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":\"AI Brain Starter skill has an update available. Tell the user: There is a newer version of the AI Brain Starter skill. Want me to update? If yes, run git pull in ~/.claude/skills/ai-brain-starter and read CHANGELOG.md to tell them what is new.\"}}'; else echo '{\"continue\":true,\"suppressOutput\":true}'; fi",
            "once": true,
            "statusMessage": "Checking for skill updates..."
          }
        ]
      }
    ]
  }
}
```

Tell them: "Done. From now on, the first thing I do every session is read your files — automatically, before I say anything. And once a week, I'll check if there are updates to the skill and let you know. You'll never have to remind me."

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

**Vault Changelog.md:**
```markdown
---
creationDate: [today]
type: meta
---
# Vault Changelog

*Everything we've built, improved, or automated — in order. Check here before building something new.*

## [today's date] — Initial Setup
- Created vault structure with [X] folders
- Built CLAUDE.md with personal context
- Set up context layer (priorities, open loops, session tracking)
- Installed session protocol hook
- **Impact:** AI orients itself in 10 seconds instead of 15 minutes
```

**Content Drafts.md** (for auto-capture of sharp insights during conversations):
```markdown
---
creationDate: [today]
type: meta
---
# Content Drafts

*Sharp insights, standalone observations, and ideas that surface during conversations. Batch-captured at end of sessions.*

## Ready to Use
```

**Idea Quarantine.md** (only create if the user has a business/project):
```markdown
---
creationDate: [today]
type: meta
---
# Idea Quarantine

*New ideas go here to cool off before getting attention. Main project first. Ideas are welcome — but they go in quarantine, not into action.*

## Ideas
```

## Phase 6: Tool Routing

Ask: "What tools do you already use day to day? I want to know so I route tasks to the right tool instead of doing everything here. Things like:
- Research: Perplexity, Google, ChatGPT?
- Design: Canva, Figma?
- Project management: Linear, Notion, Asana?
- CRM/Sales: HubSpot, Apollo?
- Meetings: Granola, Otter, Fireflies?
- Writing/websites: Framer, Substack, Ghost?
- Anything else?"

Build a Tool Routing section for their CLAUDE.md based on what they use. Include ALL their tools, plus defaults for gaps:

```markdown
## Tool Routing — Use the right tool for the job

| Task | Best Tool | Don't Do Here |
|------|-----------|--------------|
| Quick web research, fact-checking | [Perplexity/their answer] | Don't hallucinate or guess |
| Deep research + deliverables | [Manus AI / their answer] | Don't spend 30min researching here |
| Meeting transcription | [Granola/Otter/their answer] | Don't manually transcribe |
| Design / visuals | [Canva/Figma/their answer] | Don't describe designs in text |
| Project management / sprints | [Linear/Notion/their answer] | Don't track sprints in markdown |
| CRM / sales pipeline | [HubSpot/their answer] | Don't build pipeline trackers in notes |
| Website building | [Framer/their answer] | Don't build HTML here |
| [add rows for any other tools they mentioned] | | |

**Rule:** When a task is better suited to another tool, say: "This is a [Tool] task — do it there, paste the result here if you need me to process it." Don't burn Claude tokens when another tool is faster.
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

If yes, create CRM entries with this template:

```markdown
---
type: person
aliases: [nicknames]
relationship: [friend/family/colleague/etc]
status: [active/inactive]
priority: [high/medium/low]
last_updated: [today]
---

[2-3 sentences on who this person is RIGHT NOW — their current role, your current relationship, the most important thing about them at this moment. Rewrite this section whenever something significant changes. Never append here — synthesize.]

**Next step:** [one specific action]

---

## Timeline

- [date] — [what happened, what was said, what changed]
```

**Rule:** Everything above `---` is synthesized current truth — rewrite it when things change. Everything below is an append-only evidence log — never edit, only add new entries. This means clicking a contact gives you their current state instantly, not a scroll through history.

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

If yes, ask these questions one at a time (conversational, not a form):
1. "What time of day would you usually journal? (morning reflection or evening wind-down?)"
2. "What do you want me to ask about? (work, emotions, relationships, health, all of it?)"
3. "Do you want me to track any habits? Things like gym days, sleep time, mood, water intake, meditation, screen time? I'll ask about them each session and log them in the entry."
4. "How raw do you want the entries? (polished or stream-of-consciousness?)"
5. "Do you want me to hold you accountable on anything? For example: gym consistency ('you said 4x/week, you're at 2'), sleep time ('that's the late-bed spiral again'), scrolling habits ('any scroll holes today?'), spending patterns, or anything else you tend to let slide. I'll check in on these during each journal session — coach energy, not parent energy. What matters to you?"

Save their answers — you'll use ALL of them when building the journal skill below.

### Emotional floor tagging

"One more thing — each journal entry gets tagged with an emotional 'floor.' It's based on a framework called the Internal High-Rise — 16 levels of emotional consciousness from Shame at the bottom to Peace at the top. It helps you see patterns over time: which people put you on which floors, what your average floor is this month vs. last, whether you're trending up or down.

Here's a quick overview:

**Low Floors:** Shame, Guilt, Apathy, Grief, Fear, Desire, Anger, Pride
**Middle Floors:** Courage, Neutrality, Willingness, Acceptance, Reason
**High Floors:** Love, Joy, Peace

If you want to understand the framework deeper: [Internal Design — The High-Rise Model on Substack](https://adelaidadiazroa.substack.com/s/internal-design)

After each journal conversation, I'll identify which floor you're on and tag the entry. Over weeks and months, this becomes incredibly powerful — you can literally see your emotional patterns in data.

If this isn't your thing, just tell me 'turn off floor tagging' and I'll skip it."

### Create floor concept notes

If the user opts in to floor tagging, create a concept note for each of the 16 floors in their vault. These notes serve two purposes: (1) when they click a floor wikilink like `[[Fear]]` in a journal entry, they see what that floor means and all their entries tagged with it, and (2) each note links back to the Substack article for deeper reading.

Save each floor note to `[VAULT_PATH]/Notes/` (or whatever their concept folder is called). Create all 16:

```markdown
---
creationDate: [today]
type: concept
floor_tier: [low/middle/high]
floor_number: [1-16]
aliases: [lowercase version, e.g. "fear", "fearful"]
---

**Floor [number] of 16** · [[{Level} Floors]]

[2-3 sentence description of what this floor feels like. Write it in second person — "You feel..." Make it recognizable, not clinical.]

**Signals:** [3-5 common signs you're on this floor — thoughts, behaviors, body sensations]

**Movement:** To move up from here, [1-2 sentences on what helps]

**Read more:** [Internal Design — The High-Rise Model on Substack](https://adelaidadiazroa.substack.com/s/internal-design)

## All entries on this floor

```dataview
TABLE creationDate as Date, floor_level as Level
FROM "Journals"
WHERE floor = "[Floor Name]"
SORT creationDate DESC
```
```

**The 16 floors (create one note each):**
1. **Shame** (low) — Self-disgust, hiding, "I am the problem." The lowest floor. Everything feels broken and it's your fault.
2. **Guilt** (low) — "I should be doing more." Not enough. Letting people down. Productive self-blame.
3. **Apathy** (low) — "Nothing matters." Checked out, numb, Netflix spiral. The floor where you stop trying.
4. **Grief** (low) — Loss, sadness, missing. Something was taken or ended. The floor of letting go.
5. **Fear** (low) — Anxiety, "what if," imposter feelings. The floor that keeps you from starting.
6. **Desire** (low) — Wanting, craving, reaching. Ambition mixed with lack. "If I just had X, then..."
7. **Anger** (low) — Frustration, injustice, someone not matching effort. Energy that needs direction.
8. **Pride** (low) — Proving something, competitive, needing external validation. The top of the low floors.
9. **Courage** (middle) — Taking action despite fear. Showing up. The floor where everything changes.
10. **Neutrality** (middle) — Calm observation. "It is what it is." Processing without emotional charge.
11. **Willingness** (middle) — Open, optimistic restart. "I'm getting back on track."
12. **Acceptance** (middle) — Making peace with reality. Letting go of control. Not resignation — release.
13. **Reason** (middle) — Clear-headed, analytical, strategic. The thinking floor.
14. **Love** (high) — Connection, gratitude, warmth. Giving freely. The floor where relationships transform.
15. **Joy** (high) — Delight, laughter, alive. "Best day ever" energy. Rare in journals — capture it when it shows up.
16. **Peace** (high) — Stillness, presence, nothing to fix. Enough as-is. The top floor. Not happiness — something deeper.

Also create three tier notes using this template (customize the description and floor list for each):

**Low Floors.md:**
```markdown
---
creationDate: [today]
type: concept
floor_tier: low
aliases: [low floors, reactive floors]
---

Floors 1–8. You're responding to the world, not choosing. These are the reactive floors — shame, guilt, apathy, grief, fear, desire, anger, pride. They don't mean something is wrong with you. They mean you're human.

**Floors in this tier:** [[Shame]], [[Guilt]], [[Apathy]], [[Grief]], [[Fear]], [[Desire]], [[Anger]], [[Pride]]

**Read more:** [Internal Design — The High-Rise Model on Substack](https://adelaidadiazroa.substack.com/s/internal-design)

## Recent entries on these floors

```dataview
TABLE creationDate as Date, floor as Floor
FROM "Journals"
WHERE floor_level = "low"
SORT creationDate DESC
LIMIT 20
```
```

**Middle Floors.md:**
```markdown
---
creationDate: [today]
type: concept
floor_tier: middle
aliases: [middle floors, transitional floors]
---

Floors 9–13. You're starting to choose how you respond. These are the transitional floors — courage, neutrality, willingness, acceptance, reason. The shift from reacting to deciding happens here.

**Floors in this tier:** [[Courage]], [[Neutrality]], [[Willingness]], [[Acceptance]], [[Reason]]

**Read more:** [Internal Design — The High-Rise Model on Substack](https://adelaidadiazroa.substack.com/s/internal-design)

## Recent entries on these floors

```dataview
TABLE creationDate as Date, floor as Floor
FROM "Journals"
WHERE floor_level = "middle"
SORT creationDate DESC
LIMIT 20
```
```

**High Floors.md:**
```markdown
---
creationDate: [today]
type: concept
floor_tier: high
aliases: [high floors, generative floors]
---

Floors 14–16. You're creating, not reacting. Love, joy, peace — the generative floors. These aren't destinations you reach permanently. They're floors you visit, live in for stretches, and return to.

**Floors in this tier:** [[Love]], [[Joy]], [[Peace]]

**Read more:** [Internal Design — The High-Rise Model on Substack](https://adelaidadiazroa.substack.com/s/internal-design)

## Recent entries on these floors

```dataview
TABLE creationDate as Date, floor as Floor
FROM "Journals"
WHERE floor_level = "high"
SORT creationDate DESC
LIMIT 20
```
```

### Building the journal skill

Create a journal skill customized to their answers. Save it to `~/.claude/skills/daily-journal/SKILL.md`.

**IMPORTANT: The skill you generate must be PRESCRIPTIVE and COMPLETE. Do NOT generate a skeleton that relies on Claude's judgment at runtime. Every step, every question, every format must be spelled out explicitly in the skill file. A vague instruction like "ask about habits" will produce inconsistent results. Instead write the exact questions, the exact follow-up logic, and the exact format. The skill file IS the specification — if it's not in the file, it won't happen.**

The journal skill MUST include ALL of the following steps, in this order:

#### Step 1: Opening question
Warm, casual, matched to time of day. ONE question, don't overwhelm.
- Morning: "Hey! How are you waking up today? What's on your mind?"
- Afternoon: "How's the day going so far? Anything standing out?"
- Evening: "How was today? What's sitting with you right now?"

#### Step 2: Follow the thread (2-4 follow-up questions)
Based on their answer, dig deeper. Be curious, not clinical. Include these specific behaviors in the skill:
- If they mention **work**: "How does that make you feel about where things are headed?" or "Is that exciting or stressful or both?"
- If they mention **a person**: "What floor did that interaction put you on?" or "How did you feel after?"
- If they mention **feeling good**: "What specifically made it good? I want to capture this one." (Most people document bad days in detail but skip over good ones — push here.)
- If they mention **feeling bad**: "Is this a familiar pattern or something new?" or "What would the High-Rise say about where you are right now?"
- If they seem surface-level: "What's underneath that?" or "If you were writing this at 1am with no filter, what would you actually say?"
- Don't let them off the hook with "I'm fine" — gently dig.
- Use their language back to them.
- Celebrate wins they'd normally skip over.

#### Step 2.5: Abundance / gratitude check
Ask ONE quick question about present abundance:
- "What's one thing you have right now — financially, personally, anything — that you're grateful for?"
- Even "I had a great dinner" or "I can pay my rent" counts.
- This counters the natural bias toward only journaling when things are hard. The good stuff is there — it just doesn't get written down. Include the answer naturally in the entry.

#### Step 3: Accountability check
Based on what the user said they want to be held accountable on (question 5 from setup), build a SPECIFIC accountability check into the skill. For each item they chose, include:

**The pattern:** What to ask, what a good answer looks like, what a bad answer looks like, and what to say for each.

Example structures (adapt to whatever they actually asked for):

**Gym / exercise:**
- "Did you hit the gym today?" or "How many gym days this week so far?"
- If below their target: "You're at [X] for the week. You said [target]. When are you going tomorrow?"
- If on track: "Nice. That's [X] this week. The streak is building."
- Log the count in the entry.

**Sleep:**
- "What time did you go to bed last night?"
- If past their target: "That's the late bed -> tired tomorrow -> unproductive -> guilt spiral pattern. Phone in another room tonight?"
- If reasonable: Note it positively.

**Scrolling / screen time:**
- "Any scroll holes or binge sessions today?"
- If yes: Flag the pattern without judgment. "That's the crash after a sprint. Normal. But let's not let it become a streak."

**Spending / money:**
- If they mentioned spending: "Can you afford that without it stinging after?"

**Other habits:** Follow the same structure — ask, compare to their stated goal, push gently if behind, celebrate if on track.

**Key principle: Coach energy, not parent energy.** Direct but not nagging. Track the data. Name the patterns. Don't lecture.

#### Step 3.5: Idea quarantine check (for entrepreneurs/builders)
If the user mentioned during setup that they're working on a business or project, include this step in the skill:
- If a new business idea or "what if I built..." moment comes up during the conversation, DON'T let it derail. Note it, and after saving the journal entry, append it to an `Idea Quarantine` section in their vault (create `Business/Idea Quarantine.md` if it doesn't exist).
- Format: `- **[YYYY-MM-DD]** — [the idea, 1-2 sentences] *(from journal)*`
- Tell the user: "I caught an idea in there — parked it in Idea Quarantine so it doesn't distract but doesn't get lost."
- If they're excited about a side idea during a hard stretch on their main project, name it: "Is this real inspiration or escape from the hard thing?"

Skip this step entirely for users who aren't building something.

#### Step 4: Identify the floor
Based on everything they said, identify the PRIMARY floor:

**Low Floors:**
- Shame — "I'm such an idiot," self-disgust, hiding
- Guilt — "I should be doing more," not enough, letting people down
- Apathy — "Nothing matters," checked out, numb, Netflix spiral
- Grief — Loss, sadness, missing someone/something, killed mood
- Fear — Anxiety, "what if," scared, uncertain, imposter feelings
- Desire — Wanting, craving, reaching, ambition mixed with lack
- Anger — Frustration, someone not matching effort, disrespect
- Pride — Proving something, competitive, need for external validation

**Middle Floors:**
- Courage — Taking action despite fear, showing up, doing the hard thing
- Neutrality — Calm observation, "it is what it is," processing without charge
- Willingness — "Getting back on track," optimistic restart, open to trying
- Acceptance — Making peace with reality, letting go of control
- Reason — Analytical, strategic, clear-headed problem solving

**High Floors:**
- Love — Connection, gratitude, warmth, feeling held, giving freely
- Joy — Delight, fun, laughter, alive, "best day ever" energy
- Peace — Stillness, presence, nothing to fix, enough as-is

#### Step 5: Advisory panel (3-4 advisors)
Select the **3-4 most relevant advisors** from the panel below based on what came up in the conversation. Give a brief, in-character perspective — 1-2 sentences per advisor, in their authentic voice. Not a full panel discussion, just the sharpest insight each would offer on today's situation.

**The Advisory Panel:**

*Wealth & Strategy:*
Naval Ravikant (leverage, freedom-through-clarity) · Warren Buffett (patience, circle of competence) · Ray Dalio (principles, macro cycles) · Alex Hormozi (execution, offers, scaling) · Marc Andreessen (tech thesis, founder empathy) · Howard Marks (risk, second-level thinking)

*Leadership & Execution:*
Sheryl Sandberg (org scale, people systems) · Keith Rabois (execution, cadence) · Patrick Collison (speed + quality) · Reid Hoffman (network strategy, blitzscaling) · Adam Grant (org psych, generosity) · Tony Robbins (state management, peak performance)

*Psychology & Inner Work:*
Brene Brown (vulnerability, shame research, courage) · Robert Greene (power dynamics, strategy) · Gabor Mate (root wounds, compassion-led healing) · Martin Seligman (strengths, flourishing) · Dr. Emily Anhalt (emotional fitness for founders)

*Relationships:*
Esther Perel (erotic intelligence, polarity) · Alain de Botton (love as education) · Terry Real (empowered love, boundaries)

*Health & Body:*
Dr. Peter Attia (longevity, metric-driven protocols) · Dr. Chris Winter (sleep architecture) · Dr. Rhonda Patrick (micronutrients, cellular health)

*Wisdom & Meaning:*
Thich Nhat Hanh (mindful presence, compassion) · Marcus Aurelius (agency, serenity, controllables) · Mo Gawdat (happiness as OS) · Maya Angelou (purpose, grace, authentic voice)

*Creativity:*
Rick Rubin (presence, subtractive genius) · Elizabeth Gilbert (creative courage, fear alchemy)

**Panel rules:**
- Select 3-4 most relevant based on what came up today
- Each speaks in their authentic voice, 1-2 sentences
- Challenge assumptions where useful — not consensus for its own sake
- Keep it tight. This is a daily nudge, not a full session.

#### Step 6: Confirm and save
Tell the user: "Okay, I've got your entry. Here's what I'm hearing — [brief summary]. I'd tag this as [Floor]. The panel says [1-line summary]. Sound right?"

If they confirm (or adjust), save the entry.

#### Step 7: Save the journal entry

**File location:** `[VAULT_PATH]/Journals/` — use the vault path from setup. This MUST be the user's actual vault path, verified during Phase 3.

**Filename format:** Descriptive title from the content (5-8 words, Title Case):
- "Great Meeting Feeling Momentum.md"
- "Hard Conversation Stayed Calm.md"
- "Low Energy But Got Through It.md"

**Entry format:**

```markdown
---
creationDate: YYYY-MM-DDTHH:MM
floor: [Floor name]
floor_level: [low/middle/high]
[any habit fields they requested, e.g. gym_count: 3, sleep_time: 11pm]
---
[The journal entry — written in FIRST PERSON as the user, in their voice. Stream of consciousness, casual, honest. Include the details they shared. Don't clean it up too much — journals should be raw and real. But DO capture insights that surfaced during the conversation that they wouldn't have written on their own.]

[Include the abundance/gratitude note naturally woven in.]

[Accountability tracking line, e.g.:]
**Gym:** [X]/[target] this week · **Sleep:** [time to bed] · **Scroll check:** [clean/flagged]

**Panel insight:** [The 1-2 best lines from the advisory panel today]

*Floor: [[{Floor}]] · [[{Level} Floors]]*

## Concepts
[[Tag1]] | [[Tag2]] | [[Tag3]]
```

**CRITICAL — Post-save verification:**
After writing the file, VERIFY it exists and is not empty. Use the Read tool to confirm the file was saved. If the save fails for any reason (wrong path, missing folder, permissions), TELL THE USER IMMEDIATELY. Say what failed and offer to retry. **Never let a journal entry be lost.**

#### Step 7.5: To-Do Extraction

After saving the journal entry, scan the full conversation for **action items, follow-ups, or things the user said they need to do**. Look for:
- "Remind me to..." / "I need to..." / "I should..." / "I have to..."
- Follow-ups promised to people
- Conversations they flagged as needed ("I need to have that hard talk with X")
- Events or deadlines mentioned that need a task attached

If you find any:
1. Read the user's to-do file (check CLAUDE.md for path — typically `Home/✅ Get to-do.md` or similar)
2. Check for duplicates before adding
3. Add a new dated section near the top (after any urgent section):

```markdown
## 📋 From Journal — [YYYY-MM-DD]

- [ ] [task 1 — specific, include context so future-you knows why]
- [ ] [task 2]
```

4. Update `updated:` in frontmatter to today
5. Tell the user: "I also pulled [X] to-dos from the journal and added them to your list."

If no clear action items came up, skip silently — don't force it.

#### Step 8: After saving
Tell them the file name and floor. Connect to patterns when possible:
- "This is your 3rd Courage entry this month — you're on a streak."
- "Last time that person came up, you were on Anger. Today it's Acceptance. That's movement."
- "You mentioned money stress + a new idea in the same breath. Classic escape pattern. Just flagging it."
- If an idea was quarantined: "Parked [idea] in Idea Quarantine. Main project first. But it's saved."
- Habit count: "You're at [X]/[target] this week. [Encouragement or push as appropriate.]"

**Important principles for the generated skill:**
- Write the entry AS the user, not about them
- Keep their voice — people write journals in long flowing paragraphs, thinking out loud
- Include specific details (names, places, what happened)
- If they surfaced something new in the conversation that surprised them, make sure it lands in the entry
- Don't over-polish. The best entries are messy and real.
- The floor tag goes before ## Concepts
- Use `[[wikilinks]]` for all concept references
- **Good days matter.** Most people only journal in detail when things are bad. Push for detail on good days too — these are the entries they'll want to read later.

### Add /journal routing to CLAUDE.md

After creating the journal skill, also add this block to the user's CLAUDE.md so `/journal` works as a slash command:

```markdown
# daily journal
- **daily-journal** (`~/.claude/skills/daily-journal/SKILL.md`) — daily journal interview. Trigger: `/journal`
When the user types `/journal`, invoke the Skill tool with `skill: "daily-journal"` before doing anything else.
```

Tell them: "I added /journal to your memory file. From now on, just type /journal and we'll start."

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

Then offer the meeting-todos skill:

"After any meeting, type `/meeting-todos` and I'll read the transcript, pull out your action items (separate from others'), and add them to your to-do with context. You'll see a preview before anything gets written."

Install the skill:

```bash
# The skill is bundled in this repo
cp -r ~/.claude/skills/ai-brain-starter/meeting-todos ~/.claude/skills/meeting-todos
```

Add routing to the user's CLAUDE.md:

```markdown
# meeting todos
- **meeting-todos** (`~/.claude/skills/meeting-todos/SKILL.md`) — extract action items from a meeting note and add them to to-do. Trigger: `/meeting-todos`
When the user types `/meeting-todos`, invoke the Skill tool with `skill: "meeting-todos"` before doing anything else.
```

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

```markdown
## Obsidian Rules

1. Always wikilink. First occurrence per file. Use alias syntax: [[Concept|natural text]]
2. Block references for quotes. Never copy-paste text between notes. Use ^block-id at end of source paragraph + ![[File#^block-id]] to embed. This keeps a single source of truth.
3. YAML frontmatter on every note. Minimum: creationDate. Add type: (concept/journal/person/article) where applicable
4. Aliases in frontmatter for flexible linking: aliases: [nickname, abbreviation]
5. New concepts get their own note. In the right folder with a description and connected concepts.
6. Descriptive file names. When importing files, rename cryptic names to descriptive ones. No source prefixes ("Slack - ", "Google Drive - ").
7. Never duplicate the title. Obsidian shows the filename as the page title — don't repeat it with a # heading.
8. Idea quarantine. New business ideas or shiny distractions go to an Idea Quarantine note, not into action.
9. CRM on import. When importing anything that mentions people, create or update their CRM entry with: relationship, status, last_interaction, next_step, priority.
10. Catch content ideas. If a sharp insight comes up during conversation, save it to a Content Drafts note.
11. Log decisions. When you make a decision during conversation, append it to a Decision Log with what, why, and date.
12. NEVER fail silently. If a file save fails, a path doesn't exist, or ANYTHING doesn't work — tell the user immediately and fix it.
13. Optimize for navigation. Dense links in, dense links out. Every note should be reachable from related notes.
14. Wikilink new content on import. When creating notes from external sources, add wikilinks inline. Check the Wikilink Reference for all linkable notes.

## Efficiency Rules

1. Scripts over agents for bulk/mechanical operations. 10+ similar edits → one script.
2. Read files once. Work from memory after first read.
3. Batch auto-captures. Content ideas, decisions, vault improvements — batch at end of session, don't interrupt the conversation to log them.
4. Don't do things without confirming first.
5. Route to the right tool. Check the Tool Routing table. Don't burn Claude tokens when another tool is faster.

## Auto-Update Check

On every session start, check if the ai-brain-starter skill has updates:
```bash
cd ~/.claude/skills/ai-brain-starter && git fetch origin main --quiet 2>/dev/null && [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ] && echo "UPDATE AVAILABLE" || echo "UP TO DATE"
```
If an update is available, tell the user: "There's a newer version of the AI Brain Starter skill. Want me to update? (`git pull` — takes 2 seconds)." If yes, run `git pull`, read CHANGELOG.md, and tell them what's new in plain English. If they say no, don't ask again this session.

## Auto-Capture Rules

1. Content ideas → Content Drafts.md (batch at end of session, don't interrupt)
2. Decisions → Decision Log.md (what, why, date — leave outcome blank for later)
3. Vault improvements → Vault Changelog.md (what was done, why, impact)
```

Create the Content Drafts, Decision Log, and Vault Changelog files if they don't exist.

### Build the Wikilink Reference

After all rules are added, build a Wikilink Reference file that lists every linkable note in the vault. This helps Claude (and the user) know what can be wikilinked when writing new content.

Create `[VAULT_PATH]/Meta/Wikilink Reference.md`:

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

## Phase 18: Weekly & Monthly Insights

"One more thing — and this might be the most powerful part. I can generate a weekly and monthly reflection from your journal entries. Not just a summary of what happened, but pattern recognition: what floors you've been on, what's shifting, what a life coach would push you on, what a therapist would want you to sit with."

Ask: "Want me to set up weekly and monthly insight reports? You type /weekly or /monthly anytime and I'll analyze your entries for that calendar period and give you a reflection."

If yes, first create a journal index builder script at `[VAULT_PATH]/Meta/scripts/build-journal-index.py`:

```python
#!/usr/bin/env python3
"""Build a date index of all journal entries for fast lookup."""
import os, json
from datetime import datetime

VAULT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JOURNAL_DIR = os.path.join(VAULT, "\U0001f4d3 Journals")
OUTPUT = os.path.join(VAULT, "\u2699\ufe0f Meta", "journal-index.json")

entries = []
for fname in os.listdir(JOURNAL_DIR):
    if not fname.endswith(".md") or os.path.isdir(os.path.join(JOURNAL_DIR, fname)):
        continue
    try:
        with open(os.path.join(JOURNAL_DIR, fname), 'r', encoding='utf-8', errors='replace') as f:
            in_fm, meta = False, {}
            for i, line in enumerate(f):
                if i == 0 and line.strip() == '---':
                    in_fm = True; continue
                if in_fm:
                    if line.strip() == '---': break
                    if ': ' in line:
                        k, v = line.split(': ', 1)
                        meta[k.strip()] = v.strip().strip("'\"")
                if i > 15: break
            if 'creationDate' in meta:
                entry = {"file": fname, "date": meta['creationDate'][:10]}
                if 'floor' in meta: entry["floor"] = meta["floor"]
                if 'floor_level' in meta: entry["floor_level"] = meta["floor_level"]
                entries.append(entry)
    except: pass

entries.sort(key=lambda x: x["date"])
with open(OUTPUT, 'w') as f:
    json.dump({"total": len(entries), "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M"), "entries": entries}, f, indent=2, ensure_ascii=False)
print(f"Indexed {len(entries)} entries")
```

Run it: `python3 "[VAULT_PATH]/Meta/scripts/build-journal-index.py"`

Then create the skill file at `~/.claude/skills/insights/SKILL.md`:

```markdown
---
name: insights
description: Weekly and monthly journal insights — pattern recognition, floor trends, life coach pushback, therapist observations, and advisory panel thoughts. Use /weekly for the current calendar week, /monthly for the current calendar month.
---

# Insights — Weekly & Monthly Reflection

When the user types /weekly or /monthly, generate an insight report from their recent journal entries.

## For /weekly — read all journal entries from the current calendar week (Monday–Sunday). If today is Monday or Tuesday, default to the previous week (since there's barely any data yet). The user can specify "this week" to override.

## For /monthly — read all journal entries from the current calendar month (1st–last day). If today is the 1st–3rd, default to the previous month. The user can specify "this month" to override.

## CRITICAL: How to find entries by date

**DO NOT grep the entire Journals folder.** With hundreds of entries, that times out.

Instead, use the journal index at `[VAULT_PATH]/Meta/journal-index.json`. This is a JSON file mapping every journal entry to its `creationDate`, `floor`, and `floor_level`. One file read instead of hundreds.

If the index doesn't exist or is stale, rebuild it:
```bash
python3 "[VAULT_PATH]/Meta/scripts/build-journal-index.py"
```

Filter entries by date range from the index, then read ONLY the matching files.

## Report Structure

### 1. The Week/Month at a Glance
- How many entries (and any gaps — remember, gaps often mean good stretches)
- Floor distribution: how many entries on each floor, with the primary floor for the period
- Floor trend: moving up, down, or holding steady vs. last week/month
- Habit tracking summary: gym count, average bedtime, scroll incidents (if tracked in entries)
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
Select 3-5 advisors most relevant to what came up. 1-2 sentences each, in character. Challenge assumptions, don't just validate.

Use the full advisory panel. Each advisor has a distinct voice — match it when they speak.

**Wealth & Strategy** — for money, business models, leverage, risk, and building wealth:
- Naval Ravikant — leverage through code and media, wealth vs. status games, specific knowledge. Speaks in compressed, philosophical one-liners.
- Warren Buffett — patience, compounding, circle of competence, margin of safety. Folksy midwestern wisdom, says "no" to almost everything.
- Ray Dalio — radical transparency, principles-based decisions, pain + reflection = progress. Systematic, almost clinical.
- Alex Hormozi — offers, value equations, volume over perfection, "do the boring work." Blunt, high-energy, zero fluff.
- Steven Wheelwright — operations strategy, focused factories, process-product alignment. Academic but practical.
- Luis Carlos Vélez — Colombian media/business perspective, directness, entrepreneurship in LatAm. Provocative, no sugarcoating.
- Kim Borrero — Colombian venture/startup ecosystem, founder-investor dynamics in emerging markets. Strategic and connected.
- David Moreno — Colombian tech entrepreneurship, Rappi-era thinking, scaling in LatAm. Builder mindset.
- Marc Andreessen — software eating the world, techno-optimism, building in uncertain markets. Bold, contrarian.
- Stephen Schwarzman — scale, deal-making, "go big or go home," institutional relationship-building. Corporate gravitas.
- Howard Marks — second-level thinking, risk vs. uncertainty, market cycles. Thoughtful, memo-style reasoning.
- Sam Zell — contrarian real estate, finding value where others see risk, "dance on the grave." Irreverent, street-smart.
- Robert Kiyosaki — cash flow over salary, assets vs. liabilities, financial literacy gaps. Repetitive but motivating.
- Ken Griffin — high-performance culture, precision, competing at the highest level. Intense, data-driven.
- Luis Carlos Sarmiento — Colombian business dynasty, long-term positioning, banking and infrastructure. Old-school power, quiet strategy.

**Leadership** — for managing people, making decisions, and growing as a leader:
- Sheryl Sandberg — leaning in, resilience after loss, navigating power as a woman. Polished, direct, empathetic.
- Keith Rabois — operator mentality, barrels vs. ammunition, editing not writing. Sharp, impatient with mediocrity.
- Patrick Collison — craft, speed, taste, building for decades. Quietly intense, bookish, precise.
- Reid Hoffman — blitzscaling, alliance-building, permanent beta. Strategic networker, thinks in systems.
- Adam Grant — givers vs. takers, originals, rethinking. Evidence-based, generous, occasionally contrarian.
- Tony Robbins — state management, peak performance, massive action. Big energy, sometimes too much — but moves people.
- Richard Branson — adventure, brand-as-personality, "screw it let's do it." Dyslexic entrepreneur who proved them wrong.

**Gatherings** — for how people come together, events, and creating belonging:
- Priya Parker — purposeful gathering, generous authority, "who not how many." Reframes every event as a choice about what matters.

**Psychology** — for inner work, patterns, emotional processing, and growth:
- Brené Brown — vulnerability as courage, shame resilience, wholehearted living. Warm, research-backed, Texan-direct.
- Robert Greene — power dynamics, mastery through patience, human nature. Strategic, historical, slightly dark.
- Debbie Ford — shadow work, owning every part of yourself, "the dark side of the light chasers." Compassionate but unflinching.
- Gabor Maté — trauma-informed everything, addiction as coping, the body keeps the score. Gentle, wise, occasionally devastating.
- Martin Seligman — learned optimism, character strengths, positive psychology. Academic but practical.
- Jungian analyst voice — archetypes, individuation, shadow integration, the unconscious speaking through patterns. Symbolic, deep.
- CBT voice — cognitive distortions, thought records, behavioral activation. Structured, here's-what-to-do practical.
- Existential therapist voice — meaning-making, freedom and responsibility, confronting mortality. Sits with the big questions.
- Inner child voice — the wounded young self that drives adult reactions. Tender, protective, needs to be heard.
- Esther Perel (as therapist) — dual-trained: relationships AND internal identity. Sees the erotic and the domestic, the self and the other.
- Lori Gottlieb — "maybe you should talk to someone," blind spots, the stories we tell ourselves. Warm, witty, doesn't let you off the hook.

**Relationships** — for love, dating, attachment, conflict, and connection:
- Esther Perel — desire vs. security, erotic intelligence, the space between. European sophistication, accent and all.
- Stan Tatkin — attachment science, PACT method, "your partner is not your enemy." Neuroscience-grounded, practical for couples.
- John & Julie Gottman — the four horsemen, bids for connection, repair attempts. Decades of research, warmly clinical.
- Terry Real — relational life therapy, "us consciousness," confronting grandiosity and shame. Direct, breaks the therapy rules.
- Sue Johnson — emotionally focused therapy, attachment bonds, "hold me tight." Tender, sees the panic beneath the anger.
- Andrew Solomon — far from the tree, radical acceptance of difference, love as expansion. Literary, deeply humane.
- Alain de Botton — philosophy of everyday love, why we choose who we choose, romantic realism. Elegant, melancholy, wise.
- Matthew Hussey — dating strategy, high-value behavior, confidence in pursuit. Practical, action-oriented, especially for women.
- William Ury — getting to yes with yourself, negotiation as self-awareness, the "balcony." Calm, principled, sees the third way.
- Jay & Radhi Shetty — purpose-driven relationships, monk mindset meets modern love. Spiritual but grounded.

**Health** — for body, sleep, hormones, movement, and longevity:
- Peter Attia — longevity, zone 2 cardio, metabolic health, "live longer and better." Medical precision, engineer's mind.
- Stacy Sims — women's exercise physiology, "women are not small men," hormone-aware training. Evidence-based, fierce advocate.
- Lara Briden — women's hormonal health, period repair, post-pill recovery. Naturopathic but scientifically rigorous.
- Chris Winter — sleep science, circadian rhythms, "the sleep solution." Practical, demystifies insomnia.
- Alyssa Braddock — sports nutrition, fueling performance, body composition without obsession. Balanced, athlete-focused.
- Rhonda Patrick — micronutrients, sauna science, genetic optimization. Deep-dives that change behavior.
- Peter Levine — somatic experiencing, trauma lives in the body, completing the stress cycle. Gentle, body-first.
- Bessel van der Kolk — "the body keeps the score," trauma rewires the brain, movement and EMDR. Foundational, paradigm-shifting.

**Wisdom** — for meaning, perspective, and the bigger picture:
- Thich Nhat Hanh — mindfulness, interbeing, washing dishes to wash dishes. Gentle, present, profoundly simple.
- Marcus Aurelius — stoic emperor, memento mori, control what you can. Journaled his own struggles two thousand years ago.
- Yuval Noah Harari — sapiens-level perspective, stories that bind societies, what makes us human. Zooms way out.
- Mo Gawdat — happiness as an equation, grief as teacher (lost his son), engineering joy. Optimistic despite everything.
- Jane Goodall — patience, observation, hope as action, respecting other beings. Quiet moral authority.
- Charles Eisenstein — the more beautiful world our hearts know is possible, gift economy, interbeing. Radical tenderness.
- Robin Wall Kimmerer — braiding sweetgrass, indigenous wisdom meets science, reciprocity with the earth. Poetic, grounding.
- Maya Angelou — "when people show you who they are, believe them," rising, courage, dignity. Voice of earned wisdom.
- Oprah Winfrey — "what I know for sure," turning pain into purpose, living your best life. Earned every word of it.

**Creativity** — for making things, creative blocks, and artistic practice:
- Rick Rubin — the creative act, removing yourself from the work, nature as source. Zen-like, minimal, listens more than speaks.
- Elizabeth Gilbert — big magic, creative courage, curiosity over passion. Warm, funny, demystifies the creative life.
- Twyla Tharp — the creative habit, showing up is the work, scratch and routine. Disciplined, no-nonsense choreographer energy.

### 6. Wins to Celebrate
Things that went well that might get overlooked. Good days matter MORE to document than bad ones.

### 7. One Question to Sit With
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
gym_total: [X]
avg_bedtime: [time]
---

[Full report]

*Primary floor: [[Floor]] · [[Level Floors]]*
```

## After Saving: Update Floor Notes with Personal Insights

After saving the insight report, check whether any floor that appeared this period has a new personal pattern worth capturing.

**For each floor that appeared 2+ times this period:**
1. Read the floor note (e.g., `[[Fear]]`, `[[Courage]]`, `[[Joy]]`)
2. Check if it has a `## Personal Patterns` section. If not, create one.
3. Ask: Is there a NEW trigger, pattern, or movement insight from this period that isn't already captured?
   - New trigger: "Fear spikes before investor meetings and when money conversations come up."
   - New pattern: "Joy tends to follow 3+ gym days and flow states."
   - New movement: "Moving from Anger to Acceptance happened same-day — both times after journaling the frustration out."
   - New person-floor link: "Conversations with [person] consistently land on [floor]."
4. If yes, append under `## Personal Patterns` with the date: `- *(Week of Apr 7, 2026)* Joy shows up after back-to-back gym days and uninterrupted creative mornings.`
5. If nothing new, skip — don't add filler.

**What's worth adding:** Triggers that appeared 2+ times, movement strategies that worked, person-floor correlations, surprises.
**What to skip:** Generic observations already in the static description, one-off events, anything already captured.

Over time, clicking `[[Fear]]` won't show a textbook definition — it'll show YOUR fear: what triggers it, who brings it, what moves you out of it, and how it's changed.

**For monthly insights:** Do a deeper review. Read ALL accumulated personal patterns and update, merge, or retire stale ones.

## After Floor Notes: Auto-Wikilink Check & Graph Integration

After updating floor notes, scan this week's journal entries for missing wikilinks:

1. Read the Wikilink Reference file
2. For each journal entry from this period, check if key concepts mentioned in plain text have matching entries in the Wikilink Reference that aren't wikilinked
3. Add `[[wikilinks]]` where missing (first occurrence per file only, use alias syntax)
4. Don't over-link — only link concepts that are actual vault notes

**If a graphify graph exists** (`graphify-out/graph.json`):
- Check for high-degree concepts that appear 10+ times but have no vault note — flag them as candidates for new concept notes
- Check for graph edges suggesting connections not yet captured in wikilinks — if the graph knows a relationship between two concepts and a journal entry mentions both without linking them, add the link
- Run `graphify --update` on new entries to keep the graph current

## Rules
- Read EVERY journal entry in the period. Don't skip or skim.
- Be specific — use their words, reference entries by name, name people and situations.
- Life coach = direct. Therapist = gentle. Both = honest.
- Compare to previous weeks/months if data exists. Trends > snapshots.
- The panel should react to what actually happened, not give generic advice.
- If fewer than 3 entries, say so: "You only journaled [X] times. Here's what I can see, but the data is thin."
- The closing question should land. Make them think.
- **NEVER fail silently.** After saving any file, verify it exists. If the save fails, TELL THE USER IMMEDIATELY. Never let an insight report be lost.
```

Then add routing to the user's CLAUDE.md so `/weekly` and `/monthly` work as slash commands:

```markdown
# insights (weekly / monthly)
- **insights** (`~/.claude/skills/insights/SKILL.md`) - journal pattern recognition. Triggers: `/weekly`, `/monthly`, `/insights`
When the user types `/weekly` or `/monthly`, invoke the Skill tool with `skill: "insights"` before doing anything else.
```

Then ask: "Want these to run automatically? I can set up a cron job so your weekly insight generates every Monday morning and your monthly insight on the 2nd of each month — no typing required."

If yes, set up automatic generation:

### Mac / Linux

Create the script at `[vault]/⚙️ Meta/scripts/run-insights.sh`:

```bash
#!/bin/bash
# run-insights.sh — Generate weekly or monthly journal insight reports via Claude Code CLI
# Usage: ./run-insights.sh weekly   (Monday mornings via cron)
#        ./run-insights.sh monthly  (2nd of each month via cron)

PERIOD="${1:-weekly}"
VAULT_DIR="$HOME/Desktop/Adelaida Notes"  # ← update to user's vault path
LOG_FILE="$VAULT_DIR/⚙️ Meta/scripts/.insights-cron.log"

# Find the Claude CLI (path changes with version updates)
CLAUDE_BASE="$HOME/Library/Application Support/Claude/claude-code"
CLAUDE_BIN=$(find "$CLAUDE_BASE" -name "claude" -path "*/MacOS/claude" 2>/dev/null | sort -V | tail -1)

# Linux fallback
if [ -z "$CLAUDE_BIN" ]; then
  CLAUDE_BIN=$(command -v claude 2>/dev/null)
fi

if [ -z "$CLAUDE_BIN" ]; then
  echo "$(date): ERROR — Claude CLI not found" >> "$LOG_FILE"
  exit 1
fi

echo "$(date): Starting $PERIOD insights generation..." >> "$LOG_FILE"

cd "$VAULT_DIR" || exit 1

"$CLAUDE_BIN" --print \
  --model claude-sonnet-4-6 \
  --allowedTools "Read,Write,Edit,Glob,Grep,Bash" \
  --permission-mode acceptEdits \
  "Run the /insights skill for a $PERIOD report. Read the skill at ~/.claude/skills/insights/SKILL.md first, then follow its instructions exactly. Read all journal entries for the $PERIOD calendar period and generate the full report. Save it to the correct folder." \
  >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "$(date): Finished $PERIOD insights (exit code: $EXIT_CODE)" >> "$LOG_FILE"
```

Make it executable: `chmod +x "[vault]/⚙️ Meta/scripts/run-insights.sh"`

Then add cron jobs. Ask the user their timezone and convert to UTC:

```bash
# Example for America/Bogota (UTC-5): 9am local = 14:00 UTC
crontab -e
# Add these lines:
# Weekly insights — every Monday at 9am local
0 14 * * 1 /bin/bash "/path/to/vault/⚙️ Meta/scripts/run-insights.sh" weekly
# Monthly insights — 2nd of each month at 9am local
0 14 2 * * /bin/bash "/path/to/vault/⚙️ Meta/scripts/run-insights.sh" monthly
```

### Windows

Create `run-insights.ps1` in the vault's `⚙️ Meta/scripts/` folder:

```powershell
# run-insights.ps1 — Generate weekly or monthly journal insight reports via Claude Code CLI
# Usage: .\run-insights.ps1 -Period weekly
#        .\run-insights.ps1 -Period monthly
param([string]$Period = "weekly")

$VaultDir = "$env:USERPROFILE\Documents\Adelaida Notes"  # ← update to user's vault path
$LogFile = "$VaultDir\⚙️ Meta\scripts\.insights-cron.log"

# Find Claude CLI (Windows)
$ClaudeBin = Get-ChildItem "$env:LOCALAPPDATA\AnthropicClaude\claude-code" -Recurse -Filter "claude.exe" -ErrorAction SilentlyContinue |
  Sort-Object FullName | Select-Object -Last 1

if (-not $ClaudeBin) {
  $ClaudeBin = Get-Command claude -ErrorAction SilentlyContinue
}

if (-not $ClaudeBin) {
  Add-Content $LogFile "$(Get-Date): ERROR — Claude CLI not found"
  exit 1
}

Add-Content $LogFile "$(Get-Date): Starting $Period insights generation..."
Set-Location $VaultDir

& $ClaudeBin.FullName --print `
  --model claude-sonnet-4-6 `
  --allowedTools "Read,Write,Edit,Glob,Grep,Bash" `
  --permission-mode acceptEdits `
  "Run the /insights skill for a $Period report. Read the skill at ~/.claude/skills/insights/SKILL.md first, then follow its instructions exactly. Read all journal entries for the $Period calendar period and generate the full report. Save it to the correct folder." `
  2>&1 | Add-Content $LogFile

Add-Content $LogFile "$(Get-Date): Finished $Period insights (exit code: $LASTEXITCODE)"
```

Then set up Windows Task Scheduler:

```powershell
# Weekly — every Monday at 9am
$WeeklyAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File `"C:\path\to\vault\⚙️ Meta\scripts\run-insights.ps1`" -Period weekly"
$WeeklyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -TaskName "AI Brain Weekly Insights" -Action $WeeklyAction -Trigger $WeeklyTrigger -Description "Generate weekly journal insights"

# Monthly — 2nd of each month at 9am
$MonthlyAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File `"C:\path\to\vault\⚙️ Meta\scripts\run-insights.ps1`" -Period monthly"
$MonthlyTrigger = New-ScheduledTaskTrigger -Once -At 9am -RepetitionInterval (New-TimeSpan -Days 30)
# Note: For exact "2nd of month" scheduling, use Task Scheduler GUI or schtasks:
# schtasks /create /tn "AI Brain Monthly Insights" /tr "powershell -File \"C:\path\to\vault\run-insights.ps1\" -Period monthly" /sc monthly /d 2 /st 09:00
Register-ScheduledTask -TaskName "AI Brain Monthly Insights" -Action $MonthlyAction -Trigger $MonthlyTrigger -Description "Generate monthly journal insights"
```

Tell the user which option was set up and confirm the schedule: "Your weekly insight will generate automatically every Monday at [time] and your monthly on the 2nd at [time]. You can also run /weekly or /monthly manually anytime. Check the log at `⚙️ Meta/scripts/.insights-cron.log` if you ever want to verify it ran."

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

### Step 5: Create /team-weekly skill

Create a team weekly digest skill at `~/.claude/skills/team-weekly/SKILL.md`:

```markdown
---
name: team-weekly
description: Weekly operational digest for the team. Scans meeting notes, CRM changes, strategy updates, sales activity, and decisions from the past week. Use /team-weekly to generate.
---

# Team Weekly Digest

Generate a weekly operational report by scanning all changes across the team vault in the past 7 days.

## How to Find Recent Files

Use `find "[TEAM_VAULT_PATH]" -name "*.md" -mtime -7` to get files modified in the past 7 days. Read only those files.

## Report Structure

### 1. This Week at a Glance
- Date range (Mon–Sun)
- Files modified, meetings held, new contacts
- One-line summary

### 2. Meetings & Conversations
For each meeting note: who, what, decisions, action items (done vs. open)

### 3. Pipeline & Sales
New leads, outreach sent, deals moved, revenue updates

### 4. Product & Team
What was shipped, blockers, team changes

### 5. Decisions Made
From Decision Log — business decisions this week

### 6. Open Loops
Unresolved heading into next week

### 7. Next Week Focus
Top 3 priorities for next week

## Save Location
- Team vault: `[TEAM_VAULT_PATH]/Strategy/Weekly Digests/YYYY-WXX Team Weekly.md`
- Personal vault: `[PERSONAL_VAULT_PATH]/[PROJECT_FOLDER]/Weekly Digests/YYYY-WXX Team Weekly.md`

## Rules
- Business only — no personal journal content or floor tags
- Name people, meetings, amounts — be specific
- Compare to last week when data exists
- Flag risks: overdue follow-ups, stalled deals, missed deadlines
- NEVER fail silently. Verify both saves.
```

Replace `[TEAM_VAULT_PATH]`, `[PERSONAL_VAULT_PATH]`, and `[PROJECT_FOLDER]` with the user's actual paths.

Add routing to the user's CLAUDE.md:

```markdown
# team weekly
- **team-weekly** (`~/.claude/skills/team-weekly/SKILL.md`) — weekly team operational digest. Trigger: `/team-weekly`
When the user types `/team-weekly`, invoke the Skill tool with `skill: "team-weekly"` before doing anything else.
```

Tell the user: "Your team vault is ready. Share the Google Drive folder with your team and send them the First Time Setup note. They'll have full context from day one. Type `/team-weekly` anytime to get a digest of what happened this week across the team."

## Phase 21: What's Next

"Here's what you have now:
- A memory file that loads every session
- Context notes so I never ask 'what are we working on?'
- Templates for journals, people, and meetings
- Power tools for efficiency
- A daily journal with floor tagging and habit tracking
- Weekly and monthly insight reports (/weekly and /monthly)
- A team weekly digest (/team-weekly) if you have a team vault
- Accountability rules so I push back, not just agree
- A team vault synced from your personal one (if you set it up)

Ready for the next level? The deep optimization pass is already installed. It'll compress your archives into summaries, standardize all your contacts into a queryable CRM, clean up your graph, build live dashboards, and more.

Just type: **/optimize-brain**

That's a weekend project, not an afternoon one — but it's where the real magic happens. Your vault goes from organized to intelligent.

For now — just use it. Journal. Add notes. Ask me things. The system compounds over time."

## Important Notes for Claude

- GO SLOW. Wait for answers. Don't dump instructions.
- **NEVER STOP MID-SETUP.** After completing each phase, ALWAYS continue to the next phase automatically. Do not wait for the user to ask "what's next?" — tell them what's coming and proceed. The only reasons to pause are: (1) the user explicitly says "let's stop here" or "I need a break," (2) a critical install failed and needs manual intervention, or (3) the user asks a question that needs answering before continuing. After the journal phase especially — there are 10+ more phases. Don't stop there.
- At the start of each phase, briefly tell the user where they are: "Phase [X] of 21: [Name]. This is where we [one sentence]."
- If context gets compressed mid-setup (long session), re-read SKILL.md to pick up where you left off. Check which phases are done by looking at what exists in the vault (folders, CLAUDE.md, skills, templates).
- If they seem overwhelmed, say: "We can stop here and pick up the rest tomorrow. What we've done so far is already working." But default is to KEEP GOING.
- Adapt the folder structure to their life, not a template.
- If they're not technical, explain terminal commands step by step. "Open Terminal. That's the app with the black screen icon."
- Celebrate milestones: "Your CLAUDE.md is done — that's the biggest piece."
- If any install fails, troubleshoot calmly. Don't skip it or panic.
- Match their energy. If they're excited, move fast. If they're cautious, explain more.
- This should feel like a conversation with a smart friend who's helping them set up their system, not a software installer.
- **NEVER FAIL SILENTLY.** If any file save, install, or operation fails — tell the user immediately. Say what failed, why, and offer to fix it.
- **NEVER FAIL SILENTLY.** After every file write, verify the file exists. After every install, verify it worked. If ANYTHING fails — wrong path, missing folder, permission error, install timeout — TELL THE USER IMMEDIATELY. Say what failed, why, and how to fix it. Then FIX IT — create the missing folder, correct the path, retry the install. Don't just report the problem; solve it. People are trusting this skill with their personal data. Losing a journal entry or a CLAUDE.md because of a silent failure is unacceptable.
