# AI Brain Starter

**The operating system for founders running a company and a life.**

---

A founder's job is to carry context other people cannot carry. Investor relationships. Board decisions. Team dynamics. Contractor handoffs. The patterns inside your own thinking that compound quietly into wins, or quietly into drift.

Most AI tools handle tasks. This is the operating system that handles the context.

No more re-explaining who you are and what you are building. No more insights lost to chat transcripts. No more decisions you cannot find when you need them. Every session compounds. Every meeting becomes memory. Every pattern surfaces before it becomes a problem.

## They say entrepreneurship is the greatest growth school

It is. The problem is the school forgets everything you learn the moment you walk out of the classroom.

This accelerates the growth and cuts the mistakes. That acceleration comes from two things most AI tools for founders don't give you:

- **Inner knowledge.** A daily journal with an advisory panel of 90+ real voices (Naval, Brene Brown, Hormozi, Buffett, your own custom advisors) that track your emotional patterns, catch your blind spots, and surface the avoidance behaviors you cannot see from the inside.
- **Honest feedback.** Fifteen accountability rules baked into every session. Claude corrects you when you are wrong, calls out avoidance, checks your ego, and reminds you who you said you wanted to be. Not a yes-machine. A thinking partner.

Plus everything that makes a founder's week compound instead of reset:

- **Memory that compounds** — Claude reads your context file (CLAUDE.md) every session. Corrections stick. Preferences persist. You never re-explain yourself.
- **Session lifecycle hooks** — every session start loads your last context and current priorities. Every session end captures decisions, insights, ideas, and to-dos to the right files. Nothing stays trapped in a chat transcript.
- **Knowledge graphs** — Graphify turns your entire vault into a queryable graph. Claude answers "what did I decide about pricing in February?" from structured data instead of grepping thousands of files.
- **Pattern recognition** — weekly and monthly insight reports surface what you avoided, what stalled, what you promised and did not deliver. Your system catches the founder-shame loop before it catches you.
- **First-principles analysis** — the /deconstruct skill auto-triggers on high-stakes decisions. Surfaces hidden assumptions, finds foundational truths, rebuilds from scratch.
- **Writing that sounds like you, not AI** — the Humanizer (v3.0.0) strips AI patterns and rewrites in your actual voice, statistically anchored to your own writing corpus. Run `/humanizer --diff` to score how close any draft is to your voice before publishing.

The whole system ships as one install command, works for non-technical founders, and auto-updates itself.

---

## What a Monday looks like after the system is installed

**7:04 AM.** You run `/journal`. The advisory panel (Naval, Brene Brown, Hormozi, Buffett, plus the custom voices you build) meets your draft and pushes back where your thinking is soft. You walk into the day with ten-minute clarity on something that would have taken an hour of spinning.

**11:20 AM.** A one-hour meeting ends. You drop the transcript in. The system files it, tags participants, extracts five action items, routes each one to the right owner by role, and drafts the follow-up message for you to review. Thirty-five minutes of post-meeting work compressed to two.

**3:00 PM.** You write a one-liner for a contractor. A hook blocks the save: missing the four required fields (source, location, shape, channel). You rewrite the task in ninety seconds. She ships in one pass. You save a $500 week.

**Sunday, 9:00 PM.** The weekly ritual runs. Every open loop from the last fourteen days surfaces in a single view: decisions pending, promises outstanding, follow-ups due. You resolve three, deliberately defer two, and close the week with a clean runway into the next one.

Monday starts with context, not amnesia.

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

Built for founders. The people running a company and a life, carrying a dozen contexts at once, losing the thread between investor calls, contractor handoffs, board updates, and the actual work. If that is you, the rest of this list is people the system also fits, but you are the bullseye.

- **Founders** running a company and a life, tired of re-explaining context to AI every session and losing decisions to chat transcripts
- **Operators, Chiefs of Staff, co-founders** carrying the context for a founder who is too busy to carry it themselves
- **Claude Code power users** who want every session to build on the last one
- **Writers** with years of notes scattered everywhere who want them connected and queryable
- **Anyone who journals** (or wants to) and wants an AI that remembers what you said, challenges you, and surfaces your patterns
- **Teams** who want a shared knowledge system with personal vaults that stay private. See [for-teams/](for-teams/) for what changes when more than one person uses the vault.
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

## Working with me

The repo is free. The full custom setup is not.

I install the full version for a small number of founders and teams each quarter. 2-hour deep-dive, custom vault architecture, knowledge graph densification across your existing notes, MCP integrations with your actual stack, one week of async training. Packages and pricing: [for-teams/working-with-me.md](for-teams/working-with-me.md).

Free 20-minute AI diagnostic at [diazroa.com](https://diazroa.com) if you want to see whether it is a fit before a package conversation. No pitch deck, no follow-up sequence. I audit your workflow live and tell you where you are losing time to work AI should be doing. If it is a fit, we talk packages. If it is not, you keep the audit and we part as friends.

---

## License

MIT — use it, fork it, make it yours.
