#!/usr/bin/env bash
# patch-claude-mem-read-hook.sh
#
# Disables the claude-mem PreToolUse:Read hook. The hook replaces Read tool
# output with a "prior observations" timeline plus just line 1 of the file,
# which breaks normal file reads. Subsequent re-reads with offset/limit get
# short-circuited by Read as "file unchanged", so the full content never
# reaches the agent.
#
# Run this after any claude-mem plugin update that restores the PreToolUse
# entry in hooks/hooks.json.
#
# Idempotent: safe to run repeatedly. Creates a timestamped backup before
# patching. No-op if already disabled.
#
# Ship date: 2026-04-15

set -eu
set -o pipefail

PLUGIN_GLOB="$HOME/.claude/plugins/cache/thedotmack/claude-mem"
HOOKS_JSON=""

# Find latest installed version
latest=$(ls -dt "$PLUGIN_GLOB"/[0-9]*/ 2>/dev/null | head -1 || true)
if [ -n "$latest" ]; then
    latest="${latest%/}"
    HOOKS_JSON="$latest/hooks/hooks.json"
fi

if [ -z "$HOOKS_JSON" ] || [ ! -f "$HOOKS_JSON" ]; then
    echo "claude-mem plugin not installed, nothing to patch"
    exit 0
fi

echo "target: $HOOKS_JSON"

if grep -q "_PreToolUse_DISABLED" "$HOOKS_JSON"; then
    echo "already patched, nothing to do"
    exit 0
fi

if ! grep -q '"PreToolUse"' "$HOOKS_JSON"; then
    echo "no PreToolUse hook present, nothing to patch"
    exit 0
fi

ts=$(date +%Y%m%d_%H%M)
cp "$HOOKS_JSON" "$HOOKS_JSON.backup_$ts"
echo "backup: $HOOKS_JSON.backup_$ts"

# Rename the "PreToolUse" key so Claude Code ignores it. Adds a _reason field.
python3 - "$HOOKS_JSON" <<'PY'
import json, sys
p = sys.argv[1]
d = json.loads(open(p).read())
hooks = d.get("hooks", {})
if "PreToolUse" in hooks:
    reason = (
        "Disabled: file-context hook replaced Read output with just "
        "line 1 plus observations timeline, breaking file reads. See efficiency.md."
    )
    entries = hooks["PreToolUse"]
    for e in entries:
        e["_reason"] = reason
    hooks["_PreToolUse_DISABLED_2026-04-15"] = entries
    del hooks["PreToolUse"]
    open(p, "w").write(json.dumps(d, indent=2))
    print("patched")
else:
    print("PreToolUse key not found after backup, no change")
PY

echo "done."
