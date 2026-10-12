#!/bin/bash
# claude-scheduled-runner.sh — headless Claude Code runner for launchd / cron
# Usage: claude-scheduled-runner.sh <task-name>
#
# Runs a Claude Code scheduled task in headless (-p) mode.
# Reads the task prompt from the scheduled-tasks SKILL.md file.
# Logs output to ~/Library/Logs/claude-scheduled-<task>.log
#
# Environment variables (all optional):
#   VAULT_ROOT       — working directory passed to claude (default: ~)
#   CLAUDE_BIN       — path to claude binary (default: searches PATH then common locations)
#   TASKS_DIR        — where scheduled-task SKILL.md files live
#                      (default: ~/.claude/scheduled-tasks)
#   LOG_DIR          — where to write run logs
#                      (default: ~/Library/Logs on macOS, ~/.local/log elsewhere)

set -euo pipefail

TASK_NAME="${1:?Usage: claude-scheduled-runner.sh <task-name>}"

# Resolve Claude binary
if [ -n "${CLAUDE_BIN:-}" ]; then
  CLAUDE="$CLAUDE_BIN"
elif command -v claude &>/dev/null; then
  CLAUDE="claude"
else
  # Common install locations
  for candidate in \
    "$HOME/.local/bin/claude" \
    "$HOME/local/bin/claude" \
    "/usr/local/bin/claude" \
    "$HOME/.npm-global/bin/claude"; do
    if [ -x "$candidate" ]; then
      CLAUDE="$candidate"
      break
    fi
  done
fi
: "${CLAUDE:?Cannot find claude binary. Set CLAUDE_BIN or add claude to PATH.}"

TASKS_DIR="${TASKS_DIR:-$HOME/.claude/scheduled-tasks}"
SKILL_FILE="$TASKS_DIR/${TASK_NAME}/SKILL.md"

if [ "$(uname)" = "Darwin" ]; then
  DEFAULT_LOG_DIR="$HOME/Library/Logs"
else
  DEFAULT_LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/log}"
fi
LOG_DIR="${LOG_DIR:-$DEFAULT_LOG_DIR}"
LOG_FILE="$LOG_DIR/claude-scheduled-${TASK_NAME}.log"

VAULT_ROOT="${VAULT_ROOT:-$HOME}"

if [[ ! -f "$SKILL_FILE" ]]; then
  echo "$(date -Iseconds) ERROR: skill file not found: $SKILL_FILE" >> "$LOG_FILE"
  exit 1
fi

# Extract the prompt (everything after the frontmatter closing ---)
PROMPT=$(awk 'BEGIN{skip=0} /^---$/{skip++; next} skip>=2{print}' "$SKILL_FILE")

if [[ -z "$PROMPT" ]]; then
  echo "$(date -Iseconds) ERROR: empty prompt in $SKILL_FILE" >> "$LOG_FILE"
  exit 1
fi

echo "$(date -Iseconds) START: running task ${TASK_NAME}" >> "$LOG_FILE"

"$CLAUDE" -p "$PROMPT" \
    --max-turns 30 \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch" \
    -d "$VAULT_ROOT" \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "$(date -Iseconds) END: task ${TASK_NAME} exited with code ${EXIT_CODE}" >> "$LOG_FILE"
exit $EXIT_CODE
