#!/usr/bin/env bash
#
# ai-brain-starter — one-command bootstrap (Mac + Linux)
#
# This script installs everything Phase 0 of /setup-brain installs, but without
# requiring you to launch Claude Code first. It's the "I just want to get
# started" path: run this once, then open Claude Code and type /setup-brain.
#
# Usage:
#     curl -fsSL https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.sh | bash
#
# What it installs:
#     - Homebrew (Mac only, if missing)
#     - Python 3.10+, Node.js, pipx, bun, gh
#     - graphify CLI + Claude skill (with optimization scripts)
#     - meeting-todos, patterns sub-skills
#     - claude-mem (marketplace + plugin)
#     - humanizer (de-AI writing)
#     - notebooklm (source-grounded answers)
#     - Granola MCP (meeting notes auto-sync)
#     - The ai-brain-starter skill itself
#
# What it does NOT install (because it requires manual steps inside Claude Code):
#     - nano-banana (image generation) — instructions printed at the end
#
# Safe to re-run. Skips anything already installed.

set -euo pipefail

REPO_URL="https://github.com/adelaidasofia/ai-brain-starter.git"
SKILL_DIR="$HOME/.claude/skills/ai-brain-starter"
FAILED=()

# ───────────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────────

log()  { printf "  \033[36m·\033[0m %s\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$*"; FAILED+=("$*"); }
hdr()  { printf "\n\033[1m%s\033[0m\n" "$*"; }

is_mac()   { [[ "$(uname -s)" == "Darwin" ]]; }
is_linux() { [[ "$(uname -s)" == "Linux" ]]; }

have() { command -v "$1" >/dev/null 2>&1; }

# ───────────────────────────────────────────────────────────────────────────────
# Checks
# ───────────────────────────────────────────────────────────────────────────────

hdr "ai-brain-starter — one-command install"
echo
echo "  This installs the full AI brain stack: graphify, humanizer, claude-mem,"
echo "  notebooklm, meeting-todos, patterns, the Granola MCP, plus the ai-brain-starter"
echo "  skill itself. Takes ~5 minutes the first time, ~10 seconds on re-runs."
echo
echo "  After this finishes, open Claude Code and type /setup-brain."
echo
sleep 1

# ───────────────────────────────────────────────────────────────────────────────
# Homebrew (Mac only)
# ───────────────────────────────────────────────────────────────────────────────

if is_mac && ! have brew; then
  hdr "Installing Homebrew"
  log "Homebrew is the package manager Mac uses for everything else here."
  log "It will ask for your Mac password — that's normal. You won't see characters as you type."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || err "homebrew install failed"
  # Add brew to PATH for the current session (Apple Silicon vs Intel)
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi

# ───────────────────────────────────────────────────────────────────────────────
# Python 3.10+
# ───────────────────────────────────────────────────────────────────────────────

if ! python3 -c "import sys; assert sys.version_info >= (3,10)" 2>/dev/null; then
  hdr "Installing Python 3.12"
  if is_mac; then
    brew install python@3.12 || err "python install failed"
  else
    sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip python3-venv 2>/dev/null \
      || sudo dnf install -y python3 python3-pip 2>/dev/null \
      || sudo pacman -S --noconfirm python python-pip 2>/dev/null \
      || err "python install failed (couldn't find apt/dnf/pacman)"
  fi
fi
have python3 && ok "python3 $(python3 --version | awk '{print $2}')"

# ───────────────────────────────────────────────────────────────────────────────
# Node.js + npm
# ───────────────────────────────────────────────────────────────────────────────

if ! have node; then
  hdr "Installing Node.js"
  if is_mac; then
    brew install node || err "node install failed"
  else
    sudo apt-get install -y nodejs npm 2>/dev/null \
      || sudo dnf install -y nodejs npm 2>/dev/null \
      || sudo pacman -S --noconfirm nodejs npm 2>/dev/null \
      || err "node install failed"
  fi
fi
have node && ok "node $(node --version)"
have npm  && ok "npm $(npm --version)"

# ───────────────────────────────────────────────────────────────────────────────
# pipx (Python app installer)
# ───────────────────────────────────────────────────────────────────────────────

if ! have pipx; then
  hdr "Installing pipx"
  if is_mac; then
    brew install pipx && pipx ensurepath || err "pipx install failed"
  else
    python3 -m pip install --user pipx && python3 -m pipx ensurepath || err "pipx install failed"
  fi
  # pipx ensurepath updates ~/.zshrc but doesn't affect this session
  export PATH="$HOME/.local/bin:$PATH"
fi
have pipx && ok "pipx $(pipx --version 2>/dev/null || echo installed)"

# ───────────────────────────────────────────────────────────────────────────────
# bun runtime (claude-mem dependency)
# ───────────────────────────────────────────────────────────────────────────────

if ! have bun && [[ ! -x "$HOME/.bun/bin/bun" ]]; then
  hdr "Installing bun"
  log "bun is the runtime claude-mem uses. Without it, claude-mem plugin commands fail silently."
  curl -fsSL https://bun.sh/install | bash >/dev/null 2>&1 || err "bun install failed"
fi
{ have bun || [[ -x "$HOME/.bun/bin/bun" ]]; } && ok "bun installed"

# ───────────────────────────────────────────────────────────────────────────────
# gh (GitHub CLI)
# ───────────────────────────────────────────────────────────────────────────────

if ! have gh; then
  hdr "Installing gh (GitHub CLI)"
  log "gh lets the session-end capture cascade file improvement ideas as GitHub issues automatically."
  if is_mac; then
    brew install gh || err "gh install failed"
  else
    sudo apt-get install -y gh 2>/dev/null \
      || sudo dnf install -y gh 2>/dev/null \
      || sudo pacman -S --noconfirm github-cli 2>/dev/null \
      || warn "couldn't auto-install gh — install it manually later if you need it"
  fi
fi
have gh && ok "gh $(gh --version 2>/dev/null | head -1 | awk '{print $3}')"

# gh authentication — required for the session-end capture cascade to file
# improvement ideas as GitHub issues automatically. Walk the user through it
# the first time only.
if have gh && ! gh auth status >/dev/null 2>&1; then
  hdr "GitHub authentication (one-time setup)"
  echo "  The session-end cascade can file improvement ideas as GitHub issues"
  echo "  automatically — but only if gh is authenticated to your GitHub account."
  echo
  echo "  This is a ONE-TIME setup. After this, your AI brain will silently file"
  echo "  any friction or improvement ideas to the maintainer's repo without"
  echo "  asking you to copy/paste anything."
  echo
  echo "  When you press Enter, gh will open a browser window for you to log in."
  echo "  Pick: GitHub.com → HTTPS → Login with web browser."
  echo
  read -p "  Press Enter to start (or Ctrl+C to skip — you can run 'gh auth login' later): " _
  gh auth login || warn "gh auth skipped or failed — run 'gh auth login' later to enable issue filing"
fi
gh auth status >/dev/null 2>&1 && ok "gh authenticated" || warn "gh not authenticated (issue filing disabled until you run: gh auth login)"

# ───────────────────────────────────────────────────────────────────────────────
# graphify CLI + Python package
# ───────────────────────────────────────────────────────────────────────────────

if ! have graphify; then
  hdr "Installing graphify (knowledge graph builder)"
  log "graphify reduces token usage by ~70% on vault queries. Most of this setup depends on it."
  pipx install graphifyy >/dev/null 2>&1 || err "graphifyy install failed"
  graphify install >/dev/null 2>&1 || err "graphify install failed"
fi
have graphify && ok "graphify $(graphify --version 2>/dev/null | head -1 || echo installed)"

# ───────────────────────────────────────────────────────────────────────────────
# Clone or update the ai-brain-starter skill
# ───────────────────────────────────────────────────────────────────────────────

hdr "Installing the ai-brain-starter skill"
mkdir -p "$HOME/.claude/skills"
if [[ -d "$SKILL_DIR/.git" ]]; then
  log "Already installed, pulling latest..."
  (cd "$SKILL_DIR" && git pull --quiet) || warn "git pull failed — using existing version"
else
  git clone --quiet "$REPO_URL" "$SKILL_DIR" || err "ai-brain-starter clone failed"
fi
[[ -f "$SKILL_DIR/SKILL.md" ]] && ok "ai-brain-starter skill at $SKILL_DIR"

# ───────────────────────────────────────────────────────────────────────────────
# Copy bundled sub-skills to ~/.claude/skills/
# ───────────────────────────────────────────────────────────────────────────────

hdr "Installing bundled sub-skills"
for sub in graphify meeting-todos patterns; do
  src="$SKILL_DIR/skills/$sub"
  dst="$HOME/.claude/skills/$sub"
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    cp -R "$src/." "$dst/" || err "$sub copy failed"
    ok "$sub skill installed"
  else
    err "$sub skill source missing in repo"
  fi
done

# ───────────────────────────────────────────────────────────────────────────────
# Humanizer
# ───────────────────────────────────────────────────────────────────────────────

if [[ ! -d "$HOME/.claude/skills/humanizer" ]]; then
  hdr "Installing humanizer (de-AI writing pass)"
  git clone --quiet https://github.com/adelaidasofia/humanizer.git "$HOME/.claude/skills/humanizer" \
    || err "humanizer clone failed"
fi
[[ -d "$HOME/.claude/skills/humanizer" ]] && ok "humanizer skill installed"

# ───────────────────────────────────────────────────────────────────────────────
# NotebookLM
# ───────────────────────────────────────────────────────────────────────────────

if [[ ! -d "$HOME/.claude/skills/notebooklm" ]]; then
  hdr "Installing notebooklm (source-grounded answers from your uploaded docs)"
  git clone --quiet https://github.com/PleasePrompto/notebooklm-skill.git "$HOME/.claude/skills/notebooklm" \
    || err "notebooklm clone failed"
fi
[[ -d "$HOME/.claude/skills/notebooklm" ]] && ok "notebooklm skill installed"

# ───────────────────────────────────────────────────────────────────────────────
# claude-mem (marketplace plugin + npx fallback)
# ───────────────────────────────────────────────────────────────────────────────

hdr "Installing claude-mem (cross-session memory)"
mkdir -p "$HOME/.claude"
python3 - <<'PY' || err "claude-mem marketplace registration failed"
import json, os
p = os.path.expanduser("~/.claude/settings.json")
try:
    with open(p) as f: s = json.load(f)
except FileNotFoundError:
    s = {}
s.setdefault("extraKnownMarketplaces", {})
if "thedotmack" not in s["extraKnownMarketplaces"]:
    s["extraKnownMarketplaces"]["thedotmack"] = {"source": {"source": "github", "repo": "thedotmack/claude-mem"}}
s.setdefault("enabledPlugins", {})
s["enabledPlugins"]["claude-mem@thedotmack"] = True
with open(p, "w") as f: json.dump(s, f, indent=2)
PY
npx --yes claude-mem install >/dev/null 2>&1 || true
ok "claude-mem registered (marketplace + plugin)"

# ───────────────────────────────────────────────────────────────────────────────
# Granola MCP (meeting workflow rule depends on this)
# ───────────────────────────────────────────────────────────────────────────────

hdr "Registering Granola MCP (meeting notes auto-sync)"
python3 - <<'PY' || err "granola MCP registration failed"
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
ok "Granola MCP registered (you'll need a Granola account to actually use it)"

# ───────────────────────────────────────────────────────────────────────────────
# Verification — NEVER FAIL SILENTLY
# ───────────────────────────────────────────────────────────────────────────────

hdr "Verifying installation"

CHECKS=(
  "graphify CLI:graphify"
  "node:node"
  "npm:npm"
  "pipx:pipx"
  "gh:gh"
)
for check in "${CHECKS[@]}"; do
  name="${check%%:*}"
  bin="${check##*:}"
  if have "$bin"; then
    ok "$name"
  else
    err "$name not callable"
  fi
done
{ have bun || [[ -x "$HOME/.bun/bin/bun" ]]; } && ok "bun" || err "bun not found"

# Skill folders
for sub in graphify meeting-todos patterns humanizer notebooklm ai-brain-starter; do
  if [[ -d "$HOME/.claude/skills/$sub" ]]; then
    ok "skill: $sub"
  else
    err "skill missing: $sub"
  fi
done

# graphify scripts present (the 80%-cost-cut wrappers)
[[ -d "$HOME/.claude/skills/graphify/scripts" ]] && ok "graphify scripts" || err "graphify scripts missing"

# Config files
grep -q "claude-mem@thedotmack" "$HOME/.claude/settings.json" 2>/dev/null \
  && ok "claude-mem registered in settings.json" \
  || err "claude-mem not in settings.json"
grep -q "granola" "$HOME/.claude/.mcp.json" 2>/dev/null \
  && ok "granola MCP in .mcp.json" \
  || err "granola not in .mcp.json"

echo
if [[ ${#FAILED[@]} -eq 0 ]]; then
  printf "\033[32m━━━ All checks passed. ━━━\033[0m\n\n"
else
  printf "\033[31m━━━ %d check(s) failed: ━━━\033[0m\n" "${#FAILED[@]}"
  for f in "${FAILED[@]}"; do printf "  • %s\n" "$f"; done
  echo
  echo "Don't proceed silently — fix these before running /setup-brain."
  echo "Re-running this script is safe and skips anything already installed."
fi

# ───────────────────────────────────────────────────────────────────────────────
# Next steps
# ───────────────────────────────────────────────────────────────────────────────

cat <<'EOF'

━━━ Next steps ━━━

  1. Open Claude Code in the directory where you want your vault to live.
     (For a NEW personal vault: a fresh empty folder.)
     (For JOINING an existing team vault: cd into the team vault folder first.)

  2. Type ONE of these:

       /setup-brain                  # New personal vault — full conversational setup
       /setup-brain join-team        # Joining an existing team vault — minimal, no
                                     # structure changes, just verifies + wires meeting tool

  3. The setup is conversational. Answer the questions Claude asks.

━━━ Optional — image generation ━━━

  Nano Banana (image generation via Google Gemini 3 Pro Image) is the one tool
  that can't auto-install from this script — it requires running /plugin
  commands inside Claude Code. After /setup-brain finishes, run these:

       /plugin marketplace add devonjones/devon-claude-skills
       /plugin install nano-banana@devon-claude-skills

  And add a Gemini API key to your shell profile (one time, persists forever):

       echo 'export GEMINI_API_KEY=your_key_here' >> ~/.zshrc
       source ~/.zshrc

  Get the key at https://ai.google.dev/

EOF
