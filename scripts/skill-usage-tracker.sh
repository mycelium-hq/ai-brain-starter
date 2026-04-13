#!/usr/bin/env bash
# skill-usage-tracker.sh
# Claude Code PostToolUse hook: logs Skill invocations to a JSONL file.
# Reads hook JSON from stdin, checks if tool_name is "Skill",
# and appends a log line with skill name, timestamp, and args.
# Always exits 0 to never block the tool pipeline.

set -euo pipefail

# Detect vault root: use $VAULT_ROOT env var, or infer from script location
# (expects this script to live in <vault>/⚙️ Meta/scripts/)
if [ -n "${VAULT_ROOT:-}" ]; then
  _VAULT="$VAULT_ROOT"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _VAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

LOG_FILE="$_VAULT/⚙️ Meta/skill-usage-log.jsonl"

# Read stdin (the hook payload)
INPUT="$(cat)"

# Quick check: bail early if this is not a Skill invocation
TOOL_NAME="$(printf '%s' "$INPUT" | /usr/bin/python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || true)"

if [ "$TOOL_NAME" != "Skill" ]; then
  exit 0
fi

# Extract skill name and args from tool_input
read -r SKILL_NAME SKILL_ARGS < <(
  printf '%s' "$INPUT" | /usr/bin/python3 -c "
import sys, json
data = json.load(sys.stdin)
ti = data.get('tool_input', {})
print(ti.get('skill', ''), ti.get('args', ''))
" 2>/dev/null || echo ""
)

if [ -z "$SKILL_NAME" ]; then
  exit 0
fi

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%S")"

# Ensure the log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Build the JSON line with Python to handle escaping correctly
/usr/bin/python3 -c "
import json, sys
print(json.dumps({
    'skill': sys.argv[1],
    'timestamp': sys.argv[2],
    'args': sys.argv[3]
}, ensure_ascii=False))
" "$SKILL_NAME" "$TIMESTAMP" "$SKILL_ARGS" >> "$LOG_FILE" 2>/dev/null || true

exit 0
