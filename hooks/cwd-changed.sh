#!/bin/bash
# CwdChanged hook: log cwd changes + run vault-integrity checks when
# entering a wrapped vault (fixes cwd-mismatch bug in team vaults per
# CLAUDE.md (see canonical rule)).
#
# Cannot block; exit code ignored. stderr shown to user only.

LOG=$HOME/.claude/hooks/cwd-changed.log
PAYLOAD=$(cat)

# Parse cwd from JSON stdin (minimal, avoids jq dep). python3 -I keeps the working directory
# and PYTHON* settings out; -X utf8 reads and prints UTF-8 whatever the locale says (-I
# ignores PYTHONUTF8, so the locale would decide).
NEW_CWD=$(printf '%s' "$PAYLOAD" | python3 -I -X utf8 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("cwd",""))' 2>/dev/null)
OLD_CWD=$(printf '%s' "$PAYLOAD" | python3 -I -X utf8 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("previous_cwd",""))' 2>/dev/null)

printf '%s\t%s -> %s\n' "$(date -Iseconds)" "$OLD_CWD" "$NEW_CWD" >> "$LOG"

exit 0
