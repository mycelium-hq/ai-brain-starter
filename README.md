# AI Brain Starter

**Turn any folder of notes into an AI-powered second brain in one conversation.**

One command to install. One command to start. Claude does the rest.

---

## What This Does

You type `/setup-brain` in Claude Code. Claude interviews you about your life, work, and goals — then builds a complete Obsidian knowledge vault around your answers:

- **Memory file** (CLAUDE.md) — Claude reads this automatically every session. No more re-explaining yourself.
- **Folder structure** — organized by how you think, not how software thinks
- **Contact cards** (CRM) — every person in your life becomes queryable
- **Context layer** — priorities, open loops, last session, decision log
- **Templates** — for journals, meetings, and contacts
- **Daily journal** — Claude interviews you, saves the entry, tracks patterns over time
- **Accountability rules** — Claude pushes back on bad ideas, checks your ego, calls you out when you're avoiding something
- **Power tools** — Graphify (knowledge graphs), Humanizer (de-AI your writing), Claude-Mem (session memory), NotebookLM (query your Google notebooks)

The whole setup takes about 2 hours with the conversation. The basics take 30 minutes.

---

## Install

### Prerequisites

- [Obsidian](https://obsidian.md) (free)
- [Claude Code](https://claude.ai/code) (desktop app or CLI)

### One command

```bash
git clone https://github.com/adelaidasofia/ai-brain-starter.git ~/.claude/skills/ai-brain-starter
```

### Stay updated

This skill is actively improving — new features, better prompts, and more tools get added regularly. Update weekly:

```bash
cd ~/.claude/skills/ai-brain-starter && git pull
```

Or just tell Claude: "Update the ai-brain-starter skill."

After updating, check [CHANGELOG.md](CHANGELOG.md) to see what's new — written in plain English, no jargon.

### Start

Open Claude Code and type:

```
/setup-brain
```

Claude will walk you through everything from there. No technical knowledge required.

**Want the full story first?** Read [How I Built a Second Brain That Actually Works With AI](https://adelaidadiazroa.substack.com/p/how-i-built-a-second-brain-that-actually) — the why, the surprises, and what changed.

---

## What Gets Created

```
Your Vault/
  CLAUDE.md                    # Your memory file — Claude reads this every session
  Meta/
    00 Start Here.md           # Session routing
    Current Priorities.md      # Your top 5 right now
    Open Loops.md              # What's unresolved
    Last Session.md            # What happened last time
    Decision Log.md            # Decisions tracked over time
    Templates/
      Template - Journal Entry.md
      Template - CRM Entry.md
      Template - Meeting Note.md
  Journals/                    # Daily entries
    Monthly Summaries/         # Compressed by month
  CRM/                         # People cards with live queries
  Home/                        # Personal goals, habits, health
  Work/                        # Your projects and career
  Writing/                     # Anything you create
  Books/                       # Book notes
  Psychology/                  # Inner work, therapy, growth
```

Plus any custom folders based on your life.

---

## Power Tools (Installed During Setup)

| Tool | What it does | Command |
|------|-------------|---------|
| **Humanizer** | Strips AI patterns from your writing | `/humanizer` |
| **Graphify** | Builds a knowledge graph of your vault | `/graphify .` |
| **Claude-Mem** | Remembers past sessions automatically | automatic + `/mem-search` |
| **NotebookLM** | Queries your Google NotebookLM notebooks | `/notebooklm` |
| **Weekly Insights** | Pattern recognition from your journal week | `/weekly` |
| **Monthly Insights** | Deeper trends, therapist + coach observations | `/monthly` |
| **Meeting → To-Do** | Extracts your action items from meeting notes | `/meeting-todos` |
| **Nano Banana** | Image generation via Google Gemini 3 Pro Image | `/plugin install nano-banana@devon-claude-skills` |

These require Homebrew + Python 3.12 + Node.js. The setup walks you through installing them.

**Want the full picture of every tool, why it's there, and how they fit together?** Read [`docs/POWER_TOOLS.md`](docs/POWER_TOOLS.md) — the catalog of every third-party skill, MCP server, and Obsidian plugin this setup wires together, with attribution and source links for each.

---

## After Setup

### Daily use
- Open Obsidian for visual navigation
- Open Claude Code in your vault for AI-powered work
- Type `/journal` for daily journal interviews
- Type `/humanizer` on any draft before publishing

### Deep optimization
Type `/optimize-brain` when you're ready for the weekend pass:
- **File audit** — scan vault, report stats, find the mess
- **AI chat import & cleanup** — export ChatGPT/Claude/Gemini history, keep the gold, delete the noise
- **CRM standardization** — turn people mentions into queryable contacts
- **Journal compression** — monthly summaries from your entries
- **Domain summaries** — one compressed note per life area
- **Graph cleanup** — fix broken links, connect orphans, enrich dead ends
- **Dashboards** — live Dataview queries for contacts, tasks, projects
- **Wikilink audit** — find and link unlinked mentions across the vault
- **About Me** — self-portrait built from your data
- **Vault health report** — final audit with stats and recommendations

---

## The Accountability Rules

Every CLAUDE.md created by this skill includes these rules. Claude is not a yes-machine — it's a thinking partner.

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

---

## Who This Is For

- Founders who use AI daily and want it to actually know them
- Writers who have years of notes scattered everywhere
- Anyone who journals (or wants to start)
- People who've tried Notion, Roam, Apple Notes, and none of it stuck
- Non-technical people — the setup is a conversation, not a config file

---

## Deeper Documentation

- **[`docs/POWER_TOOLS.md`](docs/POWER_TOOLS.md)** — every third-party skill, MCP server, and Obsidian plugin this setup uses, with attribution, install commands, and the why behind each
- **[`docs/MEMORY_SYSTEM.md`](docs/MEMORY_SYSTEM.md)** — how to make Claude Code accumulate knowledge across sessions using typed memories (the most underrated pattern in this whole setup)
- **[`skills/graphify/RUNBOOK.md`](skills/graphify/RUNBOOK.md)** — the production playbook for running graphify on a large vault, with cost guardrails and lessons from ~5M tokens of real runs
- **[`templates/dataview-queries.md`](templates/dataview-queries.md)** — reusable Dataview query library for journals, CRM, AI chats, decision logs
- **[`templates/Decision Log.md`](templates/Decision%20Log.md)** — template for tracking the *how* of your decisions so you can learn patterns over time
- **[`scripts/build-journal-index.py`](scripts/build-journal-index.py)** — builds a fast lookup index over your journal entries, used by `/insights` and `/weekly`/`/monthly`
- **[CHANGELOG.md](CHANGELOG.md)** — what's new in plain English

---

## Background

This system was built by [Adelaida Diaz-Roa](https://adelaidadiazroa.substack.com), founder of Onde, across a week of intensive Obsidian + Claude Code optimization. 5,000 notes, 12 years of journals, two books in progress, a startup to raise for — all connected, compressed, and navigable.

Read the full story: [How I Built a Second Brain That Actually Works With AI](https://adelaidadiazroa.substack.com)

---

## License

MIT — use it, fork it, make it yours.
