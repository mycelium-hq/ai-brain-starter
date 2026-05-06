#!/usr/bin/env bash
#
# ai-brain-starter — one-command bootstrap (Mac + Linux)
#
# This script installs everything Phase 0 of the setup-brain skill installs.
# It runs in two modes:
#   - Inside Claude Code (from the README paste-flow): Claude invokes this
#     as part of end-to-end setup and continues into the interview after.
#   - Standalone (curl-to-bash from a terminal): tools get installed, then
#     the Next-Steps block tells the user to open Claude Code and paste the
#     setup prompt. Detection is via $CLAUDE_CODE_ENTRYPOINT.
#
# Usage:
#     curl -fsSL https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.sh | bash
#
# What it installs:
#     - Homebrew (Mac only, if missing)
#     - Python 3.10+, Node.js, pipx, gh, fastmcp
#     - Claude Code (via npm) and Obsidian (desktop app)
#     - graphify CLI + Claude skill (with optimization scripts)
#     - All bundled sub-skills: graphify, meeting-todos, patterns, insights,
#       deconstruct, daily-journal, repurpose-talk, nano-banana (skill docs only)
#     - humanizer (de-AI writing) — cloned from its own fork repo
#     - Granola + ChatPRD MCPs
#     - Marketplace: obsidian-skills (kepano); plugins: obsidian, context7, playwright
#     - Mac: Obsidian CLI symlink to /usr/local/bin/obsidian (if the app ships it)
#     - The ai-brain-starter skill itself
#
# What it does NOT install (requires marketplace commands inside Claude Code):
#     - nano-banana plugin (image generation backend) — the SKILL FOLDER is
#       synced above so /nano-banana is discoverable, but the actual plugin
#       needs /plugin install + a Gemini API key. Instructions printed at end.
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SAFETY GUARANTEES — for users with existing setups + custom integrations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# This script is safe to run on top of an existing setup. Specifically:
#
#   1. ~/.claude/settings.json — backed up to settings.json.bak-YYYY-MM-DD-HHMM
#      before edit. Existing custom marketplaces, plugins, MCP servers,
#      permissions, env vars, and any other keys are preserved
#      (setdefault() never overwrites existing values).
#
#   2. ~/.claude/.mcp.json — backed up to .mcp.json.bak-YYYY-MM-DD-HHMM before
#      edit. Only adds the granola MCP entry if not already present. Custom
#      MCP servers (Linear, Slack, Notion, anything else you wired yourself)
#      are preserved.
#
#   3. ~/.claude/skills/ai-brain-starter — if there are local uncommitted
#      changes to your clone, they're stashed (git stash push -u) BEFORE the
#      git pull, so your work is recoverable via `git stash pop`. The script
#      tells you exactly how to recover.
#
#   4. ~/.claude/skills/{graphify,meeting-todos,patterns} — synced via
#      sync-skills.sh which implements backup-before-overwrite. Any installed
#      file that differs from the repo version is backed up to
#      <file>.bak-YYYY-MM-DD-HHMM before being replaced. Local customizations
#      are recoverable.
#
#   5. ~/.claude/skills/humanizer: installed only if the folder doesn't exist
#      (idempotent git clone). NEVER touched on re-run, so your forks,
#      customizations, or local edits to this skill are 100% safe.
#
#   6. ~/.claude/skills/{anything else} — NOT TOUCHED. Custom skills you
#      installed yourself (daily-journal, your own forks, third-party skills
#      from other marketplaces) are completely untouched.
#
#   7. ~/.claude/.mcp.json custom MCP servers — preserved (see #2).
#
#   8. Your vault's CLAUDE.md — NOT TOUCHED by this script. The bootstrap
#      doesn't know where your vault is and doesn't modify any vault files.
#      The new session-start update check rule and session-end capture rule
#      are added to your vault CLAUDE.md only when you explicitly run
#      /setup-brain (new vault) or /setup-brain upgrade (existing vault).
#
#   9. gh authentication — only prompts if `gh auth status` reports unauthed.
#      Existing gh logins are preserved.
#
#   10. Homebrew, Python, Node, pipx, gh, graphifyy — all installed only
#       if missing. Existing versions are kept as-is.
#
#   11. ~/.claude/skills/{graphify,meeting-todos,patterns} with their own .git/
#       — DETECTED AS A FORK and SKIPPED ENTIRELY. If you cloned your own
#       customized version of one of these skills (e.g. your own graphify
#       fork with custom rules), the bootstrap will not touch it. You manage
#       updates yourself.
#
#   12. ~/.claude/skills/{anything} that is a SYMLINK — bootstrap warns
#       before writing through the symlink, since the target may be a shared
#       location you didn't intend to modify.
#
#   13. ~/.claude/skills/ai-brain-starter with DIVERGENT history (your local
#       clone has commits not on origin/main) — bootstrap REFUSES TO PULL
#       and tells you to merge manually. Your fork is never silently
#       overwritten.
#
# IF SOMETHING DOES GO WRONG — every backup is timestamped and recoverable.
# Look for *.bak-YYYY-MM-DD-HHMM files in ~/.claude/ and the affected skill
# folders. To restore: `mv <file>.bak-YYYY-MM-DD-HHMM <file>`.
#
# DRY RUN — pass --dry-run to see exactly what the bootstrap WOULD do without
# making any changes:
#     bash bootstrap.sh --dry-run
#
# Safe to re-run anytime. Skips anything already installed and only updates
# what's actually behind. Ends with a summary of every change made.

set -euo pipefail

REPO_URL="https://github.com/adelaidasofia/ai-brain-starter.git"
SKILL_DIR="$HOME/.claude/skills/ai-brain-starter"
DRY_RUN=0
FAILED=()
INSTALLED=()
UPDATED=()
SKIPPED=()
BACKUPS=()
CLEANED=()

# === Forensics: persistent log file ===
# Closes adelaidasofia/ai-brain-starter#3 — every bootstrap run writes a
# timestamped log to ~/.claude/.bootstrap.log (rotated when >5MB). When something
# breaks weeks later, the log is the forensic source of truth.
BOOTSTRAP_LOG="$HOME/.claude/.bootstrap.log"
mkdir -p "$HOME/.claude" 2>/dev/null || true

# Rotate if log is large
if [[ -f "$BOOTSTRAP_LOG" ]]; then
  log_size=$(stat -f %z "$BOOTSTRAP_LOG" 2>/dev/null || stat -c %s "$BOOTSTRAP_LOG" 2>/dev/null || echo 0)
  if [[ "$log_size" -gt 5242880 ]]; then
    mv "$BOOTSTRAP_LOG" "${BOOTSTRAP_LOG}.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
  fi
fi

# Parse args (must happen before tee setup so --help doesn't pollute the log)
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    --restore)
      # Closes adelaidasofia/ai-brain-starter#2 — auto-restore from .bak files
      RESTORE_SCRIPT="$SKILL_DIR/scripts/bootstrap-restore.sh"
      if [[ ! -f "$RESTORE_SCRIPT" ]]; then
        # Fallback: maintainer location
        [[ -f "$HOME/Desktop/ai-brain-starter/scripts/bootstrap-restore.sh" ]] && \
          RESTORE_SCRIPT="$HOME/Desktop/ai-brain-starter/scripts/bootstrap-restore.sh"
      fi
      if [[ -f "$RESTORE_SCRIPT" ]]; then
        shift_args=("$@")
        # Drop --restore from args we forward
        forward_args=()
        for a in "${shift_args[@]}"; do
          [[ "$a" == "--restore" ]] || forward_args+=("$a")
        done
        exec bash "$RESTORE_SCRIPT" "${forward_args[@]}"
      else
        echo "ERROR: bootstrap-restore.sh not found. Run bootstrap.sh first to install it." >&2
        exit 2
      fi ;;
    --smoke-test|--verify)
      SMOKE_SCRIPT="$SKILL_DIR/scripts/post-install-smoke-test.sh"
      [[ ! -f "$SMOKE_SCRIPT" ]] && [[ -f "$HOME/Desktop/ai-brain-starter/scripts/post-install-smoke-test.sh" ]] && \
        SMOKE_SCRIPT="$HOME/Desktop/ai-brain-starter/scripts/post-install-smoke-test.sh"
      if [[ -f "$SMOKE_SCRIPT" ]]; then
        exec bash "$SMOKE_SCRIPT"
      else
        echo "ERROR: post-install-smoke-test.sh not found." >&2
        exit 2
      fi ;;
    --detect-partial)
      DETECT_SCRIPT="$SKILL_DIR/scripts/detect-partial-installs.sh"
      [[ ! -f "$DETECT_SCRIPT" ]] && [[ -f "$HOME/Desktop/ai-brain-starter/scripts/detect-partial-installs.sh" ]] && \
        DETECT_SCRIPT="$HOME/Desktop/ai-brain-starter/scripts/detect-partial-installs.sh"
      if [[ -f "$DETECT_SCRIPT" ]]; then
        exec bash "$DETECT_SCRIPT"
      else
        echo "ERROR: detect-partial-installs.sh not found." >&2
        exit 2
      fi ;;
    --install-hooks-user-level)
      # Closes adelaidasofia/ai-brain-starter#6 — install hooks at user level
      # so they fire universally, including inside .claude/worktrees/<name>/.
      INSTALLER="$SKILL_DIR/scripts/install-hooks-user-level.py"
      [[ ! -f "$INSTALLER" ]] && [[ -f "$HOME/Desktop/ai-brain-starter/scripts/install-hooks-user-level.py" ]] && \
        INSTALLER="$HOME/Desktop/ai-brain-starter/scripts/install-hooks-user-level.py"
      if [[ -f "$INSTALLER" ]]; then
        forward_args=()
        for a in "$@"; do
          [[ "$a" == "--install-hooks-user-level" ]] || forward_args+=("$a")
        done
        exec python3 "$INSTALLER" "${forward_args[@]}"
      else
        echo "ERROR: install-hooks-user-level.py not found." >&2
        exit 2
      fi ;;
    --help|-h)
      cat <<'HELP'
Usage: bash bootstrap.sh [OPTIONS]

Install or update the ai-brain-starter setup. Safe to re-run.

Options:
  --dry-run, -n                 Show what would be installed without making changes
  --restore                     Interactive restore from .bak files (closes #2)
  --smoke-test                  Run end-to-end verification of the installed setup
  --detect-partial              Scan for half-installed components (closes #4)
  --install-hooks-user-level    Install hooks at user level (closes #6 — fires
                                universally including inside git worktrees)
  --help, -h                    This help

Logs: every run is appended to ~/.claude/.bootstrap.log (closes #3).
HELP
      exit 0 ;;
  esac
done

# Tee subsequent output to the log (header + everything that follows)
exec > >(tee -a "$BOOTSTRAP_LOG") 2>&1
printf "\n=== bootstrap run %s (PID %d) ===\n" "$(date +%Y-%m-%dT%H:%M:%S)" "$$" >> "$BOOTSTRAP_LOG"

# ───────────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────────

log()  { printf "  \033[36m·\033[0m %s\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$*"; FAILED+=("$*"); }
hdr()  { printf "\n\033[1m%s\033[0m\n" "$*"; }
dry()  { printf "  \033[35m[dry-run]\033[0m %s\n" "$*"; }

is_mac()   { [[ "$(uname -s)" == "Darwin" ]]; }
is_linux() { [[ "$(uname -s)" == "Linux" ]]; }

have() { command -v "$1" >/dev/null 2>&1; }

# ───────────────────────────────────────────────────────────────────────────────
# Locale detection + bilingual translation helper
# Override via BOOTSTRAP_LANG=es|en. Otherwise: $LC_ALL > $LANG > AppleLocale > en.
# ───────────────────────────────────────────────────────────────────────────────
detect_lang() {
  local raw="${BOOTSTRAP_LANG:-${LC_ALL:-${LANG:-}}}"
  if [[ -z "$raw" ]] && is_mac; then
    raw="$(defaults read -g AppleLocale 2>/dev/null || true)"
  fi
  [[ -z "$raw" ]] && raw="en_US"
  [[ "${raw:0:2}" == "es" ]] && echo "es" || echo "en"
}
LANG_CODE="$(detect_lang)"
t() { [[ "$LANG_CODE" == "es" ]] && echo "$2" || echo "$1"; }

# ───────────────────────────────────────────────────────────────────────────────
# Email gate (universal). Every install passes through the form once. The form
# at https://myceliumai.co/install captures email + context, mints a 32-char
# token, and emails the install command. Bootstrap validates the token and
# writes a marker file. Future bootstrap re-runs find the marker and skip the
# gate. Existing users (no marker yet) get the same prompt on their next run.
#
# Bypass for development: EMAIL_GATE_BYPASS=1 bash bootstrap.sh
# ───────────────────────────────────────────────────────────────────────────────
EMAIL_MARKER="$HOME/.claude/.ai-brain-starter-email-on-file"
INSTALL_API_BASE="${MYCELIUM_INSTALL_API:-https://myceliumai.co}"

if [[ "${EMAIL_GATE_BYPASS:-0}" != "1" && $DRY_RUN -eq 0 && ! -f "$EMAIL_MARKER" ]]; then
  hdr "$(t "Email gate (one-time)" "Verificación de email (una sola vez)")"
  if [[ -z "${TOKEN:-}" ]]; then
    # No token. Print the form URL + how to re-run with the token.
    cat <<EOF

  $(t "We need your email before installing the second brain." \
        "Necesitamos tu email antes de instalar el segundo cerebro.")

  $(t "This is a one-time gate. Once you submit the form, you get a token by" \
        "Esto es una sola vez. Una vez completes el formulario, recibís un token")
  $(t "email; future re-runs skip this prompt." \
        "por email; las próximas corridas saltean este paso.")

  1. $(t "Open this URL in your browser:" "Abrí este URL en tu navegador:")
     https://myceliumai.co/install
     ($(t "Spanish:" "Español:") https://myceliumai.co/es/install)

  2. $(t "Fill out the short form. Takes about 4 minutes." \
          "Completá el formulario corto. Tarda unos 4 minutos.")

  3. $(t "Check your email. You'll receive your personalized install command." \
          "Revisá tu email. Vas a recibir tu comando de instalación personalizado.")

  4. $(t "Either paste that full command into Claude Code (recommended)," \
          "Pegá ese comando completo en Claude Code (recomendado),")
     $(t "OR re-run this script with the token:" "O volvé a correr este script con el token:")

         TOKEN=<your-token-from-email> bash $0

EOF
    exit 3
  fi

  # Token provided — validate against the API.
  TOKEN="$(echo "$TOKEN" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  if [[ ! "$TOKEN" =~ ^[a-f0-9]{32}$ ]]; then
    err "$(t "Token shape invalid. Expected 32 hex characters." \
            "Formato de token inválido. Esperaba 32 caracteres hexadecimales.")"
    exit 4
  fi
  log "$(t "Validating token against $INSTALL_API_BASE..." \
          "Validando token contra $INSTALL_API_BASE...")"
  set +e
  VERIFY_RESP="$(curl -sS -m 10 "$INSTALL_API_BASE/api/install/verify?token=$TOKEN" 2>/dev/null)"
  set -e
  if [[ -z "$VERIFY_RESP" ]] || ! echo "$VERIFY_RESP" | grep -q '"valid":true'; then
    REASON="$(echo "${VERIFY_RESP:-}" | grep -oE '"reason":"[^"]+"' | sed 's/.*"reason":"\([^"]*\)".*/\1/' || true)"
    err "$(t \
      "Token validation failed (reason: ${REASON:-unknown}). Get a fresh token at https://myceliumai.co/install and re-run." \
      "Falló la validación del token (motivo: ${REASON:-desconocido}). Conseguí un token nuevo en https://myceliumai.co/install y volvé a correr.")"
    exit 4
  fi
  ok "$(t "Token valid. Recording email-on-file marker." \
          "Token válido. Guardando marca de email-en-archivo.")"
  mkdir -p "$HOME/.claude"
  printf '%s\n' "$TOKEN" > "$EMAIL_MARKER"
  chmod 600 "$EMAIL_MARKER"
fi

# ───────────────────────────────────────────────────────────────────────────────
# Pre-flight gate (skip with PREFLIGHT_BYPASS=1)
# Refuses to install on RED. Continues on YELLOW/GREEN.
# ───────────────────────────────────────────────────────────────────────────────
PREFLIGHT_SCRIPT_LOCAL="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/scripts/preflight.sh"
PREFLIGHT_SCRIPT_INSTALLED="$HOME/.claude/skills/ai-brain-starter/scripts/preflight.sh"
PREFLIGHT_TO_RUN=""
[[ -f "$PREFLIGHT_SCRIPT_LOCAL" ]] && PREFLIGHT_TO_RUN="$PREFLIGHT_SCRIPT_LOCAL"
[[ -z "$PREFLIGHT_TO_RUN" && -f "$PREFLIGHT_SCRIPT_INSTALLED" ]] && PREFLIGHT_TO_RUN="$PREFLIGHT_SCRIPT_INSTALLED"

if [[ "${PREFLIGHT_BYPASS:-0}" != "1" && -n "$PREFLIGHT_TO_RUN" && $DRY_RUN -eq 0 ]]; then
  hdr "$(t "Pre-flight check" "Verificación previa")"
  log "$(t \
    "Verifying every prerequisite before any tool is installed." \
    "Verificando cada requisito antes de instalar nada.")"
  set +e
  bash "$PREFLIGHT_TO_RUN"
  PREFLIGHT_RC=$?
  set -e
  if [[ $PREFLIGHT_RC -eq 2 ]]; then
    printf "\n\033[31m%s\033[0m\n" "$(t \
      "Bootstrap aborted: pre-flight found blockers. Fix them and re-run." \
      "Bootstrap detenido: la verificación previa encontró bloqueantes. Arreglalos y volvé a correr.")"
    printf "  %s\n" "$(t "To bypass during development: PREFLIGHT_BYPASS=1 bash bootstrap.sh" \
                          "Para saltarla en desarrollo: PREFLIGHT_BYPASS=1 bash bootstrap.sh")"
    exit 2
  fi
fi

# Run a command, OR print what it would do in dry-run mode.
# Usage: do_cmd "human description" actual command...
do_cmd() {
  local desc="$1"; shift
  if [[ $DRY_RUN -eq 1 ]]; then
    dry "$desc"
    return 0
  fi
  "$@"
}

# Backup a file before editing it. No-op in dry-run.
backup_file() {
  local f="$1"
  [[ ! -f "$f" ]] && return 0
  local bak="${f}.bak-$(date +%Y-%m-%d-%H%M)"
  if [[ $DRY_RUN -eq 1 ]]; then
    dry "would back up: $f → $bak"
  else
    cp "$f" "$bak"
    BACKUPS+=("$bak")
  fi
}

# ───────────────────────────────────────────────────────────────────────────────
# Header
# ───────────────────────────────────────────────────────────────────────────────

hdr "$(t "ai-brain-starter — one-command install" "ai-brain-starter — instalación de un solo comando")"
echo
if [[ $DRY_RUN -eq 1 ]]; then
  printf "  \033[35m%s\033[0m %s\n\n" \
    "$(t "DRY RUN MODE" "MODO DE PRUEBA")" \
    "$(t "— showing what would be installed without making any changes." \
         "— mostrando lo que se instalaría sin hacer cambios reales.")"
fi
echo "  $(t \
  "This installs the full AI brain stack: graphify, humanizer," \
  "Esto instala el stack completo de AI brain: graphify, humanizer,")"
echo "  $(t \
  "meeting-todos, patterns, the Granola MCP, plus the ai-brain-starter" \
  "meeting-todos, patterns, el MCP de Granola, y la skill ai-brain-starter")"
echo "  $(t \
  "skill itself. Takes ~5 minutes the first time, ~10 seconds on re-runs." \
  "misma. Tarda ~5 minutos la primera vez, ~10 segundos en recorridas siguientes.")"
echo
echo "  $(t \
  "When it's done, Claude continues with the setup interview automatically." \
  "Cuando termine, Claude continúa con la entrevista de setup automáticamente.")"
echo "  $(t "You don't need to type anything." "No necesitás tipear nada.")"
echo
[[ $DRY_RUN -eq 0 ]] && sleep 1

# ───────────────────────────────────────────────────────────────────────────────
# Cleanup deprecated tools
# Tools removed from the bundled stack are cleaned up automatically here.
# No action needed from the user — if something is detected, it's gone.
# ───────────────────────────────────────────────────────────────────────────────

hdr "Cleaning up deprecated tools"

# claude-mem (removed 2026-04-16): unauthenticated local HTTP API, arbitrary
# file-read surface, API keys in plaintext, and a hook that injected content
# into every session. The built-in memory system covers all use cases safely.
SETTINGS="$HOME/.claude/settings.json"
_claude_mem_present=0
if [[ -f "$SETTINGS" ]] && python3 -c "
import json, sys
try:
    s = json.load(open('$SETTINGS'))
    has_mkt = 'thedotmack' in s.get('extraKnownMarketplaces', {})
    has_plug = s.get('enabledPlugins', {}).get('claude-mem@thedotmack') is not False and 'claude-mem@thedotmack' in s.get('enabledPlugins', {})
    sys.exit(0 if (has_mkt or has_plug) else 1)
except: sys.exit(1)
" 2>/dev/null; then
  _claude_mem_present=1
fi

if [[ $_claude_mem_present -eq 1 ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then
    dry "would remove claude-mem from settings.json (marketplace + plugin entry)"
  else
    backup_file "$SETTINGS"
    python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.claude/settings.json")
s = json.load(open(p))
s.get("extraKnownMarketplaces", {}).pop("thedotmack", None)
ep = s.get("enabledPlugins", {})
ep.pop("claude-mem@thedotmack", None)
with open(p, "w") as f: json.dump(s, f, indent=2)
PY
    ok "Removed claude-mem — had security issues (open local HTTP port, file-read surface). Built-in memory covers everything it did."
    CLEANED+=("claude-mem")
  fi
else
  ok "claude-mem not present — nothing to clean"
fi

# notebooklm skill (removed 2026-04-16): Chromium browser automation +
# Google auth dance added friction that wasn't worth it for most users.
# If you actively use it, it still works — just not bundled by default.
NOTEBOOKLM_DIR="$HOME/.claude/skills/notebooklm"
if [[ -d "$NOTEBOOKLM_DIR" ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then
    dry "would remove $NOTEBOOKLM_DIR (notebooklm skill)"
  else
    rm -rf "$NOTEBOOKLM_DIR"
    ok "Removed notebooklm — rarely used, required browser automation + Google login on every session. If you want it back: git clone https://github.com/PleasePrompto/notebooklm-skill.git ~/.claude/skills/notebooklm"
    CLEANED+=("notebooklm")
  fi
else
  ok "notebooklm not present — nothing to clean"
fi

# ───────────────────────────────────────────────────────────────────────────────
# Homebrew (Mac only)
# ───────────────────────────────────────────────────────────────────────────────

if is_mac && ! have brew; then
  hdr "$(t "Installing Homebrew" "Instalando Homebrew")"
  log "$(t \
    "Homebrew is the package manager Mac uses for everything else here." \
    "Homebrew es el gestor de paquetes que Mac usa para todo lo demás acá.")"
  log ""
  log "  ⚠️  $(t "HEADS UP: Homebrew will ask for your Mac password in a moment." \
                  "AVISO: Homebrew va a pedirte tu contraseña de Mac en un momento.")"
  log "  ⚠️  $(t "When the prompt appears, type your password and press Enter." \
                  "Cuando aparezca el prompt, tipeá tu contraseña y presioná Enter.")"
  log "  ⚠️  $(t "YOU WILL NOT SEE CHARACTERS AS YOU TYPE — that's normal Mac security." \
                  "NO VAS A VER LOS CARACTERES MIENTRAS TIPIÁS — es normal en Mac.")"
  log "  ⚠️  $(t "DO NOT CLOSE THIS WINDOW. The install takes ~2 minutes after the password." \
                  "NO CIERRES ESTA VENTANA. La instalación tarda ~2 minutos después de la contraseña.")"
  log ""
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || err "$(t "homebrew install failed" "falló la instalación de Homebrew")"
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
# Claude Code (Anthropic's CLI/desktop app — REQUIRED for /setup-brain)
# Without this, the user has no way to actually run the skill they just installed.
# Distributed via npm so the install path is identical on Mac, Linux, and Windows
# once Node is present.
# ───────────────────────────────────────────────────────────────────────────────

if ! have claude; then
  hdr "$(t "Installing Claude Code" "Instalando Claude Code")"
  log "$(t \
    "Claude Code is Anthropic's developer tool that runs the AI brain skill." \
    "Claude Code es la herramienta de Anthropic para developers que corre la skill del AI brain.")"
  log "$(t \
    "It's different from claude.ai (the chat website) — this one lives in your terminal" \
    "Es diferente de claude.ai (el sitio web de chat) — este vive en tu terminal")"
  log "$(t \
    "and can read and write files in your vault. We're installing it via npm." \
    "y puede leer y escribir archivos en tu vault. Lo instalamos vía npm.")"
  npm install -g @anthropic-ai/claude-code 2>/dev/null \
    || err "$(t "Claude Code install failed — install manually with: npm install -g @anthropic-ai/claude-code" \
               "Falló la instalación de Claude Code — instalalo manual con: npm install -g @anthropic-ai/claude-code")"
fi
have claude && ok "claude $(claude --version 2>/dev/null | head -1 || echo installed)"

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
# gh (GitHub CLI) — installed silently, NO auth prompt
# Auth is never required for the core setup. If the user wants to log in
# later (for issue filing), they can run: gh auth login
# ───────────────────────────────────────────────────────────────────────────────

if ! have gh; then
  hdr "Installing gh (GitHub CLI)"
  if is_mac; then
    brew install gh || warn "gh install failed — non-blocking, continue"
  else
    sudo apt-get install -y gh 2>/dev/null \
      || sudo dnf install -y gh 2>/dev/null \
      || sudo pacman -S --noconfirm github-cli 2>/dev/null \
      || warn "couldn't auto-install gh — non-blocking, install later if needed"
  fi
fi
have gh && ok "gh $(gh --version 2>/dev/null | head -1 | awk '{print $3}')" || true
# No auth prompt — connecting GitHub is never required for the brain setup.

# ───────────────────────────────────────────────────────────────────────────────
# Obsidian — REQUIRED, the entire setup writes notes into an Obsidian vault.
# Auto-install via brew --cask (Mac) / snap or flatpak (Linux). Never ask the
# user to "go download" anything — that breaks the one-command promise and
# assumes they know what Obsidian is and how to install a desktop app.
# ───────────────────────────────────────────────────────────────────────────────

if is_mac; then
  if [[ ! -d "/Applications/Obsidian.app" ]]; then
    hdr "$(t "Installing Obsidian" "Instalando Obsidian")"
    log "$(t \
      "Obsidian is the note-taking app this whole setup writes into. Free, runs locally, no account." \
      "Obsidian es la app de notas en la que todo este setup escribe. Gratis, corre local, sin cuenta.")"
    log "$(t \
      "Installing via Homebrew so you don't have to download anything yourself." \
      "Instalando vía Homebrew para que no tengas que descargar nada manual.")"
    brew install --cask obsidian \
      || err "$(t \
        "Obsidian install failed — install manually from https://obsidian.md and re-run this script" \
        "Falló la instalación de Obsidian — instalalo manual desde https://obsidian.md y volvé a correr este script")"
  fi
  if [[ -d "/Applications/Obsidian.app" ]]; then
    ok "$(t "Obsidian installed at /Applications/Obsidian.app" \
            "Obsidian instalado en /Applications/Obsidian.app")"
  fi
else
  # Linux — try snap, then flatpak, then AppImage download. Never ask the user to
  # download anything themselves. Order matters: snap is more common on Ubuntu,
  # flatpak on Fedora/Arch, AppImage works literally everywhere as last resort.
  obsidian_installed() {
    have obsidian \
      || [[ -f "/var/lib/flatpak/exports/bin/md.obsidian.Obsidian" ]] \
      || [[ -f "$HOME/.local/share/flatpak/exports/bin/md.obsidian.Obsidian" ]] \
      || [[ -x "$HOME/.local/bin/obsidian" ]]
  }
  if ! obsidian_installed; then
    hdr "Installing Obsidian"
    log "Obsidian is the note-taking app this whole setup writes into. Free, runs locally, no account."

    if have snap; then
      log "Installing via snap."
      sudo snap install obsidian --classic 2>/dev/null || warn "snap install failed — trying flatpak"
    fi
    if ! obsidian_installed && have flatpak; then
      log "Installing via flatpak."
      flatpak install -y flathub md.obsidian.Obsidian 2>/dev/null || warn "flatpak install failed — trying AppImage"
    fi
    if ! obsidian_installed; then
      log "Falling back to AppImage download (works on any Linux distro)."
      mkdir -p "$HOME/.local/bin"
      # Resolve the latest AppImage URL from the official GitHub releases API
      APPIMAGE_URL="$(curl -fsSL https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest 2>/dev/null \
        | grep -oE 'https://github.com/obsidianmd/obsidian-releases/releases/download/[^"]+\.AppImage' \
        | head -1)"
      if [[ -n "$APPIMAGE_URL" ]]; then
        if curl -fsSL -o "$HOME/.local/bin/obsidian" "$APPIMAGE_URL" 2>/dev/null; then
          chmod +x "$HOME/.local/bin/obsidian"
          log "AppImage installed at ~/.local/bin/obsidian"
          log "Run it with: obsidian (make sure ~/.local/bin is on your PATH)"
        else
          err "AppImage download failed. Manual fallback: go to https://obsidian.md/download, download the AppImage, chmod +x it, place it in ~/.local/bin/obsidian, and re-run this script."
        fi
      else
        err "Could not resolve the latest Obsidian AppImage URL. Manual fallback: go to https://obsidian.md/download, download the AppImage, chmod +x it, place it in ~/.local/bin/obsidian, and re-run this script."
      fi
    fi
  fi
  obsidian_installed && ok "Obsidian installed"
fi

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
# FastMCP — framework for building custom MCP servers in minimal Python.
# Needed when wiring CRM bridges, vault sync, investor relations, or any
# project-specific MCP the user (or their team) builds on top of this stack.
# ───────────────────────────────────────────────────────────────────────────────

if ! have fastmcp; then
  hdr "Installing fastmcp"
  log "fastmcp lets you build custom MCP servers in a few lines of Python."
  pipx install fastmcp >/dev/null 2>&1 || warn "fastmcp install failed (non-blocking — install later with: pipx install fastmcp)"
fi
have fastmcp && ok "fastmcp $(fastmcp --version 2>/dev/null | head -1 || echo installed)"

# ───────────────────────────────────────────────────────────────────────────────
# Clone or update the ai-brain-starter skill
# SAFETY:
#   - Stashes local uncommitted changes before pulling
#   - Detects DIVERGENT history (your fork has commits not on origin/main)
#     and refuses to pull, so your fork is never silently overwritten
# ───────────────────────────────────────────────────────────────────────────────

hdr "Installing the ai-brain-starter skill"
mkdir -p "$HOME/.claude/skills"
if [[ -d "$SKILL_DIR/.git" ]]; then
  log "Already installed — checking for updates..."
  cd "$SKILL_DIR"

  # Fetch first so we know the divergence state
  if [[ $DRY_RUN -eq 1 ]]; then
    dry "would: git fetch --quiet origin"
  else
    git fetch --quiet origin 2>/dev/null || warn "git fetch failed — skipping update check"
  fi

  # Detect divergent history: count commits ahead and behind
  AHEAD=$(git rev-list --count "@{u}..HEAD" 2>/dev/null || echo 0)
  BEHIND=$(git rev-list --count "HEAD..@{u}" 2>/dev/null || echo 0)

  if [[ "$AHEAD" -gt 0 && "$BEHIND" -gt 0 ]]; then
    # Divergent fork — refuse to pull
    warn "DIVERGENT FORK DETECTED at $SKILL_DIR"
    warn "  Your local clone has $AHEAD commit(s) NOT on origin/main"
    warn "  AND origin/main has $BEHIND commit(s) NOT on your clone"
    warn "  Refusing to pull. Your fork is preserved unchanged."
    warn "  To merge manually: cd $SKILL_DIR && git pull --rebase (or your preferred merge strategy)"
    SKIPPED+=("ai-brain-starter clone (divergent fork — manual merge required)")
  elif [[ "$AHEAD" -gt 0 && "$BEHIND" -eq 0 ]]; then
    # Local-only commits, no upstream changes — leave alone
    log "Your clone has $AHEAD local commit(s) and is otherwise current. Leaving as-is."
    SKIPPED+=("ai-brain-starter clone (local commits, up to date)")
  elif [[ "$BEHIND" -gt 0 ]]; then
    # Behind upstream — safe to pull. Check for uncommitted changes first.
    if ! git diff --quiet --ignore-submodules HEAD 2>/dev/null; then
      STASH_MSG="bootstrap auto-stash $(date +%Y-%m-%d-%H%M)"
      log "Detected local uncommitted changes — stashing as: $STASH_MSG"
      log "Recover later with: cd $SKILL_DIR && git stash list && git stash pop"
      do_cmd "git stash push -u -m '$STASH_MSG'" git stash push -u -m "$STASH_MSG" >/dev/null 2>&1 || warn "stash failed"
    fi
    do_cmd "git pull --quiet (fast-forward $BEHIND commit(s))" git pull --quiet 2>/dev/null || warn "git pull failed"
    UPDATED+=("ai-brain-starter clone (pulled $BEHIND commit(s))")
  else
    log "ai-brain-starter clone is up to date"
  fi

  cd - >/dev/null
else
  do_cmd "clone ai-brain-starter to $SKILL_DIR" git clone --quiet "$REPO_URL" "$SKILL_DIR" || err "ai-brain-starter clone failed"
  INSTALLED+=("ai-brain-starter clone")
fi
[[ -f "$SKILL_DIR/SKILL.md" || $DRY_RUN -eq 1 ]] && ok "ai-brain-starter skill at $SKILL_DIR"

# ───────────────────────────────────────────────────────────────────────────────
# Install bundled sub-skills (with comprehensive safety checks)
# SAFETY:
#   - If the destination is a SYMLINK, warn before writing through
#   - If the destination has its own .git directory, treat it as a FORK and
#     skip entirely (the user manages updates themselves)
#   - Otherwise: sync via sync-skills.sh which implements backup-before-overwrite
#   - Custom skill folders outside the bundled set are NEVER touched
# ───────────────────────────────────────────────────────────────────────────────

hdr "Installing bundled sub-skills (with safety checks)"

SKILL_FORKS=()
SKILL_SYMLINKS=()
SKILLS_TO_SYNC=()

for sub in graphify meeting-todos patterns insights deconstruct daily-journal repurpose-talk nano-banana; do
  dst="$HOME/.claude/skills/$sub"

  if [[ -L "$dst" ]]; then
    # Symlink — warn before writing through
    target="$(readlink "$dst")"
    SKILL_SYMLINKS+=("$sub → $target")
    warn "$sub is a SYMLINK to $target — bootstrap will NOT write through it"
    warn "  If you want bootstrap to update this skill, replace the symlink with a regular folder."
    SKIPPED+=("$sub skill (symlink to $target)")
  elif [[ -d "$dst/.git" ]]; then
    # User's own fork (their own .git inside the skill folder) — skip entirely
    SKILL_FORKS+=("$sub")
    log "$sub has its own .git/ directory — detected as YOUR FORK, skipping entirely"
    log "  Your fork is preserved untouched. You manage updates to it yourself."
    SKIPPED+=("$sub skill (your own fork — has .git)")
  elif [[ -d "$dst" || ! -e "$dst" ]]; then
    # Regular folder (or missing) — eligible for sync
    SKILLS_TO_SYNC+=("$sub")
  else
    err "$sub destination $dst exists but is not a folder, symlink, or missing — skipping"
    SKIPPED+=("$sub skill (unexpected destination type)")
  fi
done

if [[ ${#SKILLS_TO_SYNC[@]} -gt 0 ]]; then
  if [[ -x "$SKILL_DIR/scripts/sync-skills.sh" ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then
      dry "would run sync-skills.sh for: ${SKILLS_TO_SYNC[*]}"
      dry "  any installed file that differs from the repo version would be backed up first"
    else
      # sync-skills.sh syncs ALL bundled skills; we need it to skip the ones
      # we identified as forks/symlinks. The simplest way: run it, then for
      # each fork/symlink we already protected by NOT including it in
      # SKILLS_TO_SYNC. But sync-skills.sh doesn't know about our list — it
      # syncs all skills it finds in the repo. We need to either patch the
      # script to accept a skip list, OR just sync each safe skill manually.
      # Going with manual per-skill sync for explicitness.
      for sub in "${SKILLS_TO_SYNC[@]}"; do
        src="$SKILL_DIR/skills/$sub"
        dst="$HOME/.claude/skills/$sub"
        if [[ ! -d "$src" ]]; then
          err "$sub skill source missing in repo"
          continue
        fi
        mkdir -p "$dst"
        # File-by-file sync with backup-before-overwrite (mirrors sync-skills.sh logic)
        STAMP="$(date +%Y-%m-%d-%H%M)"
        BACKED_UP_THIS_SUB=0
        UPDATED_THIS_SUB=0
        CREATED_THIS_SUB=0
        while IFS= read -r srcfile; do
          rel="${srcfile#$src/}"
          dstfile="$dst/$rel"
          mkdir -p "$(dirname "$dstfile")"
          if [[ -f "$dstfile" ]]; then
            if ! cmp -s "$srcfile" "$dstfile"; then
              cp "$dstfile" "$dstfile.bak-$STAMP"
              BACKUPS+=("$dstfile.bak-$STAMP")
              cp "$srcfile" "$dstfile"
              BACKED_UP_THIS_SUB=$((BACKED_UP_THIS_SUB + 1))
              UPDATED_THIS_SUB=$((UPDATED_THIS_SUB + 1))
            fi
          else
            cp "$srcfile" "$dstfile"
            CREATED_THIS_SUB=$((CREATED_THIS_SUB + 1))
          fi
        done < <(find "$src" -type f)
        if [[ $BACKED_UP_THIS_SUB -gt 0 || $UPDATED_THIS_SUB -gt 0 || $CREATED_THIS_SUB -gt 0 ]]; then
          ok "$sub: $CREATED_THIS_SUB new, $UPDATED_THIS_SUB updated, $BACKED_UP_THIS_SUB backed up"
          UPDATED+=("$sub skill ($CREATED_THIS_SUB new, $UPDATED_THIS_SUB updated, $BACKED_UP_THIS_SUB backed up)")
        else
          ok "$sub: already current"
        fi
      done
    fi
  else
    warn "sync-skills.sh not found — using direct copy (no backups)"
    for sub in "${SKILLS_TO_SYNC[@]}"; do
      src="$SKILL_DIR/skills/$sub"
      dst="$HOME/.claude/skills/$sub"
      [[ -d "$src" ]] && do_cmd "cp -R $src → $dst" mkdir -p "$dst" && do_cmd "" cp -R "$src/." "$dst/"
    done
  fi
fi

# Summary of what was protected this section
[[ ${#SKILL_FORKS[@]} -gt 0 ]] && log "Forks preserved untouched: ${SKILL_FORKS[*]}"
[[ ${#SKILL_SYMLINKS[@]} -gt 0 ]] && log "Symlinks preserved untouched: ${#SKILL_SYMLINKS[@]} skill(s)"

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
# Granola MCP (meeting workflow rule depends on this)
# ───────────────────────────────────────────────────────────────────────────────

hdr "Registering MCPs (Granola + ChatPRD)"
# SAFETY: backup .mcp.json before editing. Existing MCP servers
# (custom integrations, other URL or stdio MCPs the user wired themselves)
# are preserved — setdefault() only adds entries that are missing.
backup_file "$HOME/.claude/.mcp.json"
if [[ $DRY_RUN -eq 1 ]]; then
  dry "would register granola + chatprd MCPs in ~/.claude/.mcp.json (existing entries preserved)"
else
  python3 - <<'PY' || err "MCP registration failed"
import json, os
p = os.path.expanduser("~/.claude/.mcp.json")
try:
    with open(p) as f: m = json.load(f)
except FileNotFoundError:
    m = {"mcpServers": {}}
m.setdefault("mcpServers", {})
added = []
if "granola" not in m["mcpServers"]:
    m["mcpServers"]["granola"] = {"type": "url", "url": "https://mcp.granola.ai/mcp"}
    added.append("granola")
if "chatprd" not in m["mcpServers"]:
    m["mcpServers"]["chatprd"] = {"type": "url", "url": "https://app.chatprd.ai/mcp"}
    added.append("chatprd")
with open(p, "w") as f: json.dump(m, f, indent=2)
print("added:", ", ".join(added) if added else "nothing new (already registered)")
PY
  ok "MCPs registered: granola, chatprd — .mcp.json backed up (existing entries preserved)"
fi

# ───────────────────────────────────────────────────────────────────────────────
# Marketplaces + enabled plugins (settings.json)
# SAFETY: backup settings.json first. setdefault() never clobbers existing
# marketplaces, plugins, permissions, env vars, or any other keys.
# ───────────────────────────────────────────────────────────────────────────────

hdr "Registering marketplace + enabling plugins"
backup_file "$HOME/.claude/settings.json"
if [[ $DRY_RUN -eq 1 ]]; then
  dry "would register obsidian-skills marketplace (kepano/obsidian-skills) and enable: obsidian, context7, playwright"
else
  python3 - <<'PY' || err "settings.json plugin registration failed"
import json, os
p = os.path.expanduser("~/.claude/settings.json")
try:
    with open(p) as f: s = json.load(f)
except FileNotFoundError:
    s = {}
s.setdefault("extraKnownMarketplaces", {})
if "obsidian-skills" not in s["extraKnownMarketplaces"]:
    s["extraKnownMarketplaces"]["obsidian-skills"] = {
        "source": {"source": "github", "repo": "kepano/obsidian-skills"}
    }
s.setdefault("enabledPlugins", {})
for plug in ("obsidian@obsidian-skills", "context7", "playwright"):
    s["enabledPlugins"].setdefault(plug, True)
with open(p, "w") as f: json.dump(s, f, indent=2)
PY
  ok "Marketplace + plugins registered (settings.json backed up)"
fi

# ───────────────────────────────────────────────────────────────────────────────
# Obsidian CLI symlink (Mac only, Obsidian 1.12.7+)
# The Obsidian desktop app ships a CLI binary. Linking it into /usr/local/bin
# makes `obsidian search`, `obsidian backlinks` etc. callable from anywhere —
# used by the graphify and meeting skills for fast vault queries.
# Requires sudo for /usr/local/bin; we skip cleanly if the user declines.
# ───────────────────────────────────────────────────────────────────────────────

if is_mac; then
  OBS_CLI="/Applications/Obsidian.app/Contents/MacOS/obsidian-cli"
  LINK="/usr/local/bin/obsidian"
  if [[ -f "$OBS_CLI" ]] && [[ ! -e "$LINK" || "$(readlink "$LINK" 2>/dev/null)" != "$OBS_CLI" ]]; then
    hdr "Linking Obsidian CLI"
    log "Makes 'obsidian search/backlinks/...' callable from any terminal."
    log "Requires your Mac password (for the /usr/local/bin symlink)."
    if [[ $DRY_RUN -eq 1 ]]; then
      dry "would: sudo ln -sf $OBS_CLI $LINK"
    else
      sudo ln -sf "$OBS_CLI" "$LINK" 2>/dev/null \
        && ok "obsidian CLI linked at $LINK" \
        || warn "obsidian CLI link skipped (not blocking — vault works fine without it)"
    fi
  elif [[ -L "$LINK" ]]; then
    ok "obsidian CLI already linked"
  fi
fi

# ───────────────────────────────────────────────────────────────────────────────
# Verification — NEVER FAIL SILENTLY
# ───────────────────────────────────────────────────────────────────────────────

hdr "Verifying installation"

if [[ $DRY_RUN -eq 1 ]]; then
  log "skipping verification under --dry-run (nothing was actually installed)"
  # Jump past the verification block via a flag; the change-summary still runs.
  SKIP_VERIFY=1
else
  SKIP_VERIFY=0
fi

if [[ $SKIP_VERIFY -eq 0 ]]; then
CHECKS=(
  "graphify CLI:graphify"
  "node:node"
  "npm:npm"
  "pipx:pipx"
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
# Skill folders (full bundled set + humanizer + ai-brain-starter itself)
for sub in graphify meeting-todos patterns insights deconstruct daily-journal repurpose-talk nano-banana humanizer ai-brain-starter diagnose; do
  if [[ -d "$HOME/.claude/skills/$sub" ]]; then
    ok "skill: $sub"
  else
    err "skill missing: $sub"
  fi
done

# graphify scripts present (the 80%-cost-cut wrappers)
[[ -d "$HOME/.claude/skills/graphify/scripts" ]] && ok "graphify scripts" || err "graphify scripts missing"

# MCP entries
grep -q "granola" "$HOME/.claude/.mcp.json" 2>/dev/null \
  && ok "granola MCP in .mcp.json" \
  || err "granola not in .mcp.json"
grep -q "chatprd" "$HOME/.claude/.mcp.json" 2>/dev/null \
  && ok "chatprd MCP in .mcp.json" \
  || err "chatprd not in .mcp.json"

# Marketplace + plugins
grep -q "obsidian-skills" "$HOME/.claude/settings.json" 2>/dev/null \
  && ok "obsidian-skills marketplace in settings.json" \
  || warn "obsidian-skills marketplace not in settings.json (non-blocking)"
fi  # end: if [[ $SKIP_VERIFY -eq 0 ]]

echo
if [[ ${#FAILED[@]} -eq 0 ]]; then
  printf "\033[32m━━━ %s ━━━\033[0m\n\n" \
    "$(t "All checks passed." "Todas las verificaciones pasaron.")"
else
  printf "\033[31m━━━ %d %s ━━━\033[0m\n" "${#FAILED[@]}" \
    "$(t "check(s) failed:" "verificación(es) fallaron:")"
  for f in "${FAILED[@]}"; do printf "  • %s\n" "$f"; done
  echo
  echo "$(t \
    "Don't proceed silently. Fix these before continuing the setup interview." \
    "No sigas en silencio. Arreglá esto antes de continuar con la entrevista de setup.")"
  echo "$(t \
    "Re-running this script is safe and skips anything already installed." \
    "Volver a correr este script es seguro y saltea lo que ya está instalado.")"
fi

# ───────────────────────────────────────────────────────────────────────────────
# Change summary — every action this run took (or would take in dry-run mode)
# ───────────────────────────────────────────────────────────────────────────────

hdr "Change summary"
if [[ $DRY_RUN -eq 1 ]]; then
  printf "\033[35mDRY RUN — no actual changes made.\033[0m\n"
fi

if [[ ${#INSTALLED[@]} -eq 0 && ${#UPDATED[@]} -eq 0 && ${#SKIPPED[@]} -eq 0 && ${#BACKUPS[@]} -eq 0 && ${#CLEANED[@]} -eq 0 ]]; then
  echo "  Nothing to report — your setup was already current."
else
  if [[ ${#INSTALLED[@]} -gt 0 ]]; then
    printf "\n  \033[32mInstalled (new):\033[0m\n"
    for x in "${INSTALLED[@]}"; do printf "    + %s\n" "$x"; done
  fi
  if [[ ${#UPDATED[@]} -gt 0 ]]; then
    printf "\n  \033[36mUpdated:\033[0m\n"
    for x in "${UPDATED[@]}"; do printf "    ↑ %s\n" "$x"; done
  fi
  if [[ ${#SKIPPED[@]} -gt 0 ]]; then
    printf "\n  \033[33mSkipped (your customizations preserved):\033[0m\n"
    for x in "${SKIPPED[@]}"; do printf "    ⊘ %s\n" "$x"; done
  fi
  if [[ ${#BACKUPS[@]} -gt 0 ]]; then
    printf "\n  \033[33mBackups created (recoverable):\033[0m\n"
    for x in "${BACKUPS[@]}"; do printf "    ↳ %s\n" "$x"; done
    echo
    printf "  To restore any backup: \033[1mmv <file>.bak-YYYY-MM-DD-HHMM <file>\033[0m\n"
  fi
  if [[ ${#CLEANED[@]} -gt 0 ]]; then
    printf "\n  \033[31mRemoved (deprecated):\033[0m\n"
    for x in "${CLEANED[@]}"; do printf "    ✕ %s\n" "$x"; done
  fi
fi
echo

# ───────────────────────────────────────────────────────────────────────────────
# User-level hook install (closes #6 — fires universally inside worktrees)
# ───────────────────────────────────────────────────────────────────────────────

USER_HOOK_INSTALLER="$SKILL_DIR/scripts/install-hooks-user-level.py"
if [[ -f "$USER_HOOK_INSTALLER" ]] && [[ "$DRY_RUN" -eq 0 ]]; then
  hdr "Installing hooks at user level (so they fire inside worktrees)"
  if python3 "$USER_HOOK_INSTALLER" --quiet 2>&1 | tee -a "$BOOTSTRAP_LOG"; then
    ok "User-level hooks installed (~/.claude/settings.json)"
  else
    warn "User-level hook install had issues; check $BOOTSTRAP_LOG"
  fi
fi

# ───────────────────────────────────────────────────────────────────────────────
# Report install completion to Mycelium (best-effort, fail-open)
# ───────────────────────────────────────────────────────────────────────────────

if [[ -f "$EMAIL_MARKER" && $DRY_RUN -eq 0 ]]; then
  RECORDED_TOKEN="$(head -1 "$EMAIL_MARKER" 2>/dev/null | tr -d '[:space:]')"
  if [[ -n "$RECORDED_TOKEN" ]]; then
    OS_INFO="$(uname -srm 2>/dev/null || echo unknown)"
    set +e
    curl -sS -m 8 -X POST "$INSTALL_API_BASE/api/install/complete" \
      -H "content-type: application/json" \
      -d "{\"token\":\"$RECORDED_TOKEN\",\"os\":\"$OS_INFO\",\"completed\":true}" \
      >/dev/null 2>&1 || true
    set -e
  fi
fi

# ───────────────────────────────────────────────────────────────────────────────
# Next steps
# ───────────────────────────────────────────────────────────────────────────────

if [[ -n "${CLAUDE_CODE_ENTRYPOINT:-}" ]]; then
  # Running inside Claude Code (paste-flow from README). Claude will continue
  # with the setup interview automatically; no user action needed.
  if [[ "$LANG_CODE" == "es" ]]; then
    cat <<'EOF'

━━━ Instalación completa ━━━

  Las herramientas están listas. Claude continúa con la entrevista de setup
  automáticamente desde acá. Sin comandos que tipear, sin carpetas que abrir,
  sin terminal que tocar.

  ⌘↩ vs tipear: cuando veas un cuadro gris de aprobación de herramienta,
  presioná ⌘↩ (Mac) o Ctrl+Enter (Windows). Cuando Claude te haga una pregunta,
  solo tipeá tu respuesta y presioná Enter.

  Cuando tu vault personal esté corriendo, podés pedirle a Claude cualquiera
  de estas para conectar la versión de equipo:

       "¿Cómo agrego a mi equipo sin mezclar mis cosas personales?"
       "Optimizá esto para mi empresa."
       "¿Cómo se ve la versión de equipo?"

  Generación de imágenes (Nano Banana, vía Gemini) es lo único que no se
  puede auto-instalar acá. Necesita comandos /plugin dentro de Claude Code
  y una API key de Gemini en https://ai.google.dev/. Pedile a Claude que la
  prenda cuando quieras generar imágenes; no la necesitás para el setup base.

EOF
  else
    cat <<'EOF'

━━━ Install complete ━━━

  Tools are ready. Claude continues with the setup interview automatically
  from here. No commands to type, no folders to open, no terminal to touch.

  ⌘↩ vs typing: when you see a gray tool-approval box, press ⌘↩ (Mac) or
  Ctrl+Enter (Windows). When Claude asks you a question, just type your
  answer and press Enter.

  When your personal vault is running, you can ask Claude any of these to
  wire up the team version:

       "How do I add my team to this without mixing in my personal stuff?"
       "Optimize this for my company."
       "What does the team version look like?"

  Image generation (Nano Banana, via Gemini) is the one thing that can't
  auto-install here. It needs /plugin commands inside Claude Code and a
  Gemini API key from https://ai.google.dev/. Ask Claude to turn it on when
  you actually want image generation; you don't need it for the core setup.

EOF
  fi
else
  # Running standalone (curl-to-bash from a plain terminal). The user has no
  # active Claude session to continue into; guide them to the paste-flow.
  if [[ "$LANG_CODE" == "es" ]]; then
    cat <<'EOF'

━━━ Instalación completa ━━━

  Las herramientas están listas. Ahora abrí la app de escritorio de Claude
  Code y pegá esto en el chat para correr la entrevista de setup:

      Por favor configurá mi AI Brain Starter completo en esta sesión.
      La skill ai-brain-starter ya está instalada en
      ~/.claude/skills/ai-brain-starter. Empezá la entrevista de setup
      corriendo la skill setup-brain y guiame por cada fase sin parar.

  Claude te va a preguntar dónde vivirá tu vault y va a construir todo
  alrededor de tus respuestas. No necesitás tipear ningún otro comando.

EOF
  else
    cat <<'EOF'

━━━ Install complete ━━━

  Tools are ready. Now open the Claude Code desktop app and paste this
  into the chat to run the setup interview:

      Please set up my AI Brain Starter end-to-end in this session. The
      ai-brain-starter skill is already installed at
      ~/.claude/skills/ai-brain-starter. Start the setup interview by
      running the setup-brain skill and walk me through every phase
      without stopping.

  Claude will ask where your vault should live and build everything
  around your answers. You don't need to type any other commands.

EOF
  fi
fi
