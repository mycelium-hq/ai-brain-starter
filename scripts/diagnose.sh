#!/usr/bin/env bash
# diagnose.sh - Self-check for an installed AI Brain Starter vault.
# Runs ~10 checks and prints a green/yellow/red report.
#
# Usage:
#   bash diagnose.sh              # auto-detect vault from $VAULT_PATH or cwd
#   bash diagnose.sh /path/vault  # check a specific vault
#
# Exit codes:
#   0 = all green
#   1 = at least one red (something is broken)
#   2 = only yellows (warnings, not broken)
#
# Designed to be safe to run any time. No writes, no network.

set -u

# ----- color helpers (no-op if not a tty) -----
if [ -t 1 ]; then
  G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; B=$'\033[1m'; N=$'\033[0m'
else
  G=''; Y=''; R=''; B=''; N=''
fi

GREEN=0; YELLOW=0; RED=0

ok()   { echo "  ${G}OK${N}    $1"; GREEN=$((GREEN+1)); }
warn() { echo "  ${Y}WARN${N}  $1"; [ -n "${2:-}" ] && echo "        -> $2"; YELLOW=$((YELLOW+1)); }
bad()  { echo "  ${R}FAIL${N}  $1"; [ -n "${2:-}" ] && echo "        -> $2"; RED=$((RED+1)); }

section() { echo; echo "${B}$1${N}"; }

# ----- locate vault -----
VAULT="${1:-${VAULT_PATH:-$PWD}}"
if [ ! -d "$VAULT" ]; then
  echo "${R}Vault path not a directory:${N} $VAULT"
  echo "Pass the vault path: bash diagnose.sh /path/to/vault"
  exit 1
fi
VAULT="$(cd "$VAULT" && pwd)"

echo "${B}AI Brain Starter diagnostics${N}"
echo "Vault: $VAULT"

# ----- 1. CLAUDE.md exists -----
section "1. Vault memory (CLAUDE.md)"
if [ -f "$VAULT/CLAUDE.md" ]; then
  size=$(wc -c < "$VAULT/CLAUDE.md" | tr -d ' ')
  if [ "$size" -lt 200 ]; then
    warn "CLAUDE.md exists but is tiny ($size bytes)" "Re-run /setup-brain Phase 4 to rebuild it."
  else
    ok "CLAUDE.md present ($size bytes)"
  fi
  if grep -q "## Vault Map" "$VAULT/CLAUDE.md"; then
    ok "Vault Map section present"
  else
    warn "No '## Vault Map' section in CLAUDE.md" "Claude will create duplicate folders without it."
  fi
else
  bad "CLAUDE.md missing" "Run /setup-brain Phase 4."
fi

# ----- 2. Meta folder structure -----
section "2. Meta folder"
META="$VAULT/⚙️ Meta"
if [ -d "$META" ]; then
  ok "⚙️ Meta/ folder present"
  for sub in scripts rules; do
    if [ -d "$META/$sub" ]; then
      ok "⚙️ Meta/$sub/ present"
    else
      warn "⚙️ Meta/$sub/ missing"
    fi
  done
else
  bad "⚙️ Meta/ folder missing" "Run /setup-brain Phase 3."
fi

# ----- 3. Skills installed -----
section "3. Claude Code skills"
SKILLS_DIR="$HOME/.claude/skills"
if [ -d "$SKILLS_DIR" ]; then
  # shellcheck disable=SC2088  # literal ~ in user-facing message, not a path
  ok "~/.claude/skills/ exists"
  # ai-brain-starter itself
  if [ -d "$SKILLS_DIR/ai-brain-starter" ]; then
    ok "ai-brain-starter skill installed"
  else
    warn "ai-brain-starter skill not in ~/.claude/skills/" "Re-run bootstrap to symlink it."
  fi
  # daily-journal is the most-used downstream skill
  if [ -d "$SKILLS_DIR/daily-journal" ] || [ -f "$SKILLS_DIR/daily-journal/SKILL.md" ]; then
    ok "daily-journal skill installed"
  else
    warn "daily-journal skill not installed" "/setup-brain Phase 10a creates it."
  fi
else
  # shellcheck disable=SC2088  # literal ~ in user-facing message, not a path
  bad "~/.claude/skills/ missing" "Claude Code may not be installed, or the skills dir was deleted."
fi

# ----- 4. Hooks registered -----
section "4. Claude Code hooks"
SETTINGS="$HOME/.claude/settings.json"
LOCAL_SETTINGS="$VAULT/.claude/settings.local.json"
hook_found=0
for f in "$SETTINGS" "$LOCAL_SETTINGS"; do
  if [ -f "$f" ] && grep -q '"hooks"' "$f" 2>/dev/null; then
    hook_found=1
    ok "hooks registered in $f"
  fi
done
if [ "$hook_found" -eq 0 ]; then
  warn "No hooks registered in settings.json or .claude/settings.local.json" \
    "/setup-brain Phase 5 wires them. Without them, no auto context-loading."
fi

# graph-context-hook script (the one that bit Windows users)
GCH="$META/scripts/graph-context-hook.sh"
if [ -f "$GCH" ]; then
  ok "graph-context-hook.sh present"
  if bash -n "$GCH" 2>/dev/null; then
    ok "graph-context-hook.sh parses cleanly"
  else
    bad "graph-context-hook.sh has bash syntax errors" "Run: bash -n '$GCH'"
  fi
else
  warn "graph-context-hook.sh not in ⚙️ Meta/scripts/" "Phase 5 installs it."
fi

# ----- 5. Journal index -----
section "5. Insights pipeline"
INDEX="$META/journal-index.json"
if [ -f "$INDEX" ]; then
  if [ "$(uname)" = "Darwin" ]; then
    age_days=$(( ( $(date +%s) - $(stat -f %m "$INDEX") ) / 86400 ))
  else
    age_days=$(( ( $(date +%s) - $(stat -c %Y "$INDEX") ) / 86400 ))
  fi
  if [ "$age_days" -gt 14 ]; then
    warn "journal-index.json is $age_days days old" "Re-run build-journal-index.py or /weekly to refresh."
  else
    ok "journal-index.json is fresh ($age_days days old)"
  fi
  # quick JSON validity check
  if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$INDEX" 2>/dev/null; then
    ok "journal-index.json is valid JSON"
  else
    bad "journal-index.json is malformed" "Delete it and re-run build-journal-index.py."
  fi
else
  warn "No journal-index.json yet" "/weekly or /monthly will build it on first run."
fi

# ----- 6. Required CLI tools -----
section "6. Required CLI tools"
for tool in git python3 jq; do
  if command -v "$tool" >/dev/null 2>&1; then
    ok "$tool installed"
  else
    if [ "$tool" = "jq" ]; then
      warn "$tool missing" "Optional, but some scripts prefer it. brew install jq"
    else
      bad "$tool missing" "Required. brew install $tool"
    fi
  fi
done

# ----- 7. Git in vault -----
section "7. Vault git status"
if [ -d "$VAULT/.git" ]; then
  ok "Vault is a git repo (snapshot history available)"
  remote=$(cd "$VAULT" && git remote -v 2>/dev/null | head -1)
  if [ -n "$remote" ]; then
    warn "Vault has a git remote: $remote" \
      "Vaults are usually local-only. Make sure you actually want this."
  else
    ok "No git remote (correct for a private vault)"
  fi
else
  warn "Vault is not a git repo" "You won't have rollback history. Optional but recommended."
fi

# ----- 8. .ps1 sanity (if any exist) -----
section "8. PowerShell files (Windows compat)"
ps1_files=$(find "$VAULT" "$HOME/.claude/skills/ai-brain-starter" \
  -name '*.ps1' -not -path '*/.git/*' 2>/dev/null | head -20)
if [ -z "$ps1_files" ]; then
  ok "No .ps1 files to check"
else
  bom_fail=0; emdash_fail=0
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    head_bytes=$(head -c 3 "$f" 2>/dev/null | od -An -tx1 | tr -d ' \n')
    [ "$head_bytes" != "efbbbf" ] && bom_fail=$((bom_fail+1))
    grep -l $'\xe2\x80\x94' "$f" >/dev/null 2>&1 && emdash_fail=$((emdash_fail+1))
  done <<< "$ps1_files"
  if [ "$bom_fail" -eq 0 ]; then
    ok "All .ps1 files have UTF-8 BOM"
  else
    warn "$bom_fail .ps1 file(s) missing UTF-8 BOM" "Windows PowerShell 5.1 will crash on non-ASCII bytes."
  fi
  if [ "$emdash_fail" -eq 0 ]; then
    ok "No em dashes in .ps1 files"
  else
    warn "$emdash_fail .ps1 file(s) contain em dashes" "Replace with ASCII hyphens (defense-in-depth)."
  fi
fi

# ----- 9. MCP config -----
section "9. MCP servers"
MCP_LOCAL="$VAULT/.mcp.json"
MCP_GLOBAL="$HOME/.claude.json"
mcp_found=0
for f in "$MCP_LOCAL" "$MCP_GLOBAL"; do
  if [ -f "$f" ] && grep -q '"mcpServers"' "$f" 2>/dev/null; then
    mcp_found=1
    if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null; then
      ok "MCP config valid: $f"
    else
      bad "MCP config malformed: $f" "Invalid JSON. Fix the file."
    fi
  fi
done
[ "$mcp_found" -eq 0 ] && warn "No MCP config found" "MCPs are optional. Skip if you don't use them."

# ----- 10b. Scheduled-task naming hygiene -----
section "10b. Scheduled-task naming hygiene"
SCHED_DIR="$HOME/.claude/scheduled-tasks"
if [ -d "$SCHED_DIR" ]; then
  collide_count=0
  noprefix_count=0
  collide_names=""
  noprefix_names=""
  for entry in "$SCHED_DIR"/*; do
    [ -d "$entry" ] || continue
    [ -f "$entry/SKILL.md" ] || continue
    name=$(basename "$entry")
    # Collision: scheduled-task name matches an installed skill name.
    if [ -d "$HOME/.claude/skills/$name" ] || [ -f "$HOME/.claude/skills/$name/SKILL.md" ]; then
      collide_count=$((collide_count+1))
      collide_names="$collide_names $name"
    fi
    # Convention: cron-only tasks should prefix with _ so autocomplete
    # surfaces them at the bottom and reads them as cron-only.
    case "$name" in
      _*) ;;
      *) noprefix_count=$((noprefix_count+1)); noprefix_names="$noprefix_names $name";;
    esac
  done
  if [ "$collide_count" -eq 0 ] && [ "$noprefix_count" -eq 0 ]; then
    ok "Scheduled-task names are clean (no skill collisions, all underscore-prefixed)"
  else
    if [ "$collide_count" -gt 0 ]; then
      warn "$collide_count scheduled-task name(s) collide with installed skills:$collide_names" \
        "Rename: e.g. 'daily-journal' -> '_daily-journal-cron'. See docs/MAINTENANCE.md."
    fi
    if [ "$noprefix_count" -gt 0 ]; then
      warn "$noprefix_count scheduled-task name(s) lack '_' prefix:$noprefix_names" \
        "Cron-only tasks should start with _ to read as cron-only in autocomplete. See docs/MAINTENANCE.md."
    fi
  fi
else
  ok "No ~/.claude/scheduled-tasks/ directory (skipped)"
fi

# ----- 10. SessionStart freshness check -----
section "10. ai-brain-starter freshness"
ABS_DIR="$HOME/.claude/skills/ai-brain-starter"
if [ -d "$ABS_DIR/.git" ]; then
  cd "$ABS_DIR" || exit 1
  local_sha=$(git rev-parse HEAD 2>/dev/null | cut -c1-7)
  if git fetch origin main --quiet 2>/dev/null; then
    remote_sha=$(git rev-parse origin/main 2>/dev/null | cut -c1-7)
    if [ "$local_sha" = "$remote_sha" ]; then
      ok "ai-brain-starter is up to date ($local_sha)"
    else
      behind=$(git rev-list --count "$local_sha..$remote_sha" 2>/dev/null)
      warn "ai-brain-starter is $behind commit(s) behind origin/main" \
        "cd ~/.claude/skills/ai-brain-starter && git pull"
    fi
  else
    warn "Could not fetch from origin (offline?)"
  fi
  cd - >/dev/null || exit 1
else
  # shellcheck disable=SC2088  # literal ~ in user-facing message, not a path
  warn "~/.claude/skills/ai-brain-starter is not a git repo" "Re-run bootstrap.sh to clone it."
fi

# ----- 11. cloud-sync location (the freeze class) -----
section "11. Cloud-sync location"
CHECK_CLOUD=""
for c in "$(cd "$(dirname "$0")" && pwd)/check-cloud-sync.py" \
         "$HOME/.claude/skills/ai-brain-starter/scripts/check-cloud-sync.py"; do
  [ -f "$c" ] && CHECK_CLOUD="$c" && break
done
if [ -n "$CHECK_CLOUD" ]; then
  verdict="$(python3 "$CHECK_CLOUD" --porcelain "$VAULT" 2>/dev/null)"
  case "$verdict" in
    OK_LOCAL)
      ok "Vault is on a local disk (not a consumer cloud-sync root)" ;;
    CLOUD_SYNC_RISK:*)
      bad "Vault is inside ${verdict#CLOUD_SYNC_RISK:} — a consumer cloud-sync folder" \
        "A git-backed vault here melts the sync daemon (pegged CPU / frozen machine). Move it local (e.g. ~/Brain). See docs/CLOUD_SYNC.md." ;;
    *)
      warn "Could not evaluate cloud-sync location" "check-cloud-sync.py returned: ${verdict:-<empty>}" ;;
  esac
else
  warn "check-cloud-sync.py not found" "Cannot verify the vault is outside a cloud-sync root."
fi

# ----- 12. off-machine backup (the one-disk-failure class) -----
section "12. Off-machine backup"
CHECK_BACKUP=""
for c in "$(cd "$(dirname "$0")" && pwd)/check-vault-backup.py" \
         "$HOME/.claude/skills/ai-brain-starter/scripts/check-vault-backup.py"; do
  [ -f "$c" ] && CHECK_BACKUP="$c" && break
done
if [ -n "$CHECK_BACKUP" ]; then
  bverdict="$(python3 "$CHECK_BACKUP" --porcelain "$VAULT" 2>/dev/null)"
  case "$bverdict" in
    BACKED_UP:vault-backup:*)
      ok "Off-machine backup present (vault-backup, ~${bverdict##*:} days old)" ;;
    BACKED_UP:timemachine)   ok "Off-machine backup present (Time Machine destination configured)" ;;
    BACKED_UP:cloud:*)       ok "Off-machine copy present (${bverdict#BACKED_UP:cloud:} — a cloud copy; single-file snapshots are safer, see docs/BACKUP.md)" ;;
    BACKED_UP:git-remote)    ok "Off-machine backup present (git HEAD pushed to a remote)" ;;
    NO_BACKUP:configured-not-run)
      warn "Backup configured but no snapshot exists yet (or destination unreachable)" \
        "Run: bash scripts/vault-backup.sh run --vault '$VAULT'" ;;
    NO_BACKUP)
      bad "Vault has NO off-machine backup — one disk failure loses everything" \
        "Set one up (one command): bash scripts/vault-backup.sh setup --vault '$VAULT'. See docs/BACKUP.md." ;;
    *)
      warn "Could not evaluate backup status" "check-vault-backup.py returned: ${bverdict:-<empty>}" ;;
  esac
else
  warn "check-vault-backup.py not found" "Cannot verify the vault has an off-machine backup."
fi

# ----- 13. Obsidian renderer crashes (the large-vault OOM class) -----
section "13. Obsidian renderer crashes"
CHECK_RENDERER=""
for c in "$(cd "$(dirname "$0")" && pwd)/check-renderer-crashes.py" \
         "$HOME/.claude/skills/ai-brain-starter/scripts/check-renderer-crashes.py"; do
  [ -f "$c" ] && CHECK_RENDERER="$c" && break
done
if [ -n "$CHECK_RENDERER" ]; then
  rverdict="$(python3 "$CHECK_RENDERER" --porcelain 2>/dev/null)"
  case "$rverdict" in
    OK_NO_CRASHES)
      ok "No repeated Obsidian renderer crashes" ;;
    SKIP_NOT_MACOS)
      ok "Renderer-crash check skipped (macOS-only crash reports)" ;;
    RENDERER_CRASHES:*)
      warn "Repeated Obsidian renderer crashes (${rverdict#RENDERER_CRASHES:} in ~14 days, EXC_BREAKPOINT / renderer OOM)" \
        "A heavy indexer plugin is likely exhausting the renderer on a large vault. Quit Obsidian, set .obsidian/community-plugins.json to [] (restricted mode), reopen, enable Dataview only, then add others one at a time. Scope or drop Smart Connections / Tasks. See templates/rules/obsidian-plugins.md 'Large-vault plugin posture'." ;;
    *)
      warn "Could not evaluate renderer-crash history" "check-renderer-crashes.py returned: ${rverdict:-<empty>}" ;;
  esac
else
  warn "check-renderer-crashes.py not found" "Cannot check for repeated Obsidian renderer crashes."
fi

# ----- summary -----
echo
echo "${B}Summary${N}"
echo "  ${G}OK:   $GREEN${N}"
echo "  ${Y}WARN: $YELLOW${N}"
echo "  ${R}FAIL: $RED${N}"
echo

if [ "$RED" -gt 0 ]; then
  echo "${R}Something is broken.${N} Fix the FAILs above, then re-run."
  exit 1
elif [ "$YELLOW" -gt 0 ]; then
  echo "${Y}Working, with caveats.${N} Address WARNs when convenient."
  exit 2
else
  echo "${G}All green. Your second brain is healthy.${N}"
  exit 0
fi
