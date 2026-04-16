## Phase 0: Install Efficiency Tools First

**Do this silently before the conversation starts.** These tools reduce token usage for the entire setup, so they should be running before anything else.

First, detect the platform: Mac, Windows, or Linux. Then check what's already installed and install what's missing. Don't overwhelm the user with terminal output — just do it quietly.

**FIRST-RUN PROGRESS MESSAGE** — non-technical users will think nothing is happening if Claude goes silent during installs. Before any install runs, tell the user (in their primary language once Phase 1 step 1.0 has run; before that, in English):

> "Setting up the tools you'll need — give me a moment. This usually takes 2–3 minutes the first time, or just a few seconds if you've already run the bootstrap. I'll keep you posted as each piece installs."

Then for each install (graphify, humanizer, granola, etc.), give a brief one-line confirmation when it completes: *"Graphify ready ✓"*, *"Humanizer ready ✓"*. This tells the user the system is alive and reduces the "is this thing frozen?" anxiety. Don't dump command output — one line per tool is enough.

If everything installs cleanly, end Phase 0 with: *"All tools ready. Now let's get you set up."*

If any tool failed, list which ones failed and offer: *"A couple of tools didn't install (listed above). I'll work around them for now and we can retry at the end. None of them are blocking what we're about to do."*

The legacy intro line — *"I need to install a couple of tools first that will make this whole setup faster and use less of your subscription. This takes a few minutes."* — is acceptable if you prefer; just don't go silent for minutes.

### Mac
```bash
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

# gh (GitHub CLI) — needed for the session-close repo-update propagation rule,
# and for any user who'll fork ai-brain-starter and push improvements back
if ! command -v gh &>/dev/null; then brew install gh; fi

# Graphify — ~70% fewer tokens on vault queries. CRITICAL: most of this setup
# (the meeting workflow, the Knowledge Graph rule, /weekly insights, the
# Decision Log queries) depends on graphify being callable. If this install
# fails, the verification block at the end of Phase 0 catches it.
if ! command -v graphify &>/dev/null; then pipx install graphifyy && graphify install; fi

# FastMCP — framework for building custom MCP servers in minimal Python.
# Needed when building custom connectors (CRM bridges, vault sync, etc.)
if ! command -v fastmcp &>/dev/null; then pipx install fastmcp; fi

# Sub-skills bundled in this repo — copy the FULL folders so the wrapper
# scripts come along too. (Plain `cp SKILL.md` misses the scripts/ folders
# where the cost-cutting optimizations live.) Copy ALL sub-skills here
# instead of deferring to later phases — Phase 0 must leave a working stack
# even if the user stops the conversation early.
mkdir -p ~/.claude/skills/graphify ~/.claude/skills/meeting-todos ~/.claude/skills/patterns \
        ~/.claude/skills/insights ~/.claude/skills/deconstruct ~/.claude/skills/daily-journal \
        ~/.claude/skills/repurpose-talk ~/.claude/skills/nano-banana
cp -R ~/.claude/skills/ai-brain-starter/skills/graphify/.        ~/.claude/skills/graphify/
cp -R ~/.claude/skills/ai-brain-starter/skills/meeting-todos/.   ~/.claude/skills/meeting-todos/
cp -R ~/.claude/skills/ai-brain-starter/skills/patterns/.        ~/.claude/skills/patterns/
cp -R ~/.claude/skills/ai-brain-starter/skills/insights/.        ~/.claude/skills/insights/
cp -R ~/.claude/skills/ai-brain-starter/skills/deconstruct/.     ~/.claude/skills/deconstruct/
cp -R ~/.claude/skills/ai-brain-starter/skills/daily-journal/.   ~/.claude/skills/daily-journal/
cp -R ~/.claude/skills/ai-brain-starter/skills/repurpose-talk/.  ~/.claude/skills/repurpose-talk/
cp -R ~/.claude/skills/ai-brain-starter/skills/nano-banana/.     ~/.claude/skills/nano-banana/

# Marketplace plugins — register obsidian-skills + enable context7/playwright
mkdir -p ~/.claude
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.claude/settings.json")
try:
    with open(p) as f:
        s = json.load(f)
except FileNotFoundError:
    s = {}
s.setdefault("extraKnownMarketplaces", {})
if "obsidian-skills" not in s["extraKnownMarketplaces"]:
    s["extraKnownMarketplaces"]["obsidian-skills"] = {
        "source": {"source": "github", "repo": "kepano/obsidian-skills"}
    }
s.setdefault("enabledPlugins", {})
s["enabledPlugins"]["obsidian@obsidian-skills"] = True
s["enabledPlugins"]["context7"] = True
s["enabledPlugins"]["playwright"] = True
with open(p, "w") as f:
    json.dump(s, f, indent=2)
print("registered obsidian marketplace + enabled plugins")
print("enabled context7 plugin (up-to-date library docs for coding sessions)")
print("enabled playwright plugin (headless browser automation + test suites)")
PY

# Humanizer — de-AI writing
if [ ! -d ~/.claude/skills/humanizer ]; then
  git clone https://github.com/adelaidasofia/humanizer.git ~/.claude/skills/humanizer
fi

# Granola MCP — meeting notes auto-sync. The "I just had a meeting" workflow
# rule in CLAUDE.md depends on this MCP. Without it, the rule fires but
# can't fetch the transcript. Wire it now so the rule works on day 1.
#
# IMPORTANT FOR NON-TECHNICAL USERS: registering the MCP is only HALF the
# install. The user must ALSO have a Granola account and have signed in to
# the Granola Mac/Web app at least once — otherwise the MCP returns "not
# authenticated" silently and the meeting workflow fails with no obvious
# cause. After this script runs, Claude MUST tell the user (in their primary
# language) the post-install authorization step. See the message below.
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.claude/.mcp.json")
try:
    with open(p) as f:
        m = json.load(f)
except FileNotFoundError:
    m = {"mcpServers": {}}
m.setdefault("mcpServers", {})
if "granola" not in m["mcpServers"]:
    m["mcpServers"]["granola"] = {
        "type": "url",
        "url": "https://mcp.granola.ai/mcp"
    }
    print("registered granola MCP")
if "chatprd" not in m["mcpServers"]:
    m["mcpServers"]["chatprd"] = {
        "type": "url",
        "url": "https://app.chatprd.ai/mcp"
    }
    print("registered chatprd MCP")
with open(p, "w") as f:
    json.dump(m, f, indent=2)
else:
    print("granola MCP already registered")
PY

# POST-INSTALL: tell the user about the Granola authorization step.
# This is REQUIRED non-tech-friendly UX — never assume they know that
# registering an MCP isn't the same as logging in.
#
# Claude says: "I just wired up Granola so meeting notes can auto-sync into
# your vault. One more step on YOUR side: Granola needs you to log in to
# their app at least once before the connection works. Want me to walk you
# through it?"
#
# If they say yes:
#   1. "Go to https://granola.ai and click 'Download for Mac' (or Windows
#      if/when they support it). Install it like any other app."
#   2. "Open Granola and log in — you can use Google or email, whichever you
#      prefer. The free plan is fine for now."
#   3. "Once you're logged in and you see the main Granola window, you're
#      done. Come back and tell me 'Granola is set up' and I'll verify."
#   4. After they confirm, run a quick MCP probe to verify connectivity.
#   5. If the probe fails, tell them: "The MCP is registered but I can't
#      reach Granola yet — make sure you're actually logged in to the Granola
#      app, then we'll retry."
#
# If they say no / "I don't use Granola":
#   - Remove the granola entry from .mcp.json (don't leave a dead MCP wired).
#   - Tell them: "No problem — I removed the Granola wiring. If you ever want
#      meeting auto-sync later, we can re-wire it then."
#   - Remember this answer — store NO_GRANOLA=true so the meeting workflow
#     rule installs in 'manual' mode instead of expecting Granola.

# Nano Banana — image generation via Google Gemini 3 Pro Image. OPTIONAL.
# DEFERRED: do NOT install during Phase 0. The setup requires three steps that
# all involve API jargon (marketplace add, plugin install, env var with API
# key from a separate Google product) and the average user doesn't need image
# generation on day 1. Defer install until the user explicitly asks ("I want
# to generate an image", "can you make a logo", etc.). At that point Claude
# walks them through it interactively with concrete clicks:
#
#   1. "We need three things: the nano-banana plugin, a Gemini API key, and
#      one quick environment variable. I'll do the first two with you and the
#      third one for you."
#   2. "First, in this Claude Code window, type:
#         /plugin marketplace add devonjones/devon-claude-skills
#      Then press Enter and wait for it to confirm."
#   3. "Now type:
#         /plugin install nano-banana@devon-claude-skills
#      Press Enter, wait for confirm."
#   4. "Now we need a free API key from Google. I'll open the page for you —
#      just go to https://ai.google.dev/, click 'Get API key' in the top
#      right, sign in with a Google account if asked, click 'Create API key',
#      and copy the key it gives you. It looks like a long string starting
#      with 'AI'. Paste it back to me when you have it."
#   5. After they paste the key, write it to their shell profile for them:
#        Mac/Linux: append `export GEMINI_API_KEY="<key>"` to ~/.zshrc and
#                   ~/.bash_profile, then source the active one.
#        Windows:   run `setx GEMINI_API_KEY "<key>"` so it persists.
#   6. Tell them: "Done. Try '/nano-banana create a logo of a blue mountain'
#      to test it."
#
# DO NOT mention nano-banana during Phase 0 setup. DO NOT add it to the
# Phase 0 verification block. Mentioning a feature the user didn't ask for
# and then walking them through API key setup as a "required step" is
# exactly the kind of friction non-technical users abandon over.
```

### Verification (NEVER FAIL SILENTLY — run this immediately after the Mac/Linux block above)

After installing everything above, run a verification block that checks every tool actually landed and reports failures explicitly. **This is non-negotiable** — silent failures mean the user thinks Phase 0 worked, then hits a broken `/graphify` or missing meeting workflow rule weeks later with no idea why.

```bash
echo "=== Phase 0 Verification ==="
FAILED=()

# CLI tools
command -v brew >/dev/null    || FAILED+=("brew (Homebrew)")
command -v python3 >/dev/null && python3 -c "import sys; assert sys.version_info >= (3,10)" 2>/dev/null \
                              || FAILED+=("python3 >= 3.10")
command -v node >/dev/null    || FAILED+=("node")
command -v npm >/dev/null     || FAILED+=("npm")
command -v pipx >/dev/null    || FAILED+=("pipx")
command -v graphify >/dev/null || FAILED+=("graphify CLI")
command -v gh >/dev/null      || FAILED+=("gh (GitHub CLI)")

# Skill folders
[ -d ~/.claude/skills/graphify ]      && [ -d ~/.claude/skills/graphify/scripts ] || FAILED+=("graphify skill folder (with scripts/)")
[ -d ~/.claude/skills/meeting-todos ] || FAILED+=("meeting-todos skill folder")
[ -d ~/.claude/skills/patterns ]      || FAILED+=("patterns skill folder")
[ -d ~/.claude/skills/insights ]      || FAILED+=("insights skill folder")
[ -d ~/.claude/skills/deconstruct ]   || FAILED+=("deconstruct skill folder")
[ -d ~/.claude/skills/daily-journal ] || FAILED+=("daily-journal skill folder")
[ -d ~/.claude/skills/repurpose-talk ]|| FAILED+=("repurpose-talk skill folder")
[ -d ~/.claude/skills/nano-banana ]   || FAILED+=("nano-banana skill folder")
[ -d ~/.claude/skills/humanizer ]     || FAILED+=("humanizer skill folder")

# Config files
[ -f ~/.claude/.mcp.json ]     && grep -q "granola" ~/.claude/.mcp.json \
                              || FAILED+=("Granola MCP entry in ~/.claude/.mcp.json")

if [ ${#FAILED[@]} -eq 0 ]; then
  echo "✓ Phase 0 complete — every dependency installed and verified."
else
  echo "✗ Phase 0 finished with ${#FAILED[@]} failure(s):"
  printf '  - %s\n' "${FAILED[@]}"
  echo
  echo "Tell the user EXACTLY which items failed and offer to retry each one."
  echo "Do NOT proceed silently. The downstream phases assume these are working."
fi
```

If anything fails, **tell the user immediately** with the exact failure list, why it matters, and the retry command. This rule exists because of a real incident: a co-founder's Phase 0 run left graphify partially installed, the team CLAUDE.md was never auto-loaded, and the broken state stayed invisible for days. Never let that happen again.

### Windows
```
# Check for winget (built into Windows 11 and recent Windows 10)
winget --version

# Check for Python 3.10+
python --version

# If Python is missing or below 3.10 — install it automatically via winget:
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
# After installing, restart the shell session so PATH is updated:
refreshenv 2>/dev/null || $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Check for Node.js
node --version

# If Node.js is missing — install it automatically via winget:
winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
# Refresh PATH again after install

# After Python and Node are confirmed:
pip install pipx
pipx ensurepath

# gh (GitHub CLI) — used by the session-close repo-update propagation rule
winget install -e --id GitHub.cli --accept-source-agreements --accept-package-agreements

# Graphify
pipx install graphifyy
graphify install --platform windows

:: Copy ALL sub-skills from the repo
for %%S in (graphify meeting-todos patterns insights deconstruct daily-journal repurpose-talk nano-banana) do (
  mkdir %USERPROFILE%\.claude\skills\%%S 2>nul
  xcopy /E /I /Y %USERPROFILE%\.claude\skills\ai-brain-starter\skills\%%S\* %USERPROFILE%\.claude\skills\%%S\
)

# Humanizer
git clone https://github.com/adelaidasofia/humanizer.git %USERPROFILE%\.claude\skills\humanizer

# Granola MCP — meeting workflow rule depends on this
python -c "import json, os; p = os.path.expanduser('~/.claude/.mcp.json'); m = {'mcpServers': {}}; ^
exec('try:\n  m = json.load(open(p))\nexcept: pass'); ^
m.setdefault('mcpServers', {}).setdefault('granola', {'type': 'url', 'url': 'https://mcp.granola.ai/mcp'}); ^
json.dump(m, open(p, 'w'), indent=2)"

# Nano Banana — image generation via Gemini 3 Pro Image
:: Tell the user:
:: "Run /plugin marketplace add devonjones/devon-claude-skills, then
:: /plugin install nano-banana@devon-claude-skills. You'll also need a
:: GEMINI_API_KEY from https://ai.google.dev/, set as a Windows env var:
:: setx GEMINI_API_KEY your_key_here"
```

**Run the same verification block** (the Mac/Linux version) using Git Bash on Windows. PowerShell users can adapt with `Test-Path` and `Get-Command` checks; the failure list pattern stays the same.

**If winget is not available** (older Windows): install via official installers using the Bash tool to download and run them silently:
```
# Python silent install
curl -o python-installer.exe https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe
Start-Process python-installer.exe -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait

# Node.js silent install  
curl -o node-installer.msi https://nodejs.org/dist/lts/node-v20-x64.msi
Start-Process msiexec -ArgumentList "/i node-installer.msi /quiet /norestart" -Wait
```
Tell the user: "Installing Python and Node.js for you — this takes a minute." Do not ask them to download anything manually.

### Linux
```
# Check Python 3.10+
python3 --version

# If missing or below 3.10 — install automatically:
sudo apt-get update && sudo apt-get install -y python3 python3-pip   # Ubuntu/Debian
# or: sudo dnf install python3 python3-pip                           # Fedora/RHEL
# or: sudo pacman -S python python-pip                               # Arch

# Check Node.js
node --version

# If missing — install automatically:
sudo apt-get install -y nodejs npm   # Ubuntu/Debian
# or: sudo dnf install nodejs        # Fedora/RHEL
# or: sudo pacman -S nodejs npm      # Arch

# After Python and Node are confirmed:
pip install pipx && pipx ensurepath

# gh (GitHub CLI) used by the session-close repo-update propagation rule
if ! command -v gh >/dev/null; then
  sudo apt-get install -y gh 2>/dev/null || sudo dnf install -y gh 2>/dev/null || sudo pacman -S --noconfirm github-cli 2>/dev/null || true
fi

# Graphify
pipx install graphifyy && graphify install

# Sub-skills bundled in this repo — copy ALL so Phase 0 leaves a working
# stack even if the user stops the conversation early.
mkdir -p ~/.claude/skills/graphify ~/.claude/skills/meeting-todos ~/.claude/skills/patterns \
        ~/.claude/skills/insights ~/.claude/skills/deconstruct ~/.claude/skills/daily-journal \
        ~/.claude/skills/repurpose-talk ~/.claude/skills/nano-banana
cp -R ~/.claude/skills/ai-brain-starter/skills/graphify/.        ~/.claude/skills/graphify/
cp -R ~/.claude/skills/ai-brain-starter/skills/meeting-todos/.   ~/.claude/skills/meeting-todos/
cp -R ~/.claude/skills/ai-brain-starter/skills/patterns/.        ~/.claude/skills/patterns/
cp -R ~/.claude/skills/ai-brain-starter/skills/insights/.        ~/.claude/skills/insights/
cp -R ~/.claude/skills/ai-brain-starter/skills/deconstruct/.     ~/.claude/skills/deconstruct/
cp -R ~/.claude/skills/ai-brain-starter/skills/daily-journal/.   ~/.claude/skills/daily-journal/
cp -R ~/.claude/skills/ai-brain-starter/skills/repurpose-talk/.  ~/.claude/skills/repurpose-talk/
cp -R ~/.claude/skills/ai-brain-starter/skills/nano-banana/.     ~/.claude/skills/nano-banana/

# Humanizer
git clone https://github.com/adelaidasofia/humanizer.git ~/.claude/skills/humanizer

# Granola MCP — meeting workflow rule depends on this
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.claude/.mcp.json")
try:
    with open(p) as f: m = json.load(f)
except FileNotFoundError:
    m = {"mcpServers": {}}
m.setdefault("mcpServers", {})
if "granola" not in m["mcpServers"]:
    m["mcpServers"]["granola"] = {"type": "url", "url": "https://mcp.granola.ai/mcp"}
    with open(p, "w") as f: json.dump(m, f, indent=2)
PY

# Nano Banana — image generation (marketplace install, user must run from inside Claude Code):
# /plugin marketplace add devonjones/devon-claude-skills
# /plugin install nano-banana@devon-claude-skills
# Plus a GEMINI_API_KEY from https://ai.google.dev/ (export in ~/.bashrc or ~/.zshrc to persist)
```

**Run the verification block** (same as the Mac section above) immediately after the Linux install. The bash syntax is identical and the failure modes are the same.

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

### Knowledge Graph context loading (add to user's CLAUDE.md after first /graphify run)

Once the user has run `/graphify` at least once and has `graphify-out/graph.json` + `graphify-out/GRAPH_REPORT.md`, their CLAUDE.md should include a "Knowledge Graph" rule that tells Claude to use the graph as the **primary** strategic context source. Draft template to append:

```markdown
## Knowledge Graph — CHECK THIS FIRST FOR STRATEGY / ANALYSIS

This vault has a knowledge graph at `graphify-out/`. It's the fastest and most accurate way to get strategic context. **For any question that spans multiple concepts, start here before reading individual files.**

**Context-loading decision tree:**

| Question type | Start with | Then drill into |
|---|---|---|
| Strategy / pitch / planning / multi-concept | `graphify-out/GRAPH_REPORT.md` (god nodes + communities + hyperedges) | Top 3-5 source files in the relevant community |
| "What connects X and Y?" | `/graphify path "X" "Y"` | Shortest-path files |
| "What's in the vault about X?" | `/graphify explain "X"` | Top-degree neighbors |
| "Find files mentioning X" | `obsidian search query="X"` | Matching files |
| "What links to this file?" | `obsidian backlinks file="Name"` | Source of each backlink |
| Editing a specific file | `Read` the file directly | — |

**Rules:**
1. **For strategic or multi-concept questions, ALWAYS read `GRAPH_REPORT.md` first.** It compresses the vault's structural thinking.
2. **Use `/graphify query "<question>"` instead of reading 5 files** when you need a connected subgraph with source citations.
3. **Use `/graphify path "A" "B"` for cross-concept connections.**
4. **Update the graph after any significant writing session:** `/graphify <path> --update`. The cache makes incremental runs essentially free.
5. **When merging duplicate concept nodes, update aliases in the canonical file's frontmatter — don't rename or delete.** This preserves existing `[[Old Name]]` wikilinks. See `⚙️ Meta/Graphify Runbook.md`.
```

Skip this block if the user hasn't run `/graphify` yet — but mention it in the setup summary so they know to add it after the first run.

After Phase 0 completes, tell the user: "I installed a few tools in the background that make everything faster and more efficient. Now let's get started with you."

