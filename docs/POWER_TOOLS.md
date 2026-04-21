# Power Tools Catalog

The third-party Claude Code skills, MCP servers, and Obsidian plugins that make this setup actually work.

`/setup-brain` installs most of these automatically in Phase 0. This doc is the **why** behind each one — what it does, when to use it, and where it came from. Read it if you want to understand the stack, customize the install, or pick a subset.

Nothing in this catalog is built by this repo. They're all open-source tools by other people that this setup integrates and recommends. Attribution and source links are included for every entry.

---

## Skills (Claude Code)

These get installed into `~/.claude/skills/` and become available as `/skill-name` commands.

### graphify — knowledge graph from any folder

**What it does:** Turns any folder of markdown files (or code, or papers) into a navigable knowledge graph with community detection, god-node ranking, and surprising connections. The output is one HTML graph + one JSON dump + one `GRAPH_REPORT.md` summary.

**Why it matters for a vault:** Once you have ~500 notes, you stop being able to hold the whole structure in your head. Graphify gives you a map. The `GRAPH_REPORT.md` becomes the **first thing Claude reads** for any strategic question — way faster and more accurate than reading individual files. On a 4,700-file personal vault, it cuts cross-concept research from "read 10 files" to "read one report."

**Install:**
```bash
pipx install graphifyy
graphify install
```

The Claude Code skill (in `~/.claude/skills/graphify/`) wraps the CLI with optimization scripts. `/setup-brain` Phase 0 installs both. The full pipeline + lessons learned is in [`skills/graphify/RUNBOOK.md`](../skills/graphify/RUNBOOK.md).

**Trigger:** `/graphify <folder>` to build, `/graphify <folder> --update` to incrementally update.

**Source:** [graphifyy on PyPI](https://pypi.org/project/graphifyy/) (the underlying package). The Claude Code skill in this repo wraps it with vault-specific optimizations.

---

### humanizer — remove AI writing patterns from text

**What it does:** Detects and removes the telltale signs of AI-generated writing — em dash overuse, "rule of three" pacing, vague attributions, promotional inflation, filler phrases, "it's not just X, it's Y" parallelisms, AI vocabulary words. Based on Wikipedia's "Signs of AI writing" maintained by WikiProject AI Cleanup.

**Why it matters for a founder:** every external doc you write — pitch deck, investor email, blog post, landing page — needs to sound like a human. AI-flavored writing actively hurts you in fundraising contexts. Investors are pattern-matchers and "this reads like ChatGPT" is a fast way to lose trust.

**Recent versions add:**
- **Pre-flight doc-type detection** — pitch decks need different rules than blog posts (em dashes are intentional beats in pitches)
- **Mandatory voice calibration** — loads your existing writing as a reference before editing, so it doesn't flatten your style
- **Spanish-language rule library** — handles Spanglish and bilingual docs without English-flattening
- **AI-iness density check** — adapts pass strength (light/mixed/full) to how AI-flavored the input is

**Install:**
```bash
git clone https://github.com/adelaidasofia/humanizer.git ~/.claude/skills/humanizer
```

`/setup-brain` Phase 0 installs this automatically.

**Trigger:** `/humanizer <file>` or `/humanizer "<paragraph>"`.

**Source:** Originally [blader/humanizer](https://github.com/blader/humanizer); the fork at [adelaidasofia/humanizer](https://github.com/adelaidasofia/humanizer) adds the pre-flight, voice calibration, and Spanish rules. MIT licensed.

---

### nano-banana — image generation via Gemini 3 Pro Image

**What it does:** Generate, edit, and compose images using Google's Gemini 3 Pro Image model (Nano Banana Pro). Supports text-to-image, image editing, multi-image composition (up to 14 reference images), iterative refinement via chat, and Google Search-grounded image generation for real-time data visualization.

**Why it matters for a founder:** every founder needs visuals constantly — pitch deck slides, social media assets, product mockups, blog post headers, logo iterations, infographics. The traditional answer is "open Canva" or "DM your designer." This skill lets Claude generate them in-chat from a one-line description, with aspect ratios, resolutions, and refinement built in.

**Examples:**
```bash
python scripts/generate_image.py "Clean black-and-white logo with text 'Acme', sans-serif, minimalist" logo.png --aspect 1:1
python scripts/generate_image.py "Studio-lit product photo on polished concrete, 3-point softbox" hero.png --aspect 16:9 --size 4K
python scripts/edit_image.py photo.png "Add a sunset to the background" edited.png
```

**Install:** Adds to Claude Code via the [devon-claude-skills marketplace](https://github.com/devonjones/devon-claude-skills):
```bash
/plugin marketplace add devonjones/devon-claude-skills
/plugin install nano-banana@devon-claude-skills
```

You also need a `GEMINI_API_KEY` environment variable from [Google AI Studio](https://ai.google.dev/).

**Source:** [devonjones/devon-claude-skills](https://github.com/devonjones/devon-claude-skills) (Devon Jones). The original standalone repo is archived; the marketplace is the active home.

---

## Cheap model APIs

When the task is mechanical — extract entities, summarize a doc, classify notes — burning Opus tokens is wasteful. A cheap reasoning model costs 100–150x less and is sufficient.

### MiniMax M2.7 — cheap text processing

**What it does:** A fast, cheap reasoning model good at extraction, classification, summarization, and boilerplate generation. Not a replacement for Claude on judgment-heavy work, but a workhorse for grunt-work text processing.

**Why it matters:** Entity extraction across a 500-file vault: ~$0.30 on MiniMax vs ~$45 on Opus. For batch operations (graphify pre-processing, transcript entity extraction, bulk note tagging), the savings compound.

**Cost:** ~$0.06/M tokens at [platform.minimax.io](https://platform.minimax.io) (create a free account, add credits).

**Install:** This repo ships `scripts/minimax.sh`. After getting your API key:
```bash
export MINIMAX_API_KEY="your-key-here"  # add to ~/.zshrc
chmod +x scripts/minimax.sh

# Test it
./scripts/minimax.sh "Summarize this in 3 bullet points: Claude Code is a terminal-based AI coding assistant built by Anthropic."
```

**Route to MiniMax when:** extracting structure from raw text (meeting transcripts, docs), bulk-classifying or tagging vault notes, generating boilerplate from a template, summarizing a single document with no voice requirement.

**Route to Sonnet/Opus when:** judgment calls, writing in your voice, cross-file synthesis, anything with ambiguity.

See [`docs/TOKEN_OPTIMIZATION.md`](TOKEN_OPTIMIZATION.md) for the full routing guide.

---

## MCP servers

MCP (Model Context Protocol) servers extend Claude Code with structured tool access to external systems. Configured in `~/.claude/.mcp.json`.

### Granola — meeting transcript export

**What it does:** [Granola](https://granola.ai/) records and transcribes Zoom/Meet/Teams calls with AI-generated summaries. `scripts/granola_sync.py` reads Granola's local cache directly and exports the full timestamped transcript to your vault's meeting notes folder — no API key, no network call, no MCP needed. The meeting workflow rule in CLAUDE.md (see SKILL.md Phase 4) uses this to auto-cascade meeting takeaways into:

- The meeting note itself (enriched with decisions, action items, verbatim quotes)
- The CRM contact files for every attendee (last_interaction updated, meeting note linked)
- Your team to-do file (action items extracted and assigned)
- Canonical strategy/pitch docs (decisions cascaded to the relevant doc)

**Why it matters:** without this, you spend 20 minutes after every meeting transcribing handwritten notes and updating CRM cards. With it, Claude reads the full transcript and does the cascade in one command.

**Install:**
1. Granola must be installed and have recorded at least one meeting.
2. Run once manually to test: `python3 scripts/granola_sync.py --dry-run`
3. For auto-export after every meeting, install the LaunchAgent:
   - Copy `scripts/com.granola-export.plist` to `~/Library/LaunchAgents/`
   - Edit the two placeholder paths inside it (script path + your username)
   - Run: `launchctl load ~/Library/LaunchAgents/com.granola-export.plist`

**Note on speaker labels:** The local cache captures your microphone as `[You]` and remote audio as a single stream (no per-person diarization). The Granola-generated summary notes are also included in the exported file.

**Source:** Reverse-engineered from Granola's local cache format by the ai-brain-starter community.

---

### ChatPRD — product specs and PRDs from Claude Code

**What it does:** [ChatPRD](https://www.chatprd.ai/) is an AI tool purpose-built for product requirements documents. The MCP integration lets Claude Code create, search, read, and update PRDs in your ChatPRD workspace without leaving the terminal. You can say "create a PRD for the venue search feature" and Claude writes it directly into ChatPRD.

**Why it matters:** ChatPRD has templates, version history, and shareable links for stakeholders. It's purpose-built for specs in a way that markdown files in Obsidian aren't. The MCP makes it accessible from the same place you do everything else.

**Install:** Add to your vault `.mcp.json` (the `.mcp.json` file at your vault root, NOT `~/.claude/.mcp.json`):

```json
{
  "mcpServers": {
    "ChatPRD": {
      "type": "http",
      "url": "https://app.chatprd.ai/mcp"
    }
  }
}
```

Then open Claude Code and use any ChatPRD tool — it will prompt you to authenticate via OAuth. One-time setup, then it stays connected.

**Requires:** A ChatPRD account at [chatprd.ai](https://www.chatprd.ai/).

**Source:** ChatPRD team. HTTP MCP — no server to run locally.

---

### RescueTime — productivity data for weekly reviews

**What it does:** [RescueTime](https://www.rescuetime.com/) tracks which apps and websites you use and for how long, categorizing time as productive, neutral, or distracting. The MCP integration (a custom FastMCP server included in this repo at `scripts/mcps/rescuetime-server.py`) lets Claude pull your productivity data live. Used primarily during `/weekly` reviews to merge app-level tracking ("I spent 3h in VS Code") with the session logs Claude writes at session end ("I spent 3h on the Onde investor deck").

**Why it matters:** The session-end cascade (Lane 8) logs *purpose* (what you were working on). RescueTime logs *apps* (what tools you used). Combined during `/weekly`, they give a complete picture of where your hours actually went — not just what you meant to do.

**Install:**

1. Install dependencies: `pip install fastmcp httpx` (or `pipx install fastmcp`)
2. Copy the server to a persistent location:
   ```bash
   mkdir -p ~/.claude/rescuetime-mcp
   cp scripts/mcps/rescuetime-server.py ~/.claude/rescuetime-mcp/server.py
   ```
3. Get your API key from [rescuetime.com/anapi/manage](https://www.rescuetime.com/anapi/manage) (under "API Access Key")
4. Add to your vault `.mcp.json`:
   ```json
   {
     "mcpServers": {
       "rescuetime": {
         "type": "stdio",
         "command": "fastmcp",
         "args": ["run", "/YOUR/HOME/.claude/rescuetime-mcp/server.py"],
         "env": {
           "RESCUETIME_API_KEY": "your-api-key-here"
         }
       }
     }
   }
   ```
   Replace `/YOUR/HOME/` with your actual home path (e.g., `/Users/yourname/` on Mac).

**Requires:** A RescueTime account (free tier works for basic tracking).

**Source:** Custom server in this repo at `scripts/mcps/rescuetime-server.py`. Built with [FastMCP](https://github.com/jlowin/fastmcp) against the [RescueTime Analytic API](https://www.rescuetime.com/rtx/documentation#api-reference).

---

### Recommended additional MCP servers (optional)

The Claude Code MCP ecosystem is growing fast. Other servers worth adding for a founder workflow:

- **Linear MCP** — issue/project tracking. Lets Claude read issue context and update statuses without you switching tabs.
- **Slack MCP** — read channel history, search past discussions, draft replies. Useful for "find that thing Sara said about pricing last month."
- **Gmail MCP** — read inbox, draft replies, search past threads.
- **Google Calendar MCP** — schedule meetings, find availability, check conflicts.
- **Google Drive MCP** — search/fetch Google Docs (essential if your team writes in Drive).
- **HubSpot MCP** — CRM integration if you don't use markdown CRM files.
- **Apollo MCP** — sales prospecting and enrichment.

Browse the [Anthropic MCP catalog](https://github.com/anthropics/claude-plugins-official) for the current list.

---

## Obsidian plugin stack

Install these via Obsidian Settings → Community Plugins → Browse. `/setup-brain` Phase 2 installs the core ones automatically.

### Required

- **[Dataview](https://github.com/blacksmithgu/obsidian-dataview)** — live queries against your vault. Powers the [dataview-queries.md](../templates/dataview-queries.md) library and the CRM mentions block. Without this, your CRM contact pages can't auto-list every place a person is mentioned.

- **[Templater](https://github.com/SilentVoid13/Templater)** — dynamic templates with JavaScript. Powers the journal entry template (auto-fills `creationDate`, `uuid`, prompts for floor), the CRM contact template, and the meeting note template.

### Strongly recommended

- **[Tasks](https://github.com/obsidian-tasks-group/obsidian-tasks)** — task tracking with due dates, recurring tasks, and dataview integration.

- **[YAML Properties](https://help.obsidian.md/properties)** — built into Obsidian 1.4+. Required for the frontmatter that drives all Dataview queries.

### Optional

- **[Bases](https://help.obsidian.md/bases)** — newer than Dataview, more spreadsheet-like. Good for CRM views.

- **[Outliner](https://github.com/vslinko/obsidian-outliner)** — better bullet list editing if you do a lot of nested outlining.

---

## How they fit together

This is the full stack working in concert:

1. **You write a daily journal** via `/journal` (a custom skill, not in this catalog — set up in `/setup-brain` Phase 10). Templater auto-fills the frontmatter.

2. **You run a meeting** with Granola recording. Afterward you say *"I just had a meeting with Sara"*. The meeting workflow rule in CLAUDE.md fires:
   - The Granola MCP fetches the transcript
   - Claude reads it fully
   - Updates the meeting note with decisions + action items + verbatim quotes
   - Updates Sara's CRM contact card via the mentions block (Dataview)
   - Adds her action items to your team to-do file
   - Cascades any strategy decisions to the relevant canonical docs
   - Runs `/humanizer` on any external-facing prose written

3. **You journal at the end of the day**. `/journal` captures the patterns it noticed across the week.

4. **Weekly:** you run `/graphify Journals --update` (incremental, ~free because of the cache). The graph stays current. You run `/insights` (or `/weekly`) which reads `journal-index.json` (built by `build-journal-index.py`) and surfaces patterns.

5. **Strategic moment:** you ask Claude *"what does my vault say about X?"*. Claude reads `graphify-out/GRAPH_REPORT.md` first (god nodes, communities, hyperedges) instead of grepping individual files. The answer comes with context, not just keyword matches.

6. **You write a pitch deck**. `nano-banana` generates the visuals. `humanizer` cleans the copy. The Decision Log records why you made each major framing call so you can grade them later.

None of these tools are mine. They're all open source by other people. What `/setup-brain` does is **install them and wire them together** with the right CLAUDE.md rules, templates, and folder structure so the whole stack acts like one tool.
