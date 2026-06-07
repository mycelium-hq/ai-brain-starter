#!/usr/bin/env bash
# detect-partial-installs.sh — scan for half-installed components.
#
# Closes adelaidasofia/ai-brain-starter#4 — bootstrap: detect partially-installed
# graphify (missing scripts/ subfolder) and offer to refresh.
#
# Generalizes to any of the bundled skills + key infrastructure:
#   - graphify (CLI present? skill present? scripts/ subfolder present?)
#   - daily-journal, insights, meeting-todos, patterns (SKILL.md exists?)
#   - humanizer (cloned + has src/ ?)
#   - settings.json + .mcp.json (parseable JSON?)
#   - aggregate-sessions.py + aggregate-decisions.py present in vault Meta/scripts?
#
# Output: structured list of issues with suggested fix commands.
#
# Usage:
#   bash scripts/detect-partial-installs.sh              # human-readable
#   bash scripts/detect-partial-installs.sh --json       # machine-readable
#   bash scripts/detect-partial-installs.sh --vault PATH # check vault-side too
#   bash scripts/detect-partial-installs.sh --fix        # auto-fix what's safe
#
# Exit codes: 0 = clean, 1 = issues found, 2 = critical issue (broken JSON config).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

JSON_OUTPUT=0
AUTO_FIX=0
VAULT_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON_OUTPUT=1; shift ;;
    --fix) AUTO_FIX=1; shift ;;
    --vault) VAULT_ROOT="$2"; shift 2 ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

ISSUES=()
CRITICAL=0

add_issue() {
  local severity="$1"
  local component="$2"
  local description="$3"
  local fix="$4"
  ISSUES+=("$severity|$component|$description|$fix")
  if [[ "$severity" == "critical" ]]; then
    CRITICAL=1
  fi
}

# === checks ===

check_graphify() {
  if ! command -v graphify >/dev/null 2>&1; then
    add_issue "warn" "graphify-cli" "graphify CLI not in PATH" "pipx install graphifyy"
    return
  fi
  local skill_dir="$HOME/.claude/skills/graphify"
  if [[ ! -d "$skill_dir" ]]; then
    add_issue "warn" "graphify-skill" "$skill_dir is missing" "graphify install --claude"
    return
  fi
  if [[ ! -d "$skill_dir/scripts" ]]; then
    add_issue "warn" "graphify-scripts" "graphify skill installed but scripts/ subfolder is missing (partial install)" "rm -rf '$skill_dir' && graphify install --claude"
  fi
  if [[ ! -f "$skill_dir/SKILL.md" ]]; then
    add_issue "warn" "graphify-skillmd" "graphify SKILL.md is missing from $skill_dir" "graphify install --claude --force"
  fi
}

check_bundled_skill() {
  local name="$1"
  local skill_dir="$HOME/.claude/skills/$name"
  if [[ ! -d "$skill_dir" ]]; then
    add_issue "info" "skill-$name" "$name skill not installed (this is fine if you didn't install it)" "bash bootstrap.sh"
    return
  fi
  if [[ ! -f "$skill_dir/SKILL.md" ]]; then
    add_issue "warn" "skill-$name" "$name skill folder exists but SKILL.md missing (partial install)" "bash bootstrap.sh"
  fi
}

check_humanizer() {
  local skill_dir="$HOME/.claude/skills/humanizer"
  if [[ ! -d "$skill_dir" ]]; then
    add_issue "info" "humanizer" "humanizer skill not installed" "git clone https://github.com/adelaidasofia/humanizer.git $skill_dir"
    return
  fi
  if [[ ! -d "$skill_dir/src" ]] && [[ ! -f "$skill_dir/SKILL.md" ]]; then
    add_issue "warn" "humanizer" "humanizer folder exists but missing core files (partial install)" "rm -rf '$skill_dir' && git clone https://github.com/adelaidasofia/humanizer.git '$skill_dir'"
  fi
}

check_json_config() {
  local file="$1"
  local component="$2"
  if [[ ! -f "$file" ]]; then
    return  # not present is fine; only check if it exists
  fi
  if ! python3 -c "import json; json.load(open('$file'))" 2>/dev/null; then
    add_issue "critical" "$component" "$file is not valid JSON (parser error)" "bash $(dirname "$0")/bootstrap-restore.sh --path '$file'"
  fi
}

check_vault_aggregators() {
  local vault="$1"
  if [[ ! -d "$vault" ]]; then
    return
  fi
  # Auto-detect Meta folder via the shared resolver (prefers the variant
  # containing a known subfolder, so a machine "Meta/" can't shadow "⚙️ Meta/").
  local meta=""
  meta="$(python3 "$SCRIPT_DIR/_meta_resolver.py" "$vault" scripts Decisions 2>/dev/null || true)"
  [[ -z "$meta" ]] && [[ -d "$vault/Meta" ]] && meta="$vault/Meta"
  if [[ -z "$meta" ]]; then
    add_issue "info" "vault-meta" "no Meta folder found in $vault (vault may not be set up yet)" "(run /setup-brain)"
    return
  fi
  for script in "aggregate-sessions.py" "aggregate-decisions.py"; do
    if [[ ! -f "$meta/scripts/$script" ]]; then
      add_issue "warn" "vault-aggregator" "$script missing from $meta/scripts/" "cp ~/.claude/skills/ai-brain-starter/scripts/$script '$meta/scripts/'"
    fi
  done
}

check_ai_brain_starter() {
  local skill_dir="$HOME/.claude/skills/ai-brain-starter"
  if [[ ! -d "$skill_dir" ]]; then
    add_issue "warn" "ai-brain-starter" "ai-brain-starter skill not installed at $skill_dir" "git clone https://github.com/adelaidasofia/ai-brain-starter.git '$skill_dir'"
    return
  fi
  if [[ ! -f "$skill_dir/SKILL.md" ]]; then
    add_issue "warn" "ai-brain-starter" "SKILL.md missing from $skill_dir (partial install)" "cd '$skill_dir' && git pull"
  fi
  # Detect divergence from origin
  if [[ -d "$skill_dir/.git" ]]; then
    local local_head
    local_head=$(git -C "$skill_dir" rev-parse HEAD 2>/dev/null || echo "")
    git -C "$skill_dir" fetch origin main --quiet 2>/dev/null || true
    local origin_head
    origin_head=$(git -C "$skill_dir" rev-parse origin/main 2>/dev/null || echo "")
    if [[ -n "$local_head" ]] && [[ -n "$origin_head" ]] && [[ "$local_head" != "$origin_head" ]]; then
      local behind
      behind=$(git -C "$skill_dir" rev-list --count "$local_head..$origin_head" 2>/dev/null || echo "0")
      if [[ "$behind" -gt 0 ]]; then
        add_issue "info" "ai-brain-starter" "$behind commit(s) behind origin/main" "cd '$skill_dir' && git pull"
      fi
    fi
  fi
}

# === run all checks ===

check_graphify
check_humanizer
check_ai_brain_starter
for s in daily-journal insights meeting-todos patterns deconstruct repurpose-talk nano-banana; do
  check_bundled_skill "$s"
done

check_json_config "$HOME/.claude/settings.json" "claude-settings"
check_json_config "$HOME/.claude/settings.local.json" "claude-settings-local"
check_json_config "$HOME/.claude/.mcp.json" "mcp-config"

if [[ -n "$VAULT_ROOT" ]]; then
  check_vault_aggregators "$VAULT_ROOT"
fi

# === output ===

if [[ "$JSON_OUTPUT" -eq 1 ]]; then
  printf '{"issues":['
  first=1
  for i in "${ISSUES[@]:-}"; do
    [[ -z "$i" ]] && continue
    IFS='|' read -r sev comp desc fix <<<"$i"
    if [[ $first -eq 0 ]]; then printf ','; fi
    first=0
    printf '{"severity":"%s","component":"%s","description":"%s","fix":"%s"}' \
      "$sev" "$comp" \
      "$(printf '%s' "$desc" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read())[1:-1])')" \
      "$(printf '%s' "$fix" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read())[1:-1])')"
  done
  printf '],"critical":%d}\n' "$CRITICAL"
else
  if [[ ${#ISSUES[@]} -eq 0 ]]; then
    printf "\033[32m✓\033[0m All components look clean.\n"
    exit 0
  fi
  printf "\nFound %d issue(s):\n\n" "${#ISSUES[@]}"
  for i in "${ISSUES[@]}"; do
    IFS='|' read -r sev comp desc fix <<<"$i"
    case "$sev" in
      critical) color="\033[31m" ;;
      warn) color="\033[33m" ;;
      info) color="\033[36m" ;;
      *) color="" ;;
    esac
    printf "  ${color}[%s]\033[0m %s\n" "$sev" "$comp"
    printf "      %s\n" "$desc"
    printf "      Fix: %s\n\n" "$fix"
  done

  if [[ "$AUTO_FIX" -eq 1 ]]; then
    echo "--auto-fix not yet implemented; run the suggested Fix commands manually."
  fi
fi

if [[ "$CRITICAL" -eq 1 ]]; then
  exit 2
fi
[[ ${#ISSUES[@]} -gt 0 ]] && exit 1 || exit 0
