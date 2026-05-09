# AI Brain Starter

A verification harness around your AI agent. So memory compounds instead of corrupts.

---

Microsoft DELEGATE-52 ([arxiv.org/abs/2604.15597](https://arxiv.org/abs/2604.15597), April 2026) measured what most operators already feel: frontier LLMs corrupt 25% of professional content over 20 edit interactions. Document size amplifies the failure 5×. The paper concludes the only reliable mitigation is a domain-specific verification harness around the model.

This is one.

**Four moving parts.**

- **Vault as ground truth.** Markdown on disk. Decisions, patterns, context. The model reads from the vault, not from chat history.
- **Hooks as deterministic guards.** Pre-write hooks block bad edits before they land. Em dashes in external prose. Frontmatter without required fields. Calendar events without timezone offsets. Raw `git add -A` on a 60K-file vault.
- **Bi-temporal rule lineage.** Every codified rule carries two clocks: when it was written, and when it was last verified. The resolver detects conflicts. Drift detection scans high-edit files weekly for cumulative semantic shift. The closed loop promotes hardened patterns into procedural memory and demotes stale ones.
- **Session lifecycle.** Each session start loads context. Each session end cascades decisions, insights, and to-dos to the right files. Nothing stays trapped in a chat transcript.

**Free to install. Free to run.** Your Claude subscription is the inference. No vector database, no fine-tune, no per-seat license.

[Install in one paste →](#install)

---

## Built under load

The repo is shaped by an active vault: 10,000 markdown files, twelve years of journals, two writing projects, a startup to raise for, an AI consulting practice. The system was forced into shape by the work, not designed in a lab. It's used by the founder who built it; new installs land each week through the consulting practice.

If you carry context professionally (investor relationships, board decisions, team dynamics, contractor handoffs) plus the parts of a life that don't fit inside the company, this is for you.

## A Monday after the system is installed

**7:04 AM.** You run `/journal`. The advisory panel (Naval, Brene Brown, Hormozi, Buffett, plus the custom voices you build) meets your draft and pushes back where your thinking is soft. You walk into the day with ten-minute clarity on something that would have taken an hour of spinning.

**11:20 AM.** A one-hour meeting ends. You drop the transcript in. The system files it, tags participants, extracts five action items, routes each one to the right owner by role, and drafts the follow-up message for you to review. Thirty-five minutes of post-meeting work compressed to two.

**1:00 PM.** Thirty minutes between blocks. You open the book draft. Claude reads the new scene against every previous chapter in the vault, flags a continuity break in chapter three, and scores the voice match against your own corpus. You fix the weak sentence in two minutes and close the tab.

**3:00 PM.** You write a one-liner for a contractor. A hook blocks the save: missing the four required fields (source, location, shape, channel). You rewrite the task in ninety seconds. She ships in one pass. You save a $500 week.

**6:45 PM.** A close friend texts about something the two of you talked through six months ago. You ask Claude. Three seconds later you have the thread, the date, what was unresolved, and what you promised. You reply from context, not from guesswork.

**Sunday, 9:00 PM.** The weekly ritual runs. Every open loop from the last fourteen days surfaces in a single view, across the whole life: the company, the book, the consulting, the people you care about. Decisions pending, promises outstanding, follow-ups due. You resolve three, deliberately defer two, and close the week with a clean runway into the next one.

Monday starts with context, not amnesia.

---

## When your team joins

The personal version of this system already runs your half: your context, your decisions, your patterns. The leverage step is wiring your team into the same brain without giving them access to your personal vault.

Here is what that looks like:

- Your personal vault contains everything: business, team, family, projects, writing, journals.
- Inside it, a team folder syncs bidirectionally with a separate team vault that your co-founders, operators, or contractors share.
- They get the team vault. You get the integrated view across all of it.
- Your business decisions can pull insight from your personal patterns. Your team folder routes work to specific people by role. Your to-dos shuffle between personal and team without ever leaking either way.
- On top of that, a marketplace of skills and MCP servers custom-built for your team's exact workflows, optimized to your stack, your voice, your decision logic.

The personal version of the repo handles your half. The team version handles theirs, plus the sync, plus the per-team customization.

Read the four problems the team version solves: [`for-teams/why-teams-are-different.md`](for-teams/why-teams-are-different.md). Read the four workflows it runs that a personal vault cannot: [`for-teams/team-workflows.md`](for-teams/team-workflows.md). If you want it built for you, [`for-teams/working-with-me.md`](for-teams/working-with-me.md) has the menu, or once your personal vault is installed, just ask Claude: *"how do I add my team to this without mixing in my personal stuff?"* and it will walk you through.

---

## Install

### Step 1 — Get your install link

Go to **[myceliumai.co/install](https://myceliumai.co/install)** (Spanish: **[myceliumai.co/es/install](https://myceliumai.co/es/install)**) and fill out the short form. Takes about 4 minutes.

The form personalizes your install (so the system knows your role, your data, and which language to run in) and emails you a one-paste install command with your unique token. The same form is the path for paid cohorts, paid private installs, complimentary partner cohorts, and free open-source explorers.

### Step 2 — Open Claude Code

Open the [Claude Code desktop app](https://claude.ai/download) and sign in with a paid Claude account (Pro, Max, or Team). The bootstrap installs everything else (Homebrew, Python, Node, Obsidian, all skills) for you.

### Step 3 — Paste the install command from your email

Your welcome email contains a personalized command with your token embedded. Paste it into Claude Code and approve the tool calls. Claude runs:

1. A 30-second pre-flight check (OS, network, Claude Code install, admin permissions, disk).
2. The token-gated bootstrap (clones the skill, installs all tools).
3. The setup interview (asks your language first, runs everything in your chosen language).

One paste, no terminal commands to type. Mac, Windows, and Linux all use the same flow.

**If pre-flight fails**, Claude reads the structured report and explains in plain English what to fix. The most common blockers are: Claude Code not installed (download from https://claude.ai/download), a corporate VPN blocking GitHub, or a Mac that's not in the admin group.

**Existing users** (anyone who installed before the email gate was live): your next bootstrap re-run will prompt you once to fill the same form. After that, you're never asked again.

*Local install. Your vault data never leaves your machine. The signup form is the only piece that touches our servers, and it captures only what's listed in [`SECURITY.md`](SECURITY.md) and the [privacy policy](https://myceliumai.co/privacy).*

### Quick-try (existing Claude Code users)

If you already have Claude Code **2.1.133+** and just want to try the skills against an existing vault (no full bootstrap, no Obsidian setup), load the plugin from the latest release archive:

```
claude --plugin-url https://github.com/adelaidasofia/ai-brain-starter/releases/latest/download/ai-brain-starter.zip
```

This loads the plugin **for the current session only**, giving you the skills (journaling, graphify, weekly insights, etc.) without touching your home directory or vault structure. Use it to evaluate whether the skill set fits your workflow before committing to the full bootstrap. The full install above remains the recommended path: it sets up the Obsidian vault, the hooks, the resolver, the meeting workflow, and everything else that makes the system compound across sessions.

---

## Instalar (Español)

### Paso 1 — Conseguí tu link de instalación

Andá a **[myceliumai.co/es/install](https://myceliumai.co/es/install)** (English: **[myceliumai.co/install](https://myceliumai.co/install)**) y completá el formulario corto. Tarda unos 4 minutos.

El formulario personaliza tu instalación (para que el sistema sepa tu rol, tus datos, y en qué idioma correr) y te manda por email un comando de un solo pegado con tu token único. El mismo formulario es la ruta para cohortes pagas, instalaciones privadas pagas, cohortes complementarias de partners, y exploradores open-source.

### Paso 2 — Abrí Claude Code

Abrí la [app de escritorio de Claude Code](https://claude.ai/download) y logueate con una cuenta paga de Claude (Pro, Max o Team). El bootstrap instala todo lo demás (Homebrew, Python, Node, Obsidian, todas las skills) por vos.

### Paso 3 — Pegá el comando de instalación de tu email

Tu email de bienvenida contiene un comando personalizado con tu token. Pegalo en Claude Code y aprobá las acciones. Claude va a correr:

1. Una verificación previa de 30 segundos (OS, red, instalación de Claude Code, permisos de admin, disco).
2. El bootstrap con token (clona la skill, instala todas las herramientas).
3. La entrevista de setup (te pregunta el idioma primero, corre todo en el idioma que elijas).

Un pegado, cero comandos que tipear. Mac, Windows y Linux usan el mismo flujo.

**Usuarios existentes** (cualquiera que instaló antes de que el gate de email estuviera vivo): la próxima vez que corras el bootstrap te va a pedir una sola vez que completes el mismo formulario. Después, nunca más.

---

### Joining an existing team vault

If a teammate already set up a vault and shared it with you, open Claude Code inside that folder and paste:

```
A teammate already set up an AI Brain Starter vault here and shared it with me. Wire me into it. Don't create a new one.
```

About 5 minutes.

### Stay updated

Just tell Claude: "Update my AI Brain Starter." Claude pulls the latest version and summarizes what changed. Check [docs/RELEASES.md](docs/RELEASES.md) for what's new in plain English.

### Something feels off?

Tell Claude: "Diagnose my AI Brain Starter." It runs ~10 checks against your vault (CLAUDE.md present, hooks registered, journal index fresh, skills installed, etc.) and reports in plain English what's working and what isn't. Safe any time.

---

## How It Works

### Session start
Hooks automatically load your last session context, current priorities, and graph routing. Claude already knows what you were doing before you say a word.

### During the session
Claude has access to your full context: who you are, what you're building, your decision history, your knowledge graph, your patterns. Every answer is specific to you.

### Session end
A cascade scans the entire conversation and files everything to the right place: decisions to your decision log, to-dos to your task list, insights to your captures file, ideas to your ideas doc. Substack note candidates get drafted. Journal seeds get preserved verbatim for your next /journal session.

### Over weeks and months
Weekly insight reports track your emotional floor patterns, flag avoidance, surface wins. Monthly reports go deeper. The /patterns skill (Instinct Engine) detects recurring friction and converts it into permanent rules and captures. Your corpus gets richer every week. Every conversation lands on a deeper substrate than the last one.

---

## The Toolkit

Every tool is installed and wired during setup. They work together, not in isolation.

| Command | What it does |
|---------|-------------|
| `/journal` | Daily journal interview with advisory panel, accountability checks, and emotional floor tracking |
| `/coaching` | Multi-pass coaching session for processing a hard conversation, decision, or accumulated tension. Verbatim raw + synthesized accountability record + rolling pattern tracker, with re-eval one month out |
| `/weekly` | Weekly pattern recognition across your journal entries (also surfaces Coaching Sessions whose re-eval date has passed) |
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
- **Drift detection** — `scripts/drift-detection.py` flags vault files edited 5+ times in the last 30 days as candidates for human review of cumulative semantic drift. Inspired by Microsoft DELEGATE-52 ([arxiv.org/abs/2604.15597](https://arxiv.org/abs/2604.15597)) which found frontier LLMs corrupt ~25% of professional content over 20 edits. Optional `--semantic` mode adds claude-haiku intent-shift judgment.
- **Rule conflict detection** — `scripts/check-rule-conflicts.py` catches cross-document contradictions (`always X` vs `never X` on shared nouns) at write time. Engram-inspired ([github.com/Gentleman-Programming/engram](https://github.com/Gentleman-Programming/engram)). Default keyword-anchor mode is deterministic and free; `--semantic` adds vocabulary-different contradiction detection via claude-haiku.

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

Built for founders. The people running a company and a life, carrying a dozen contexts at once, losing the thread between investor calls, board updates, contractor handoffs, the book draft open in parallel, the consulting clients on the side, the friendships they want to tend, the kids' schedules, and the actual work. If that is you, the rest of this list is people the system also fits, but you are the bullseye.

- **Founders** running a company and a life, tired of re-explaining context to AI every session and losing decisions to chat transcripts
- **Operators, Chiefs of Staff, co-founders** carrying the context for a founder who is too busy to carry it themselves
- **Claude Code power users** who want every session to build on the last one
- **Writers** with years of notes scattered everywhere who want them connected and queryable
- **Anyone who journals** (or wants to) and wants an AI that remembers what you said, challenges you, and surfaces your patterns
- **Teams** who want a shared knowledge system with personal vaults that stay private. See [for-teams/](for-teams/) for what changes when more than one person uses the vault.
- **Non-technical people** — the entire setup is a conversation, not a config file

---

## What this isn't

Not an enterprise multi-agent orchestration platform. Not a SaaS. No shared database, no per-seat license, no fine-tune to provision, no agent swarm to coordinate across machines. The vault lives on your disk. The intelligence lives in your Claude subscription. The skills and hooks are open-source files you can read in fifteen minutes.

If what you need is agent federation, swarm topologies, or a 300-tool MCP server, this is the wrong product. This one is for the founder who wants their second brain to compound, not their orchestration layer to scale.

---

## Deeper Documentation

- **[`RELIABILITY_MANIFESTO.md`](RELIABILITY_MANIFESTO.md)** — the five architectural pillars (vault as ground truth, hooks as deterministic guards, rule extraction, decision-outcome trail, session-close cascade) and the five failure modes they prevent (hallucination, silent failure, cold start, drift, knowledge loss). Read this if you want to understand why the system is shaped the way it is.
- **[`docs/POWER_TOOLS.md`](docs/POWER_TOOLS.md)** — every third-party skill, MCP server, and Obsidian plugin, with attribution and source links
- **[`docs/MEMORY_SYSTEM.md`](docs/MEMORY_SYSTEM.md)** — how Claude accumulates knowledge across sessions using typed memories
- **[`docs/TOKEN_OPTIMIZATION.md`](docs/TOKEN_OPTIMIZATION.md)** — how to stop burning tokens on overhead: compress Claude-facing files, cap memory, route cheap work to cheap models
- **[`docs/BUILD_STANDARDS.md`](docs/BUILD_STANDARDS.md)** — read before any MCP/skill/script build. Pre-build checklist, optimization pass, pre-extraction patterns
- **[`skills/graphify/RUNBOOK.md`](skills/graphify/RUNBOOK.md)** — production playbook for running graphify on a large vault, with cost guardrails
- **[`skills/graphify/LESSONS.md`](skills/graphify/LESSONS.md)** — 104 operational lessons from running graphify on a 10K-file vault across 70+ sessions
- **[`templates/dataview-queries.md`](templates/dataview-queries.md)** — reusable Dataview query library for journals, CRM, AI chats, decision logs
- **[`templates/obsidian/`](templates/obsidian/)** — 6 pre-built Templater templates (journal, theme, CRM, writing draft, floor check-in, graphify extraction prompt)
- **[`templates/CRM-examples/`](templates/CRM-examples/)** — three sample CRM cards (maintainer, advisor, contractor) showing what a populated entry looks like, plus the Source/Location/Shape/Channel pattern for delegating contractor tasks
- **[`templates/rules/`](templates/rules/)** — opt-in rule files (voice-firewall, session-close, hookify-authoring, mcp-build-checks, repo-evaluation) to paste into your CLAUDE.md
- **[`for-teams/`](for-teams/)** — extra docs for teams sharing a vault (working-with-me pages, team workflows)
- **[`docs/OPTIMIZE.md`](docs/OPTIMIZE.md)** — the deep vault optimization guide (11 phases, weekend project). Run `/optimize-brain` after setup to become a power user.
- **[`EXAMPLES.md`](EXAMPLES.md)** — sample journal entry and weekly insight report showing output quality
- **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — how to contribute (the project is opinionated by design)
- **[`SECURITY.md`](SECURITY.md)** — four practical habits that protect your machine and data when running a local AI + vault setup (secrets, skills/hooks, MCPs, Claude permissions)
- **[`docs/RELEASES.md`](docs/RELEASES.md)** — what's new in plain English. Full development history: [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

---

## Background

This system was built by [Adelaida Diaz-Roa](https://adelaidadiazroa.substack.com), founder of [Onde](https://www.planwithonde.com), across weeks of intensive optimization with Claude Code. 5,000+ notes, 12 years of journals, two books in progress, a startup to raise for, all connected, compressed, and navigable.

Read the full story: [How I Built a Second Brain That Actually Works With AI](https://adelaidadiazroa.substack.com/p/how-i-built-a-second-brain-that-actually)

---

## Working with me

The repo is free. The full custom setup is not.

I install the full version for a small number of founders, solo operators, and teams each quarter. The Personal Install is for one person whose work is decision-heavy and context-rich: founders running a company and a life, writers, product managers, consultants. The Team Install is for a co-founder pair or small company. Either way: 2-hour deep-dive, custom vault architecture, knowledge graph densification across your existing notes, MCP integrations with your actual stack, async training. Packages and pricing: [for-teams/working-with-me.md](for-teams/working-with-me.md).

Free 20-minute AI diagnostic at [diazroa.com](https://diazroa.com) if you want to see whether it is a fit before a package conversation. No pitch deck, no follow-up sequence. I audit your workflow live and tell you where you are losing time to work AI should be doing. If it is a fit, we talk packages. If it is not, you keep the audit and we part as friends.

---

## License

MIT — use it, fork it, make it yours.
