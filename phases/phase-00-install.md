## Phase 0: Install Efficiency Tools First

**Do this silently before the conversation starts.** All mechanical installs live in `bootstrap.sh` (Mac/Linux) and `bootstrap.ps1` (Windows) at the repo root. Phase 0 is a thin orchestrator: detect platform, invoke bootstrap, handle the conversational follow-ups, then hand off to Phase 1.

**Why one source of truth?** The install list (brew/python/node/pipx/gh/fastmcp, graphify, humanizer, all bundled sub-skills, Granola + ChatPRD MCPs, the obsidian-skills and vendor skill-pack marketplaces, context7/playwright plugins, Obsidian app, Obsidian CLI symlink) used to live in two places: bootstrap scripts AND this phase file. They drifted. Now bootstrap is canonical. Every line of install logic lives there, on every platform. Phase 0 never copies bash.

---

### Step 0.0. Progress message (before anything runs)

Non-technical users will think nothing is happening if Claude goes silent during installs. Before invoking bootstrap, say (English by default; Spanish once Phase 1 step 1.0 has run):

> "Setting up the tools you'll need, give me a moment. This usually takes 2 to 3 minutes the first time, or just a few seconds if you've already run the bootstrap. I'll keep you posted as each piece installs."

As bootstrap prints its own check-mark lines per tool, you don't need to narrate each one. The output is already reassuring. Chime in once at the end: *"All tools ready. Now let's get you set up."* Or, on failure: *"A couple of tools didn't install (listed above). I'll work around them for now and we can retry at the end. None of them are blocking what we're about to do."*

**One exception to "work around it" — the Terminal step.** If the bootstrap prints `TERMINAL STEP NEEDED` (this happens on a Mac when Homebrew is missing: it needs the Mac password, which you cannot type from a non-interactive session), do NOT work around it and do NOT install Homebrew yourself. Relay the exact one-line Terminal command the bootstrap printed to the user, verbatim, ask them to run it and reply when it finishes, then continue. That one command does every password-gated install (Homebrew, Obsidian, gh) and re-runs the rest idempotently. See Step 0.1b.

**DO NOT use the Monitor tool on bootstrap output.** Monitor renders every stdout line as a separate "Human:" turn in the conversation transcript — empty lines from brew/npm chatter included. Users see a wall of bare `Human:` labels interspersed with progress messages and leaked `<task-notification>` XML blocks. Bootstrap's own stdout is already user-visible — just `Bash(bash bootstrap.sh)` and let it print directly. If you want async progress, set `run_in_background: true` on the Bash call and read the result when it finishes. Monitor is for log-streaming long-running daemons, not installers.

---

### Step 0.0b. Tell the user about the trust prompt before it appears

The bootstrap registers third-party plugin marketplaces and MCP servers (see the install table in Step 0.1). Once that happens, Claude Code shows its **built-in trust prompt** for the third-party content. You cannot suppress that prompt, and you should not want to. It is a real safety feature. But a non-technical user who hits it cold, with no warning, reads it as "malicious software is sneaking onto my machine," panics, and abandons the install. This has happened to a real installer.

So get ahead of it. **Before** you invoke the bootstrap (or the instant you see the prompt appear, whichever comes first), tell the user, in their language, something close to this:

> "Heads up on one thing: in a moment Claude Code will pause and ask you to approve the tools we're installing. It may warn that they come from third parties or are not verified by Anthropic. That is Claude Code's normal safety check for anything that did not come from Anthropic itself, not a sign that anything is wrong. It is safe to approve. Everything being added is listed, with licenses, in the project's README. Go ahead and approve it when you see it, and I'll keep going."

For Spanish-speaking installs, the same beat in voseo register (peer-to-peer, not a translation):

> "Ojo con una cosa: Claude Code va a frenar en un momento para pedirte que apruebes las herramientas que estamos instalando. Te puede avisar, en un tono firme, que son de terceros o que Anthropic no las verificó. Ese es su chequeo de seguridad normal para cualquier cosa que no venga directo de Anthropic, no una señal de que algo esté mal. Es seguro aprobarlo. Todo lo que se está agregando está listado, con licencias, en el README del proyecto. Cuando aparezca, dale aprobar y seguimos."

Adapt the wording to the user and the moment; do not read it robotically. The non-negotiable part: before they read the prompt themselves, the user must KNOW it is coming, that it is expected, and that approving is the normal choice. Never let the trust prompt be the first time they hear of it. An unframed trust prompt is the single most common reason a non-technical install gets abandoned.

### Step 0.0c. The command-approval prompt is also expected — push through it, never menu

Separately from the trust prompt above, Claude Code may also ask the user to approve the install **command** itself (the `git clone` / bootstrap run), depending on their permission mode. That approval is a normal part of the install, not a wall. When it appears, tell the user to approve it (or, in a stricter mode, to allow the command) so you can continue — exactly as you pre-framed the trust prompt.

If a command is declined or a stricter permission mode blocks it, **ask the user to approve it and continue. Do NOT fall back to a menu of install methods, and do NOT downgrade to a `/plugin install`-only shortcut** — that adds the plugin's skills but skips the system tools, MCP wiring, and vault setup, so it is not the full install. A permission prompt is a click, not a reason to stop.

---

### Step 0.1. Invoke the bootstrap

The install does not gate on email. Do NOT ask the user for an email or a name before running the installer — just run it. The setup interview makes one optional email ask at the very end (Phase 24.4).

By the time `/setup-brain` fires, the ai-brain-starter skill folder already exists at `~/.claude/skills/ai-brain-starter/` (that's how Claude Code found this phase file). So the bootstrap is always a local invocation, never a fresh curl. It is idempotent: safe on fresh machines and on re-runs. It skips anything already installed.

Detect platform with `uname -s` (Mac/Linux) or `$PSVersionTable` (Windows), then run the matching bootstrap:

#### Mac / Linux

```bash
bash "$HOME/.claude/skills/ai-brain-starter/bootstrap.sh"
```

#### Windows

```powershell
& "$env:USERPROFILE\.claude\skills\ai-brain-starter\bootstrap.ps1"
```

If the user reached /setup-brain WITHOUT running bootstrap first (rare), the repo was cloned another way (ai-brain-starter skill folder exists but bootstrap hasn't run). Invoking the local bootstrap above still does the full install. The clone-and-run commands in the bootstrap's own header comment are only for users who set things up BEFORE opening Claude Code.

**What bootstrap installs (for your awareness; do NOT re-install these yourself):**

| Category | Items |
|---|---|
| CLI tools | Homebrew (Mac), Python 3.10+, Node.js, pipx, gh, fastmcp, Claude Code |
| Desktop apps | Obsidian (via brew/winget/snap/flatpak/AppImage), Obsidian CLI symlink (Mac) |
| Graphify | graphifyy Python package + `graphify install` (platform binary) |
| Sub-skills | graphify, meeting-todos, patterns, insights, deconstruct, daily-journal, repurpose-talk, nano-banana (skill folder only; plugin install is deferred) |
| Humanizer | cloned from its own public fork (idempotent, never touched on re-run) |
| MCPs | granola + chatprd (registered in ~/.claude/.mcp.json with backup) |
| Marketplaces / plugins | obsidian-skills (kepano), enabling obsidian/context7/playwright; PLUS seven vendor skill-pack marketplaces (getsentry, trailofbits, stripe, cloudflare, AgriciDaniel/claude-seo, obra/superpowers, coreyhaines31/marketingskills), skippable with SKIP_VENDOR_SKILLS=1. These third-party marketplaces are what trigger Claude Code's trust prompt; pre-frame it per Step 0.0b. |

**Bootstrap does NOT touch:**
- The user's vault CLAUDE.md (vault path isn't known until Phase 5)
- **The three vault-content hooks** — `graph-context-hook.sh`, `write-hook.sh`, `session-end-hook.sh` — which live INSIDE the vault. Bootstrap DOES wire the user-level hooks that need no vault (closing-signal, frontmatter lint, skill-usage log, the meeting-workflow trigger) into `~/.claude/settings.json`, but these three are deferred to `/setup-brain` (phase-05) and wired with the real vault path once the vault exists. Wiring them earlier against a placeholder `$HOME` path is what produced the dead `~/⚙️ Meta/scripts/` hooks that errored on every prompt / write / session-end and forced a removal decision on the user mid-install (MYC-739). `install-hooks-user-level.py` now omits any vault-content hook when invoked without a `--vault-path`.
- nano-banana plugin binary (needs `/plugin install` inside Claude Code plus a Gemini API key; deferred until the user actually asks for image generation. See Step 0.4 below)
- Any custom skills, MCPs, marketplaces, permissions, or env vars already present

**If bootstrap fails any check**, it prints an explicit failure list. Tell the user exactly which items failed and offer to retry each one. Do NOT proceed silently. Downstream phases assume these are working. This rule exists because of a real incident where a user's Phase 0 run left graphify partially installed and the broken state stayed invisible for days.

---

### Step 0.1b. The Terminal step (Mac password / Homebrew) — relay it, don't route around it

On a Mac, if Homebrew isn't installed, the bootstrap can't install it from inside Claude Code: Homebrew's installer needs the Mac password at an interactive prompt, and Claude Code's shell has no way to type it. When that happens, the bootstrap stops cleanly and prints a block headed `TERMINAL STEP NEEDED` (Spanish: `PASO EN LA TERMINAL`) containing one command, then exits 0.

This is expected and is the normal recovery — **not** a failure to work around. When you see it:

1. Show the user the exact one-line command from that block, verbatim (it is `bash ~/.claude/skills/ai-brain-starter/bootstrap.sh`). Tell them to open Terminal (`Cmd+Space`, type "terminal", Return), paste it, press Return, and type their Mac password when asked (the screen stays blank while they type — that's normal Mac security).
2. Wait for them to reply that it finished. Do **not** continue the setup interview until they confirm.
3. Then continue. That one Terminal command installs Homebrew, Obsidian, gh, and everything else, and re-runs the whole bootstrap idempotently, so by the time they're back everything is in place.

Do NOT try to install Homebrew yourself, do NOT "work around" it by skipping Obsidian (the entire vault lives in Obsidian), and do NOT downgrade to a partial install. A single framed Terminal step is the whole fix. Most users who followed the web guide already ran Homebrew in Terminal first, in which case the bootstrap finds it and this step never appears.

---

### Step 0.2. Granola setup check (conversational)

Ask:

> "Do you use Granola for meeting notes?"

**If YES:**
1. "Granola syncs via its official Public API. Generate an API key in Granola (Settings > Connectors > API keys), save it to `~/.config/granola/api-key` (chmod 600), then run `python3 scripts/granola_sync.py --health` to verify the key and `python3 scripts/granola_sync.py --dry-run` to preview what would export."
2. For auto-export every 2 hours, offer to install the LaunchAgent: "Set the script path + log path in `scripts/com.granola-export.plist`, copy it to `~/Library/LaunchAgents/`, then run `launchctl load ~/Library/LaunchAgents/com.granola-export.plist`."
3. Store `GRANOLA=api` so the meeting workflow rule knows to Glob for `*- Transcript.md` files.

**If NO / "I don't use Granola":**
- Store `NO_GRANOLA=true` so the meeting workflow rule installs in 'manual' mode.
- "No problem. If you ever want Granola auto-sync later, the script is at `scripts/granola_sync.py`."

---

### Step 0.3. Obsidian CLI confirmation

On Mac the bootstrap attempts a `/usr/local/bin/obsidian` symlink. Check whether it succeeded:

```bash
command -v obsidian >/dev/null 2>&1 && echo "cli ok" || echo "cli missing"
```

If present, note it in the Phase 5 CLAUDE.md rules: *"Use Obsidian CLI for fast vault queries: search, backlinks, unresolved links, orphans, dead ends."*

If missing (older Obsidian, sudo declined, Windows, Linux without the CLI binary): skip silently. The vault works fine without it. Claude uses file search instead.

---

### Step 0.4. Nano-banana (DEFERRED, do not install in Phase 0)

The nano-banana skill folder is synced by bootstrap so `/nano-banana` is discoverable. The actual plugin binary plus Gemini API key setup is deferred until the user explicitly asks for image generation ("I want to generate an image", "can you make a logo", etc.). At that moment, walk them through it interactively:

1. "We need three things: the nano-banana plugin, a Gemini API key, and one environment variable. I'll do the first two with you and the third one for you."
2. "In this Claude Code window, type: `/plugin marketplace add devonjones/devon-claude-skills` and press Enter."
3. "Now type: `/plugin install nano-banana@devon-claude-skills` and press Enter."
4. "Now we need a free API key from Google. Go to https://ai.google.dev/, click 'Get API key' top-right, sign in with Google, click 'Create API key', copy the key (starts with 'AI'). Paste it back to me."
5. After they paste: write it to their shell profile for them.
   - Mac/Linux: append `export GEMINI_API_KEY="<key>"` to `~/.zshrc` and `~/.bash_profile`, source the active one.
   - Windows: `setx GEMINI_API_KEY "<key>"` so it persists.
6. "Done. Try '/nano-banana create a logo of a blue mountain' to test."

**Do NOT mention nano-banana during Phase 0.** Mentioning a feature the user didn't ask for and then walking them through API key setup as a "required step" is exactly the kind of friction non-technical users abandon over.

---

### Step 0.5. GitHub — no action needed

Bootstrap installs `gh` silently but does NOT prompt for auth. Connecting GitHub is never required. If the user asks about it later, say: "If you ever want it, just run `gh auth login` once and it'll wire up automatically." Don't mention it proactively.

---

### Step 0.6. Knowledge Graph CLAUDE.md rule (deferred until first /graphify run)

Once the user has run `/graphify` at least once and has `graphify-out/graph.json` plus `graphify-out/GRAPH_REPORT.md`, their CLAUDE.md should include a Knowledge Graph rule pointing Claude there as the **primary** strategic context source. Draft template to append:

```markdown
## Knowledge Graph: CHECK THIS FIRST FOR STRATEGY / ANALYSIS

This vault has a knowledge graph at `graphify-out/`. It's the fastest and most accurate way to get strategic context. **For any question that spans multiple concepts, start here before reading individual files.**

**Context-loading decision tree:**

| Question type | Start with | Then drill into |
|---|---|---|
| Strategy / pitch / planning / multi-concept | `graphify-out/GRAPH_REPORT.md` (god nodes + communities + hyperedges) | Top 3-5 source files in the relevant community |
| "What connects X and Y?" | `/graphify path "X" "Y"` | Shortest-path files |
| "What's in the vault about X?" | `/graphify explain "X"` | Top-degree neighbors |
| "Find files mentioning X" | `obsidian search query="X"` | Matching files |
| "What links to this file?" | `obsidian backlinks file="Name"` | Source of each backlink |
| Editing a specific file | `Read` the file directly | . |

**Rules:**
1. **For strategic or multi-concept questions, ALWAYS read `GRAPH_REPORT.md` first.** It compresses the vault's structural thinking.
2. **Use `/graphify query "<question>"` instead of reading 5 files** when you need a connected subgraph with source citations.
3. **Use `/graphify path "A" "B"` for cross-concept connections.**
4. **Update the graph after any significant writing session:** `/graphify <path> --update`. The cache makes incremental runs essentially free.
5. **When merging duplicate concept nodes, update aliases in the canonical file's frontmatter. Don't rename or delete.** This preserves existing `[[Old Name]]` wikilinks. See your vault's Graphify Runbook.
```

Skip this block if the user hasn't run `/graphify` yet. Mention it in the setup summary so they know to add it after the first run.

---

### Closing line

After Phase 0 completes cleanly:

> "I installed a few tools in the background that make everything faster and more efficient. Now let's get started with you."

Then proceed to Phase 1.
