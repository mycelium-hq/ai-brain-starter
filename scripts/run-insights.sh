#!/bin/bash
# run-insights.sh -- Generate weekly or monthly journal insight reports via Claude Code CLI
# Usage: ./run-insights.sh weekly   (Monday mornings via cron)
#        ./run-insights.sh monthly  (2nd of each month via cron)
#
# Auto-detects vault root from script location (⚙️ Meta/scripts/ -> 2 levels up).
# Override with VAULT_ROOT env var if needed.

PERIOD="${1:-weekly}"

# Auto-detect vault root from script location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT_DIR="${VAULT_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
LOG_FILE="$SCRIPT_DIR/.insights-cron.log"

# Find the Claude CLI (path changes with version updates)
CLAUDE_BASE="$HOME/Library/Application Support/Claude/claude-code"
CLAUDE_BIN=$(find "$CLAUDE_BASE" -name "claude" -path "*/MacOS/claude" 2>/dev/null | sort -V | tail -1)

if [ -z "$CLAUDE_BIN" ]; then
  echo "$(date): ERROR -- Claude CLI not found in $CLAUDE_BASE" >> "$LOG_FILE"
  exit 1
fi

echo "$(date): Starting $PERIOD insights generation..." >> "$LOG_FILE"

cd "$VAULT_DIR" || exit 1

"$CLAUDE_BIN" --print "/$PERIOD" 2>>"$LOG_FILE" | tee -a "$LOG_FILE"

echo "$(date): $PERIOD insights complete." >> "$LOG_FILE"
