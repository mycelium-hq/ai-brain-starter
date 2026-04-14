#!/bin/bash
# PostToolUse hook — fires after every Write tool call
# Auto-triggers meeting-todos extraction when a meeting note is saved

INPUT=$(cat)

# Extract file_path from the Write tool input
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    path = d.get('tool_input', {}).get('file_path', '')
    print(path)
except:
    print('')
" 2>/dev/null)

if echo "$FILE_PATH" | grep -qi "Meeting Notes/\|Meeting-Notes/"; then
  BASENAME=$(basename "$FILE_PATH" .md)
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"Meeting note saved: '$BASENAME'. Run /meeting-todos on this file now -- extract action items, show the user a preview, and add confirmed tasks to the to-do file. Do this automatically without waiting to be asked.\"}}"
else
  echo "{}"
fi
