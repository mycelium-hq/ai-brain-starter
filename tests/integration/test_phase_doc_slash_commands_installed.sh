#!/usr/bin/env bash
# Test that every slash command referenced in phase docs as a user-runnable
# skill has (a) a matching skill folder in skills/ AND (b) is in the
# bootstrap.sh install loop. Prevents the bug class where a phase doc
# tells the user to "run /foo" but the skill was never installed by the
# bootstrap, so /foo doesn't appear in their slash command list.
#
# Source incident: a fresh install completed successfully, Phase 23.5
# instructed the user to run /second-brain-mapping, but the skill was
# never copied to ~/.claude/skills/ because bootstrap.sh's install loop
# didn't include it. Typing "/" in a new session didn't surface the
# command at all. Skill folder existed in the repo but the install loop
# was hardcoded to a smaller list.
#
# Skills audited: those referenced in `templates/rules/` and `phases/`
# documents as user-invocable slash commands. Excludes:
#   - Built-in slash commands (/wrap-up, /close, /journal as alias)
#   - Internal scripts (vault-metadata-extract.py is a script, not a skill)
#   - Closing-signal keywords (/cerrar, /fechar, /encerrar — detector keywords,
#     not skills)
#
# Self-contained. Exit 0 = pass. Exit 1 = fail with details.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/bootstrap.sh"
SKILLS_DIR="$REPO_ROOT/skills"
COMMANDS_DIR="$REPO_ROOT/commands"

# Slash commands documented as user-runnable in phase docs.
# Maintained explicitly so we don't accidentally promote a closing-signal
# keyword (/cerrar) or a script reference (/auto-crm-from-mentions) into
# the audit.
REQUIRED_SKILLS=(
  "graphify"
  "meeting-todos"
  "patterns"
  "insights"
  "deconstruct"
  "daily-journal"
  "repurpose-talk"
  "nano-banana"
  "humanizer"
  "diagnose"
  "second-brain-mapping"
  "setup-vault-types"
)

FAILED=0

# Skills installed via a SEPARATE clone path (not from skills/ folder).
# These skip the (a) folder check but still get the (b) install-loop check.
# humanizer = cloned from its own public fork repo per bootstrap.sh header.
SEPARATE_CLONE_SKILLS="humanizer"

for skill in "${REQUIRED_SKILLS[@]}"; do
  is_separate_clone=0
  for sc in $SEPARATE_CLONE_SKILLS; do
    [ "$skill" = "$sc" ] && is_separate_clone=1
  done

  # (a) skill folder exists in repo (skipped for separate-clone skills)
  if [ "$is_separate_clone" = "0" ] && [ ! -d "$SKILLS_DIR/$skill" ]; then
    echo "FAIL: skills/$skill/ folder missing in repo" >&2
    FAILED=$((FAILED + 1))
    continue
  fi
  # (b) skill is in the bootstrap install loop (the one that actually
  # copies files to ~/.claude/skills/). We scan for the literal skill
  # name as a token in the loop's "for sub in" line.
  if ! grep -E "^for sub in .*\b${skill}\b.*; do" "$BOOTSTRAP" >/dev/null 2>&1; then
    echo "FAIL: $skill is referenced as a slash command in phase docs but is NOT in any bootstrap.sh install loop" >&2
    echo "  Phase docs reference /$skill but new installs won't have it." >&2
    echo "  Add '$skill' to the 'for sub in ...' loops in bootstrap.sh." >&2
    FAILED=$((FAILED + 1))
    continue
  fi
  # (c) commands/<skill>.md exists in repo. Without this file, the skill
  # folder is installed but the slash command doesn't appear in the
  # Claude Code palette. This was the surface bug behind the 2026-05-14
  # install report where /second-brain-mapping wasn't surfaced even
  # though the skill folder existed.
  if [ ! -f "$COMMANDS_DIR/$skill.md" ]; then
    echo "FAIL: commands/$skill.md missing in repo" >&2
    echo "  Without this file, /$skill won't appear in the Claude Code slash command palette." >&2
    echo "  Skill folders alone don't register palette entries — commands/<name>.md does." >&2
    FAILED=$((FAILED + 1))
    continue
  fi
done

# Cross-check: every skill in the install loop has a matching folder in
# skills/. Catches typos in the install list.
INSTALL_LIST=$(grep -E "^for sub in .* second-brain-mapping " "$BOOTSTRAP" | head -1 | sed -E 's/^for sub in (.*); do/\1/')
if [ -n "$INSTALL_LIST" ]; then
  for skill in $INSTALL_LIST; do
    # Skip skills installed by separate clone paths (humanizer, ai-brain-starter)
    case "$skill" in
      humanizer|ai-brain-starter) continue ;;
    esac
    if [ ! -d "$SKILLS_DIR/$skill" ]; then
      echo "FAIL: bootstrap install loop lists '$skill' but skills/$skill/ does not exist" >&2
      FAILED=$((FAILED + 1))
    fi
  done
fi

if [ "$FAILED" -gt 0 ]; then
  echo "" >&2
  echo "$FAILED skill(s) failed the phase-doc / install-loop integrity check." >&2
  exit 1
fi

echo "All ${#REQUIRED_SKILLS[@]} required skills present in repo AND in bootstrap install loop."
