# AI Brain Starter

**The operating system for Claude Code.**

One paste installs it. One conversation configures it. Every session after that compounds.

---

## The Problem

Claude Code is powerful out of the box. But every session starts from zero. It doesn't know who you are, what you're working on, what you decided last week, or what patterns you keep repeating. You re-explain context. You lose insights to chat transcripts. You get generic answers when you need specific ones.

This system fixes that.

## What This Actually Is

AI Brain Starter turns Claude Code into a persistent, opinionated collaborator that accumulates real understanding of your life and work over time. It is not a note-taking template. It is a full behavioral layer:

- **Memory that compounds** — Claude reads your context file (CLAUDE.md) every session. Corrections stick. Preferences persist. You never re-explain yourself.
- **Session lifecycle hooks** — every session start loads your last context and current priorities. Every session end captures decisions, insights, ideas, and to-dos to the right files. Nothing stays trapped in a chat transcript.
- **A daily journal that pushes back** — not a diary prompt. A structured interview with an advisory panel of 90+ real voices (Naval, Brene Brown, Hormozi, Buffett, your own custom advisors) that challenge your thinking, catch your blind spots, and track your emotional patterns over time.
- **Knowledge graphs** — Graphify turns your entire vault into a queryable graph. Claude answers "what does my vault say about X?" from structured data instead of grepping thousands of files.
- **Pattern recognition** — weekly and monthly insight reports surface trends you can't see from inside a single day: recurring emotional states, decision patterns, avoidance behaviors, wins you forgot to celebrate.
- **First-principles analysis** — the /deconstruct skill auto-triggers on high-stakes decisions. Surfaces hidden assumptions, finds foundational truths, rebuilds from scratch.
- **Writing that sounds like you, not AI** — the Humanizer (v3.0.0) strips AI patterns and rewrites in your actual voice, statistically anchored to your own writing corpus. Run `/humanizer --diff` to score how close any draft is to your voice before publishing.
- **Accountability rules** — Claude is not a yes-machine. It corrects you, checks your ego, calls out avoidance, and reminds you who you said you wanted to be.

The whole system ships as one install command, works for non-technical users, and auto-updates itself.

---

## Install

### What you need before starting

The [Claude Code desktop app](https://claude.ai/download). That's it. Once it's open, Claude installs everything else for you.

### Step 1 — Open Claude Code

Download and open the [Claude Code desktop app](https://claude.ai/download). Navigate to an empty folder where you want your vault to live.

### Step 2 — Paste this into the chat

```
Please set up my AI Brain Starter. First run this via your Bash tool:

git clone https://github.com/adelaidasofia/ai-brain-starter.git ~/.claude/skills/ai-brain-starter 2>/dev/null || (cd ~/.claude/skills/ai-brain-starter && git pull)

Then run the bootstrap: bash ~/.claude/skills/ai-brain-starter/bootstrap.sh

Once that finishes, run /setup-brain to start my vault setup.
```

Claude clones the skill, runs the installer (Obsidian, Python, graphify, all tools), and starts the setup conversation. No terminal required.

### Step 3 — Answer the questions

Claude interviews you about your life, work, and goals, then builds your entire system around your answers. The basics take 30 minutes. The full setup takes about 2 hours.

### Joining an existing team vault

If a teammate already set up a vault and shared it with you, open Claude Code inside that folder and paste:

```
Please run /setup-brain join-team to wire me into this existing vault.
```

About 5 minutes.

### Stay updated

Just tell Claude: "Update my AI Brain Starter." Claude pulls the latest version and summarizes what changed. Check [docs/RELEASES.md](docs/RELEASES.md) for what's new in plain English.

---

### Prefer the terminal? (advanced)

**Mac and Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1 | iex
```

Then open Claude Code and type `/setup-brain`.

---

## How It Works

### Session start
Hooks automatically load your last session context, current priorities, and graph routing. Claude already knows what you were doing before you say a word.

### During the session
Claude has access to your full context: who you are, what you're building, your decision history, your knowledge graph, your patterns. Every answer is specific to you.

### Session end
A cascade scans the entire conversation and files everything to the right place: decisions to your decision log, to-dos to your task list, insights to your captures file, ideas to your ideas doc. Substack note candidates get drafted. Journal seeds get preserved verbatim for your next /journal session.

### Over weeks and months
Weekly insight reports track your emotional floor patterns, flag avoidance, surface wins. Monthly reports go deeper. The /patterns skill (Instinct Engine) detects recurring friction and converts it into permanent rules and captures. Your system literally gets smarter the more you use it.

---

## The Toolkit

Every tool is installed and wired during setup. They work together, not in isolation.

| Command | What it does |
|---------|-------------|
| `/journal` | Daily journal interview with advisory panel, accountability checks, and emotional floor tracking |
| `/weekly` | Weekly pattern recognition across your journal entries |
| `/monthly` | Deeper monthly trends with therapist and life coach observations |
| `/graphify` | Build a knowledge graph from any set of files |
| `/humanizer` | Strip AI patterns and rewrite in your voice — anchored to your actual writing corpus. `--diff` mode scores any draft 0–100 |
| `/deconstruct` | First-principles analysis on any decision or strategy |
| `/patterns` | Extract recurring patterns from sessions into permanent captures |
| `/meeting-todos` | Pull action items from meeting notes into your to-do list |
| `/optimize-brain` | Deep vault optimization: CRM, graphs, dashboards, compression, wikilinks |
| `/mem-search` | Search Claude's cross-session memory database |

### Power tools under the hood

- **Graphify** — knowledge graph extraction with community detection, audit trails, and 80-92% token savings via wrapper scripts
- **Nano Banana** — image generation via Google Gemini 3 Pro Image
- **Granola MCP** — meeting transcription with automatic cascade to downstream files
- **Dataview + Bases** — live database queries over your markdown files in Obsidian

Full catalog with attribution and source links: [`docs/POWER_TOOLS.md`](docs/POWER_TOOLS.md)

---

## What Gets Created

```
Your Vault/
  CLAUDE.md                    # Your memory file — loaded every session
  Meta/
    00 Start Here.md           # Session routing
    Current Priorities.md      # Your top focus areas
    Open Loops.md              # What's unresolved
    Last Session.md            # Continuity between sessions
    Decision Log.md            # Decisions tracked over time
    Session Captures.md        # Insights, seeds, ideas filed automatically
    rules/                     # Behavioral rules for different task types
    Templates/                 # Journal, CRM, meeting note templates
  Journals/                    # Daily entries with floor tags
    Monthly Summaries/         # Compressed by month
  CRM/                         # Queryable contact cards with Dataview
  Home/                        # Personal goals, habits, health
  Work/                        # Projects and career
  Writing/                     # Drafts, Substack, books
  Books/                       # Book notes
  Psychology/                  # Inner work, therapy, growth
```

Plus custom folders based on your interview.

---

## The Accountability Rules

Every CLAUDE.md created by this system includes these rules. Claude is a thinking partner, not a yes-machine.

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

- **Claude Code power users** who want every session to build on the last one
- **Founders** running a company and a life and tired of re-explaining context to AI
- **Writers** with years of notes scattered everywhere who want them connected and queryable
- **Anyone who journals** (or wants to) and wants an AI that actually remembers what you said
- **Teams** who want a shared knowledge system with personal vaults that stay private
- **Non-technical people** — the entire setup is a conversation, not a config file

---

## Deeper Documentation

- **[`docs/POWER_TOOLS.md`](docs/POWER_TOOLS.md)** — every third-party skill, MCP server, and Obsidian plugin, with attribution and source links
- **[`docs/MEMORY_SYSTEM.md`](docs/MEMORY_SYSTEM.md)** — how Claude accumulates knowledge across sessions using typed memories
- **[`docs/TOKEN_OPTIMIZATION.md`](docs/TOKEN_OPTIMIZATION.md)** — how to stop burning tokens on overhead: compress Claude-facing files, cap memory, route cheap work to cheap models
- **[`docs/BUILD_STANDARDS.md`](docs/BUILD_STANDARDS.md)** — read before any MCP/skill/script build. Pre-build checklist, optimization pass, pre-extraction patterns
- **[`skills/graphify/RUNBOOK.md`](skills/graphify/RUNBOOK.md)** — production playbook for running graphify on a large vault, with cost guardrails
- **[`skills/graphify/LESSONS.md`](skills/graphify/LESSONS.md)** — 104 operational lessons from running graphify on a 10K-file vault across 70+ sessions
- **[`templates/dataview-queries.md`](templates/dataview-queries.md)** — reusable Dataview query library for journals, CRM, AI chats, decision logs
- **[`templates/obsidian/`](templates/obsidian/)** — 6 pre-built Templater templates (journal, theme, CRM, writing draft, floor check-in, graphify extraction prompt)
- **[`templates/rules/`](templates/rules/)** — opt-in rule files (voice-firewall, session-close, hookify-authoring, mcp-build-checks, repo-evaluation) to paste into your CLAUDE.md
- **[`for-teams/`](for-teams/)** — extra docs for teams sharing a vault (working-with-me pages, team workflows)
- **[`docs/OPTIMIZE.md`](docs/OPTIMIZE.md)** — the deep vault optimization guide (11 phases, weekend project). Run `/optimize-brain` after setup to become a power user.
- **[`EXAMPLES.md`](EXAMPLES.md)** — sample journal entry and weekly insight report showing output quality
- **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — how to contribute (the project is opinionated by design)
- **[`docs/RELEASES.md`](docs/RELEASES.md)** — what's new in plain English. Full development history: [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

---

## Background

This system was built by [Adelaida Diaz-Roa](https://adelaidadiazroa.substack.com), founder of [Onde](https://www.planwithonde.com), across weeks of intensive optimization with Claude Code. 5,000+ notes, 12 years of journals, two books in progress, a startup to raise for, all connected, compressed, and navigable.

Read the full story: [How I Built a Second Brain That Actually Works With AI](https://adelaidadiazroa.substack.com/p/how-i-built-a-second-brain-that-actually)

---

## License

MIT — use it, fork it, make it yours.
