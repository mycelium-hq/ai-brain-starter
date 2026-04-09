---
name: changelog
description: What's new in AI Brain Starter — plain English, no jargon
---

# What's new

*Every time you update (`git pull` or tell Claude "update the ai-brain-starter skill"), check here to see what changed and why.*

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
