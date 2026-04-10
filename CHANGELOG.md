---
name: changelog
description: What's new in AI Brain Starter — plain English, no jargon
---

# What's new

*Every time you update (`git pull` or tell Claude "update the ai-brain-starter skill"), check here to see what changed and why.*

---

## April 10, 2026 (evening)

### Journal skill completely rewritten — the biggest update yet
The journal skill template was a skeleton — it told Claude "include habit tracking" but didn't specify HOW. Now it's fully prescriptive with 8 explicit steps: opening question, deep follow-up logic, abundance/gratitude check, accountability check with pushback loops, idea quarantine for entrepreneurs, floor identification with all 16 floors defined, 3-4 advisory panel reactions (up from 1-2) with the full panel built into the skill, and post-save verification so entries never get lost silently.

### New: Accountability check in journal
During setup, you're now asked: "Do you want me to hold you accountable on anything?" with examples like gym consistency, sleep time, scrolling habits, and spending patterns. Whatever you choose gets built into your journal skill with specific pushback logic — not just "did you work out?" but "You're at 2/4 this week. When are you going tomorrow?"

### New: 19 floor concept notes created during setup
When you opt into floor tagging, the setup now creates a concept note for each of the 16 floors plus 3 tier notes (Low, Middle, High Floors). Each floor note explains what it feels like, lists signals, suggests how to move up, and links back to the Substack article "The Internal High-Rise — Peace Is a Place You Can Live." Click [[Fear]] in a journal entry and you land on a page that shows you every entry you've ever written from that floor.

### New: Abundance/gratitude check in every journal entry
Counters the natural bias toward only journaling when things are hard. One quick question: "What's one thing you have right now that you're grateful for?" The answer gets woven into the entry naturally.

### New: Idea quarantine for entrepreneurs
If you're building something, the journal skill now catches side ideas mid-conversation and parks them in Business/Idea Quarantine.md instead of letting them derail your focus. Also flags escape patterns: "Is this real inspiration or escape from the hard thing?"

### New: /team-weekly — operational digest for team vaults
If you set up a team vault (Phase 20), the setup now creates a /team-weekly skill that generates a weekly operational digest: meetings, pipeline, sales, product updates, decisions, and open loops. Scans all files modified in the past 7 days across the team vault. Saves to both team and personal vault. Business only — no journals or personal content.

### Auto-update check on every session start
The skill now checks for updates automatically via a session hook — not just when you run /setup-brain. If a newer version exists on GitHub, Claude tells you and offers to update with one command. No manual checking needed.

### Vault Changelog, Content Drafts, and Idea Quarantine created during setup
Phase 5 now creates Vault Changelog.md (tracks what you build), Content Drafts.md (auto-captures sharp insights from conversations), and Idea Quarantine.md (parks business ideas so they don't derail your main focus). Previously these were referenced in the rules but never actually created.

### "Never fail silently" rule added to generated CLAUDE.md
Rule 11 in the Obsidian Rules section. If anything fails — file save, install, path issue — Claude must tell you immediately and fix it.

### Journal index for fast date lookups
New Python script at Meta/scripts/build-journal-index.py creates a JSON index of all journal entries by date. The insights skill reads this index instead of grepping hundreds of files — fixes the bug where /weekly and /monthly found wrong entry counts or timed out on large vaults.

### New: Living floor notes — updated by weekly/monthly insights
Floor concept notes now grow over time. After each /weekly or /monthly insight report, the insights skill checks if any floor that appeared 2+ times has a new personal pattern worth capturing — triggers, movement strategies, person-floor correlations, surprises. Appends them under a `## Personal Patterns` section on the floor note. Monthly insights do a deeper review and can update, merge, or retire stale patterns. Over time, clicking [[Fear]] shows YOUR fear patterns, not a textbook definition.

### Setup no longer stops mid-flow
Previously, Claude might stop after the journal phase and wait for you to ask "what's next?" Now it automatically continues through all 21 phases unless you explicitly say to pause.

### Phase 13 streamlined
Health & Habit Tracking was redundant with the journal skill. Now Phase 13 only covers importing external health data (Apple Health, Fitbit, etc.). Basic habit tracking is handled in Phase 10.

---

### Advisory panel reactions in daily journal
Your daily journal entries now get 1-2 advisor reactions after saving — short, in-character sentences from the same 50+ voice panel used in weekly/monthly insights. Instead of just saving and moving on, Claude picks the 1-2 advisors most relevant to what came up and gives you a quick outside perspective. It's like having Naval or Brene Brown read your journal entry and give you one sentence back.

### Example outputs added
New file: EXAMPLES.md. Shows exactly what a daily journal entry and a weekly insight report look like — full frontmatter, raw first-person journaling, floor tags, advisor reactions, life coach flags, therapist observations, and the closing question. Fictional but realistic. If you're wondering "what does this actually produce?" — now you can see it before committing to the setup.

### /journal routing in CLAUDE.md
The setup now adds `/journal` routing to your CLAUDE.md so it works as a slash command, just like `/weekly` and `/monthly` already do. Previously you had to remember to type the full skill name or hope Claude figured it out.

### Skill & routing health check in /optimize-brain
New Phase 10 in the optimization skill: verifies all your skills exist, all file paths resolve to real folders (catches the common double-Desktop bug), all slash commands are routed in CLAUDE.md, the session protocol hook is installed, and the advisory panel is present in both the journal and insights skills. Also fixed duplicate numbering in the phase list.

---

## April 9, 2026 (late night update)

### Session protocol hook — Claude reads your files BEFORE responding
The biggest reliability problem with the vault was that Claude sometimes greeted you before reading your CLAUDE.md, Last Session, and Current Priorities files — meaning it started the conversation without context. The fix: a `UserPromptSubmit` hook that fires on your very first message each session and forces Claude to read those files before saying anything. It's automatic — you don't have to ask. The hook fires once per session and self-removes. Setup-brain now installs this hook during Phase 5 (context layer).

### Calendar-based weekly & monthly periods
Weekly and monthly insights now use calendar periods instead of rolling windows. /weekly covers Monday–Sunday of the calendar week. /monthly covers the 1st through last day of the month. If it's early in the period (Monday/Tuesday for weekly, 1st–3rd for monthly), it defaults to the previous period so you have enough data. You can say "this week" or "this month" to override.

### /weekly and /monthly routing fix
The setup now adds routing to your CLAUDE.md so `/weekly` and `/monthly` work as direct slash commands. Previously only `/insights` was recognized.

### Full advisory panel with voice descriptions
Every advisor on the panel now has a description of who they are, what they're known for, and how they speak — so Claude actually sounds like them instead of giving generic advice. 50+ voices across 8 categories: wealth & strategy (Naval, Buffett, Dalio, Hormozi, Andreessen, and Colombian founders like Vélez, Borrero, Moreno), leadership (Sandberg, Rabois, Collison), psychology (Brené Brown, Gabor Maté, Jungian/CBT/existential/inner child voices), relationships (Perel, Gottmans, Terry Real, Sue Johnson), health (Attia, van der Kolk, Stacy Sims), wisdom (Thich Nhat Hanh, Marcus Aurelius, Maya Angelou), and creativity (Rick Rubin, Elizabeth Gilbert, Twyla Tharp). Each one challenges you differently.

### Richer insight reports
The weekly/monthly insight skill now includes: a "Wins to Celebrate" section so good days don't get overlooked, habit tracking in the frontmatter (gym count, average bedtime), and a "never fail silently" rule — if the report fails to save, Claude tells you immediately instead of losing it.

### Automatic insight generation (cron / Task Scheduler)
The setup now offers to schedule your weekly and monthly insights to run automatically — no typing required. On Mac/Linux it sets up a cron job; on Windows it creates a Task Scheduler entry. Weekly runs every Monday morning, monthly on the 2nd. Logs to `⚙️ Meta/scripts/.insights-cron.log` so you can verify it ran. You can still run /weekly or /monthly manually anytime.

---

## April 9, 2026 (night update)

### Weekly & Monthly Insight Reports
Type /weekly or /monthly anytime. Claude reads all your journal entries for that calendar period and gives you: floor trends (are you moving up or down?), patterns a life coach would flag ("you mentioned this person 4 times and each time your floor dropped"), observations a therapist would explore ("there's a thread of guilt running through this week you haven't named"), advisory panel thoughts on your week, and one question to sit with. Saves as a note so you can look back over months. It's like a therapist session, a life coach check-in, and a board meeting — on demand, from your own data.

### Team Vault Setup
If you have a team, Claude now walks you through creating a separate shared vault (synced through Google Drive or similar) that stays connected to your personal vault. Business files sync automatically. Personal stuff stays private. Team members get their own First Time Setup instructions. You work from your personal vault (which knows your whole life), they work from the team vault (which knows the business). No double-entry, no drift.

---

## April 9, 2026 (evening update)

### Efficiency tools install FIRST (Phase 0)
The setup now installs Graphify and Claude-Mem before the conversation starts, not after. This means the entire setup process uses fewer tokens — saving you money and making everything faster. Previously these were installed at Phase 9, after the vault was already built. Now they're running from the start.

### Windows + Linux support
Phase 0 now detects your operating system and gives the right install commands. Previously it was Mac-only. If you're on Windows, it walks you through downloading Python and Node.js. If you're on Linux, it uses your package manager.

### Obsidian CLI setup
If you're on Mac or Linux with Obsidian 1.12.7+, the setup now tries to enable the Obsidian CLI. This lets Claude search your vault, check backlinks, and find broken links much faster. If it's not available (Windows or older Obsidian), it skips silently — everything still works.

### Emotional floor tagging in the journal
Your daily journal entries now get tagged with an emotional "floor" — a level from 1 (Shame) to 16 (Peace). Over time this builds a map of your emotional patterns: which people, activities, and decisions put you on which floors. If you don't want it, just tell Claude "turn off floor tagging." Learn more about the framework: [Internal Design — The High-Rise Model on Substack](https://adelaidadiazroa.substack.com/s/internal-design)

### Journal saves now include floor in YAML frontmatter
Each journal entry saves the floor name and level (low/middle/high) in the file metadata, so you can query across entries: "show me all my Love entries" or "what was my average floor this month."

---

## April 9, 2026

### AI chat export & cleanup
You probably have months or years of conversations in ChatGPT, Claude, or Gemini that contain real thinking — business ideas, personal processing, decisions, brainstorming. The setup and optimize skills now walk you through exporting those conversations and importing them into your vault. They also help you clean up the noise (like "how do I resize an image" or "what's the weather") so you keep the gold and delete the junk.

### External tools connection (email, calendar, Slack, CRM, meetings, design)
The setup skill now walks you through connecting Claude to your actual tools — Gmail, Google Calendar, Slack, HubSpot, meeting recorders, Canva, Figma, and more. This means Claude can search your email, check your schedule, draft messages, and pull context from your CRM — all with your vault as the brain behind it.

### Book notes & highlights import
If you highlight books on Kindle, Apple Books, Readwise, or even physical books — those highlights are now part of the setup. The skill walks you through exporting and importing them so your reading connects to your thinking.

### Health & habit tracking
The journal skill can now track habits like gym, sleep, mood, or anything else you care about. It asks at the end of each journal entry and includes a quick summary line. Over time, you can see patterns — like whether your best weeks have something in common.

### Concept taxonomy
The skill now scans your notes for recurring themes and offers to create a "concept note" for each one. These become hubs that everything else links through. It's what turns a folder of files into a thinking system.

### Backup & sync setup
Your vault is just a folder. If it disappears, everything is gone. The skill now walks you through setting up backup — Google Drive, iCloud, Dropbox, or git.

### Obsidian power rules added to CLAUDE.md
The setup now adds rules to your memory file that make Claude smarter in every session: always wikilink, never duplicate titles, capture content ideas and decisions automatically, quarantine shiny new ideas so they don't distract from your main work.

### Auto-update check
When you run /setup-brain or /optimize-brain, the skill now checks if there's a newer version available and offers to update first. No more running an outdated version without knowing.

---

## April 8, 2026 — Launch

### Initial release
- `/setup-brain` — interactive setup that builds your vault through conversation (13 phases)
- `/optimize-brain` — deep optimization for existing vaults (9 phases)
- Accountability rules, daily journaling, power tools, CRM, templates
- Free, open source, MIT licensed
