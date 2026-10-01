#!/bin/bash
# FileChanged hook for .claude/settings.json and .mcp.json.
# Validates JSON + surfaces change to stderr so the user sees it.
# Cannot block. Used for side-effects only.

PAYLOAD=$(cat)
FILE=$(printf '%s' "$PAYLOAD" | python3 -I -c 'import json,sys;d=json.load(sys.stdin);print(d.get("file_path",""))' 2>/dev/null)

[ -z "$FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

# The path is an argument, never part of the program: spliced into the source, a quote in it
# breaks the program or ends it early.
if ! python3 -I -c 'import json,sys;json.load(open(sys.argv[1]))' "$FILE" 2>/dev/null; then
  echo "[file-changed] INVALID JSON in $FILE — session settings may be broken. Validate before continuing." >&2
  exit 0
fi

echo "[file-changed] $FILE updated and parses OK." >&2
exit 0
