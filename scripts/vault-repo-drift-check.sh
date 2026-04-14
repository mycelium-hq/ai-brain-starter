#!/bin/bash
# vault-repo-drift-check.sh — Detect when the vault has things the repo doesn't
#
# Runs monthly. Compares:
# 1. Vault rules/ vs repo templates/rules/
# 2. Vault scripts/ vs repo scripts/
# 3. Vault skills vs repo skills/
# 4. Vault hooks vs repo hooks/
# 5. Vault CLAUDE.md skill routing vs repo SKILL.md Phase 9
#
# Output: a list of files/features that exist in the vault but not the repo.
# For the maintainer: these are candidates for upstream propagation.
# For other users: these are features they're missing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Detect vault root (look for ⚙️ Meta/ folder)
if [ -n "${VAULT_ROOT:-}" ] && [ -d "$VAULT_ROOT" ]; then
  VAULT="$VAULT_ROOT"
else
  echo "ERROR: Set VAULT_ROOT to your vault path" >&2
  exit 1
fi

META="$VAULT/⚙️ Meta"
DRIFT_FOUND=0

echo "=== Vault-to-Repo Drift Check ==="
echo "Vault: $VAULT"
echo "Repo:  $REPO_ROOT"
echo ""

# 1. Rules files
echo "--- Rules ---"
for rule in "$META/rules/"*.md; do
  [ -f "$rule" ] || continue
  base=$(basename "$rule")
  if [ ! -f "$REPO_ROOT/templates/rules/$base" ]; then
    echo "  DRIFT: rules/$base exists in vault but not in repo"
    DRIFT_FOUND=1
  fi
done

# 2. Scripts
echo "--- Scripts ---"
for script in "$META/scripts/"*.{sh,py}; do
  [ -f "$script" ] || continue
  base=$(basename "$script")
  [ "$base" = "__pycache__" ] && continue
  if [ ! -f "$REPO_ROOT/scripts/$base" ]; then
    echo "  DRIFT: scripts/$base exists in vault but not in repo"
    DRIFT_FOUND=1
  fi
done

# 3. Skills
echo "--- Skills ---"
for skill_dir in ~/.claude/skills/*/; do
  [ -d "$skill_dir" ] || continue
  skill_name=$(basename "$skill_dir")
  # Skip the repo itself and external skills
  [ "$skill_name" = "ai-brain-starter" ] && continue
  [ "$skill_name" = "humanizer" ] && continue
  [ "$skill_name" = "notebooklm" ] && continue
  if [ ! -d "$REPO_ROOT/skills/$skill_name" ]; then
    echo "  DRIFT: skill $skill_name installed but not in repo"
    DRIFT_FOUND=1
  fi
done

# 4. Hooks
echo "--- Hooks ---"
for hook in ~/.claude/hooks/*.sh; do
  [ -f "$hook" ] || continue
  base=$(basename "$hook")
  if [ ! -f "$REPO_ROOT/hooks/$base" ]; then
    echo "  DRIFT: hook $base exists locally but not in repo"
    DRIFT_FOUND=1
  fi
done

# 5. Obsidian plugins
echo "--- Obsidian Plugins ---"
if [ -d "$VAULT/.obsidian/plugins" ]; then
  for plugin_dir in "$VAULT/.obsidian/plugins/"*/; do
    [ -d "$plugin_dir" ] || continue
    plugin_name=$(basename "$plugin_dir")
    # Check if plugin is in the SKILL.md auto-install list
    if ! grep -q "\"$plugin_name\"" "$REPO_ROOT/SKILL.md" 2>/dev/null; then
      echo "  DRIFT: Obsidian plugin $plugin_name installed but not in repo auto-install"
      DRIFT_FOUND=1
    fi
  done
fi

echo ""
if [ $DRIFT_FOUND -eq 0 ]; then
  echo "No drift detected. Vault and repo are in sync."
else
  echo "Drift detected. Review items above and propagate to the repo if they're universal."
fi
