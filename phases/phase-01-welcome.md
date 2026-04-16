## Phase 1: Language & Welcome

### Step 1.−1 — Detect mode: NEW PERSONAL VAULT vs JOINING EXISTING TEAM VAULT (run BEFORE the language question)

Before anything else, figure out what the user is trying to do. There are three modes:

**A. New personal vault** — fresh start, no existing vault. Walk through every phase.
**B. Joining an existing team vault** — someone else already set up a team vault and they're a new member joining. Skip structure-creation entirely; just verify Phase 0 is installed, fix any cwd-mismatch (see below), wire their meeting tool, and confirm. Should take <5 minutes.
**C. Upgrading their own existing vault** — they already ran setup once and want to add features or sync the latest CLAUDE.md template. Use the "Already Set Up?" branch at the top of this file.

**Auto-detection logic:**

```bash
# Look for an existing CLAUDE.md in the cwd, parent directories (up to 4 levels),
# and one level deep (subdirectories). The walk-down case catches the cwd-mismatch
# bug: a team member launches Claude from the wrapper folder (e.g. a Google Drive
# shared folder root) but the real CLAUDE.md is one level deeper, in the actual
# vault content subfolder.
# CLAUDE.md inside a subfolder of the launch directory.
CWD="$(pwd)"
FOUND_CLAUDE=""
DETECTED_PARENT_PATH=""

# Walk up
DIR="$CWD"
for _ in 1 2 3 4; do
  if [[ -f "$DIR/CLAUDE.md" ]]; then FOUND_CLAUDE="$DIR/CLAUDE.md"; break; fi
  PARENT="$(dirname "$DIR")"; [[ "$PARENT" == "$DIR" ]] && break; DIR="$PARENT"
done

# Walk one level down (catch cwd-mismatch)
if [[ -z "$FOUND_CLAUDE" ]]; then
  for sub in "$CWD"/*/; do
    if [[ -f "$sub/CLAUDE.md" ]]; then
      FOUND_CLAUDE="$sub/CLAUDE.md"
      DETECTED_PARENT_PATH="$sub"
      break
    fi
  done
fi
```

**Decision tree:**

- **Argument hint:** if the user invoked `/setup-brain join-team`, jump straight to mode B and skip the question below.
- **No CLAUDE.md found anywhere:** → mode A (new personal vault). Continue to Step 1.0.
- **CLAUDE.md found in cwd:** → mode C (upgrade their own vault). Use the "Already Set Up?" branch at the top of this file.
- **CLAUDE.md found in a parent directory** (and they're working in a subfolder of an existing vault): → ask "It looks like you're inside an existing vault at `<parent>`. Are you (1) joining this as a team member, (2) just adding work in a subfolder, or (3) starting fresh somewhere else?" → answer 1 routes to mode B; answer 3 routes them to a fresh directory and mode A.
- **CLAUDE.md found in a SUBFOLDER of the cwd** (the cwd-mismatch case): → this is a team-vault folder structure where the actual content lives one level deep — common with Google Drive / OneDrive / Dropbox shared folders that wrap a single content subfolder. Auto-fix it (next section). Then proceed to mode B.

### Step 1.−1a — Cwd-mismatch auto-fix (joining a team vault where the content is one level deep)

If `CLAUDE.md` was found in a subfolder of the cwd (not in the cwd itself), the user is in a team vault where the actual content folder is one level deep. This pattern is common for:

- Google Drive shared folders that contain a single subfolder of vault content
- OneDrive / Dropbox shared workspaces
- Manually-organized team folders where a top-level wrapper folder contains the actual vault

**The bug:** Claude Code only auto-loads CLAUDE.md from the cwd and walks UP, not DOWN. If the user launches Claude from the wrapper folder, the team CLAUDE.md is never loaded. Their session has no project context, the meeting workflow rule doesn't fire, the graph never gets read, and every answer is generic. The user can go DAYS without realizing.

**The auto-fix:** write a thin pointer CLAUDE.md at the cwd (the wrapper folder) that says "the real CLAUDE.md is in the subfolder — please load that file." Claude Code reads this pointer at session start, reads the pointed-at file, and the user gets full project context regardless of which folder they launched from.

```bash
# Only run if a subfolder CLAUDE.md was found AND the cwd doesn't already have one
if [[ -n "$DETECTED_PARENT_PATH" && ! -f "$CWD/CLAUDE.md" ]]; then
  REL_PATH="${DETECTED_PARENT_PATH%/}"
  REL_PATH="${REL_PATH##*/}"
  cat > "$CWD/CLAUDE.md" <<EOF
# Pointer to the real team vault CLAUDE.md

The actual project CLAUDE.md lives at \`$REL_PATH/CLAUDE.md\`. **Read that file at session start.** All project rules, the team context, the Knowledge Graph rule, and the meeting workflow rule live there.

This pointer file exists because Claude Code only auto-loads CLAUDE.md from the current working directory (and walks UP through parent directories). It does not walk DOWN into subfolders. The team vault's actual content lives in the \`$REL_PATH/\` subfolder, so without this pointer, every Claude session launched from this directory would miss the real CLAUDE.md and operate with no project context.

**Files of note (all inside \`$REL_PATH/\`):**
- \`CLAUDE.md\` — the real one
- \`⚙️ Meta/graphify-out/GRAPH_REPORT.md\` — read this first for any strategy question
- \`⚙️ Meta/graphify-out/graph.json\` — queryable knowledge graph

If you're a team member joining this vault, you can leave this pointer file in place — it's part of the team setup. Don't delete it.
EOF
  echo "✓ Wrote pointer CLAUDE.md at $CWD/CLAUDE.md → real one at $REL_PATH/CLAUDE.md"
fi
```

**Tell the user out loud:** "Heads up — I noticed your team vault has the real CLAUDE.md one folder deep (inside `<subfolder>`). Claude Code only loads CLAUDE.md from where you launch it, so I just wrote a tiny pointer file at the top level so every team member who runs Claude from this folder picks up the real one automatically. You won't have to think about it again."

### Step 1.−1b — Mode B: Joining an existing team vault (minimal setup)

If we routed to mode B (joining an existing team vault), do NOT run Phases 2, 3, 4, 5, 14, 15, 16, 19. The vault already exists; you'd just be duplicating work. Run only:

1. **Phase 0** — silent install of the dependencies (graphify, humanizer, etc.). The user may already have some of these from earlier conversations; the install commands are idempotent.
2. **Step 1.−1a** — write the cwd pointer if needed (above).
3. **Phase 11 — Meeting tool selection** (the new adaptive section, see below). Ask which tool they use and wire it up.
4. **A short verification block** — confirm the team CLAUDE.md is loadable, graphify is callable, and the meeting MCP is registered if applicable.
5. **Hand off** — say "You're ready. The team vault is at `<path>`. Open it in Claude Code from here and the real CLAUDE.md will load automatically. Try asking a question that uses the graph (e.g. *'what does our graph say about pricing?'*) to confirm the context is loading."

Don't ask the language question (1.0) or any of the personal-setup questions (1.1) — those are for new personal vaults only. The team vault already has its own CLAUDE.md with its own conventions.

### Step 1.0 — Languages (ASK FIRST, BEFORE ANYTHING ELSE)

Before any other question, ask **in English**:

> "Quick first question: **what languages do you usually take notes and journal in?** It can be one, two, three, whatever. Some people slip into a second language for emotional content, or use one language for work and another for personal stuff — that's normal, tell me all of them.
>
> Then: **which one is your primary?** (The one you think and write in most.) I'll run the rest of this setup in that primary language and build everything — your CLAUDE.md, your journal prompts, your concept notes, your folder names — in it. The other languages will get added as aliases on every concept note, so wikilinks resolve no matter which language you wrote the entry in."

Wait for their answer. Store it as:
- `PRIMARY_LANGUAGE` — the one language the whole bot runs in
- `SECONDARY_LANGUAGES` — list (possibly empty) of every other language they mentioned. These drive the alias generation later.

**CRITICAL: from this point forward, conduct EVERYTHING in their primary language.** This is not "translate the questions" — it's "be a native speaker of that language for the rest of the conversation." That includes:

- Every spoken/written prompt and explanation you give the user
- All folder names where idiomatic (e.g. Spanish: `📓 Diarios/`, `🏠 Casa/`, `📚 Libros/`, `📝 Notas/`, `👤 CRM/`, `⚙️ Meta/` — keep emojis, translate words; check with the user if they prefer English folder names for tooling reasons)
- The CLAUDE.md file content (rules, vault map, preferences — written in their language, not English)
- Journal interview questions
- Concept note descriptions, headings, and the floor framework labels
- Insight reports (`/weekly`, `/monthly`)
- Error messages and confirmations
- The names of canonical concept notes (e.g. Spanish primary → `Miedo.md` is the canonical file, `fear` is an alias; English primary with Spanish journaling → `Fear.md` is canonical, `miedo` is an alias)

If they pick a non-English primary language, do NOT default back to English mid-setup just because the SKILL.md is written in English. Translate every prompt as you go. If you don't know the idiomatic translation for a phrase, ask the user.

**Substack link override (Spanish only):** the SKILL.md links to the framework article at `https://adelaidadiazroa.substack.com/s/internal-design` (English) in several places. **Only swap it if the user picks Spanish** — in that case, replace every occurrence with `https://perspectivasblog.substack.com/s/el-rascacielos` (and use the Spanish title "El Rascacielos — el modelo del diseño interno"). For every other language (including English), leave the existing English URL as-is.

### Step 1.0b — Setup Version (ASK SECOND, after language)

Before the welcome interview, ask (in their primary language):

> "Quick question before we start building: **do you want the light or full setup?** Both work on any Claude plan. The only tradeoff is how much of your daily usage the system spends.
>
> I recommend **full** if you can spare the daily budget. It's the version the system was designed around, and the light version is genuinely a subset — useful, but missing the parts that make this feel like a second brain instead of a notes app.
>
> **Both versions include:** the daily journal interview, floor tagging (the High-Rise framework that maps where you're operating from), session memory, meeting workflow, file organization, and the core rules.
>
> **Full setup adds:**
> - **Advisory panel** — named voices in every journal entry that push back on your thinking, surface blind spots, and log dissent
> - **Knowledge graph** that maps connections across all your notes, people, projects, and decisions — surfaced automatically into conversation
> - **Automatic context routing** — when you mention a person, project, or concept, the relevant graph context loads without you asking
> - **Monthly insight reports** with pattern analysis (recurring themes, stuck loops, floor trends, decisions vs outcomes)
> - **Instinct Engine** (/patterns) — scans your journals and decisions for patterns you haven't noticed yet, and turns them into concrete rules
>
> **Light setup skips those five things.** You still get a real second brain — journaling with floor tagging, weekly summaries, session memory, meeting detection, file organization — just without the panel pushback, graph connections, and pattern surfacing that the system was designed around.
>
> Light uses noticeably less daily budget. Full uses more but gives you the pushback, pattern recognition, and connection-finding that makes this compounding instead of linear. Which do you want?"

Wait for their answer. Store it as:
- `PLAN_TIER` = `"light"` or `"full"`

If they're unsure, lean them toward full: "Honestly, full is what I'd pick. The panel and graph are the two things people say made the biggest difference. If you find the daily budget tight after a week, you can rerun setup and drop to light. Going the other way — starting light and adding later — works too, but you'll be less likely to discover what you're missing."

**Do not use the word "tokens" or "context window."** These are Claude-internal concepts. Say "daily usage" or "daily budget" if you need to reference limits. **Do not gate the choice by subscription plan (Pro/Max/Team).** Both options work on any plan; the tradeoff is usage cost, not plan tier.

This variable gates behavior in Phase 5 (hooks), Phase 10b (advisory panel), and Phase 18 (insights). See each phase file for the conditional logic.

### Step 1.1 — Welcome (in their language)

Now translate the welcome into their primary language and continue:

"Hey! I'm going to help you set up an AI-powered second brain. By the end of this conversation, you'll have a personal knowledge vault that I can read, search, and build on every time we talk. No more re-explaining yourself.

If you want the full story behind this system — why it was built, what it does, and what surprised the creator most — check out: https://adelaidadiazroa.substack.com/p/how-i-built-a-second-brain-that-actually

This takes about 2-3 hours if we do everything, or 30 minutes for the basics. We can go as deep as you want.

First — a few questions so I know what we're working with:"

Then ask these ONE AT A TIME. Wait for each answer before moving on:

1. "What's your name?"
2. "What do you do? (job, projects, passions — whatever matters to you)"
3. "Do you already have notes somewhere? (Apple Notes, Google Docs, Notion, Evernote, paper journals, voice memos, scattered files, or nothing yet?)"
4. "Have you ever journaled? (daily, occasionally, used to, never — doesn't matter either way, we're setting one up for you regardless)"
5. "**Do you write publicly?** (Blog, book, newsletter, Substack, Medium, LinkedIn posts — anything you write *for readers*, beyond private notes.) If not, that's totally fine — just say no, and I won't create a Writing folder for you."

**Store the answer as `WRITES_PUBLICLY` — true or false.** This gates whether a `✍️ Writing/` folder gets created in Phase 3, whether writing-related rules get added in Phase 4, and whether the humanizer rule fires in later sessions. Journaling does NOT count — journaling is for the user's own eyes and lives in `📓 Journals/`. Writing means content with an intended audience. If the answer is ambiguous ("kind of," "sometimes"), ask one follow-up: "Is anyone besides you reading it?" Only a clear yes creates a Writing folder.

6. **Obsidian check — DETECT FIRST, don't ask if it's already there.** The bootstrap auto-installs Obsidian, so by the time the user reaches /setup-brain it should already be present. Run the appropriate detection check FIRST and only fall through to asking if it's actually missing:

```bash
# Mac
[[ -d "/Applications/Obsidian.app" ]] && echo "OBSIDIAN_PRESENT" || echo "OBSIDIAN_MISSING"

# Linux
(command -v obsidian || [ -f "/var/lib/flatpak/exports/bin/md.obsidian.Obsidian" ] || [ -f "$HOME/.local/share/flatpak/exports/bin/md.obsidian.Obsidian" ] || [ -x "$HOME/.local/bin/obsidian" ]) && echo "OBSIDIAN_PRESENT" || echo "OBSIDIAN_MISSING"
```

```powershell
# Windows
$paths = @("$env:LOCALAPPDATA\Obsidian\Obsidian.exe", "$env:ProgramFiles\Obsidian\Obsidian.exe", "${env:ProgramFiles(x86)}\Obsidian\Obsidian.exe")
if ($paths | Where-Object { Test-Path -LiteralPath $_ }) { "OBSIDIAN_PRESENT" } else { "OBSIDIAN_MISSING" }
```

**If `OBSIDIAN_PRESENT`:** Skip the question entirely. Go straight to step 7 with: *"Obsidian is already installed (the bootstrap took care of that for you). Let's create your vault now."*

**If `OBSIDIAN_MISSING`** (the bootstrap was skipped or failed): re-run the bootstrap, which handles Obsidian install on Mac/Linux/Windows with all the platform fallbacks (brew, snap, flatpak, AppImage, winget):

```bash
# Mac/Linux
bash ~/.claude/skills/ai-brain-starter/bootstrap.sh
```

```powershell
# Windows
pwsh ~/.claude/skills/ai-brain-starter/bootstrap.ps1
```

Then say: *"I just installed Obsidian for you. Let's create your vault now."*

**Never** ask the user to "go download Obsidian" — that breaks the one-command promise and assumes they know what Obsidian is and how to install a desktop app.

7. "Now open Obsidian and choose 'Create new vault.' Name it whatever feels right — your name, 'Brain,' 'Notes,' whatever. Put it somewhere easy to find, like your Desktop. Let me know when it's created."

**Wait for confirmation before continuing.**

8. "Perfect. Now I need you to tell me the path to your vault. In Obsidian, go to Settings (gear icon) → About → look for 'Vault path.' Paste it here."

Save the vault path — you'll use it for all file operations.

