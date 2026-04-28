#!/usr/bin/env bash
# Check Claude Code installed version against the latest GitHub release.
# Warns at SessionStart if behind by >=3 patch versions. Caches result for 24h
# to avoid hammering the GitHub API on every session.
#
# Why: Claude Code drift is silent — there's no built-in "you're behind"
# notification. Multi-version drift means you miss memory-leak fixes, bash-cwd
# fixes, and other reliability improvements that ship every few weeks. This
# hook surfaces the gap at SessionStart so it can't hide.
#
# Wiring: SessionStart (no matcher needed). Pairs with vault-context.py or any
# UserPromptSubmit hook that wants to surface the warning inline by reading
# the cache file.
#
# Requires `gh` CLI installed and authenticated. Exits silently if missing.

set -uo pipefail

CACHE_FILE="$HOME/.claude/.claude-code-version-check"
CACHE_TTL_SEC=$((24 * 60 * 60))   # 24 hours
WARN_VERSION_GAP=3                # warn if behind by N or more patch versions

now=$(date +%s)
if [[ -f "$CACHE_FILE" ]]; then
  last=$(stat -f %m "$CACHE_FILE" 2>/dev/null || stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0)
  age=$(( now - last ))
  if (( age < CACHE_TTL_SEC )); then
    cat "$CACHE_FILE"
    exit 0
  fi
fi

# Need gh CLI; if missing, exit silently
if ! command -v gh >/dev/null 2>&1; then
  exit 0
fi

current=$(claude --version 2>/dev/null | awk '{print $1}')
[[ -z "$current" ]] && exit 0

latest=$(gh api repos/anthropics/claude-code/releases/latest --jq .tag_name 2>/dev/null | sed 's/^v//')
[[ -z "$latest" ]] && exit 0

# Parse semver patch components (X.Y.Z)
cur_patch=$(echo "$current" | awk -F. '{print $3}')
lat_patch=$(echo "$latest" | awk -F. '{print $3}')

if [[ "$current" == "$latest" ]]; then
  msg=""
elif [[ -n "$cur_patch" && -n "$lat_patch" ]] && (( lat_patch - cur_patch >= WARN_VERSION_GAP )); then
  gap=$(( lat_patch - cur_patch ))
  msg="[claude-code-version] $current -> latest $latest ($gap versions behind). Upgrade: npm i -g @anthropic-ai/claude-code@latest"
else
  msg="[claude-code-version] $current -> latest $latest. Upgrade when convenient: npm i -g @anthropic-ai/claude-code@latest"
fi

# Cache for 24h
printf '%s\n' "$msg" > "$CACHE_FILE"
[[ -n "$msg" ]] && echo "$msg" >&2
exit 0
