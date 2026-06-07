#!/bin/bash
# fix-plugin-hooks.sh
# Replaces ${CLAUDE_PLUGIN_ROOT} with absolute paths in all installed plugin hooks.json files.
#
# Problem: Claude Code does not reliably expand ${CLAUDE_PLUGIN_ROOT} when spawning
# hook subprocesses. When the variable is unset, the hook path resolves to
# "/hooks/script.py" (nonexistent), the hook errors, and Claude Code defaults to
# BLOCK for PreToolUse failures -- silently blocking all Write/Edit operations.
#
# Run this after installing any new plugin:
#   bash scripts/fix-plugin-hooks.sh
#
# Safe to re-run: already-fixed files are left unchanged (no double-replacement).

PLUGINS_DIR="$HOME/.claude/plugins"

if [[ ! -d "$PLUGINS_DIR" ]]; then
    echo "No plugins directory found at $PLUGINS_DIR -- nothing to fix."
    exit 0
fi

fixed=0
while IFS= read -r hooks_file; do
    if grep -q 'CLAUDE_PLUGIN_ROOT' "$hooks_file" 2>/dev/null; then
        echo "Fixing: $hooks_file"
        python3 -c "
import sys
from pathlib import Path
p = Path(sys.argv[1])
plugin_root = str(p.parent.parent)
original = p.read_text()
fixed = original.replace('\${CLAUDE_PLUGIN_ROOT}', plugin_root)
if fixed != original:
    p.write_text(fixed)
    print(f'  replaced CLAUDE_PLUGIN_ROOT -> {plugin_root}')
else:
    print('  already fixed, skipped')
" "$hooks_file"
        fixed=$((fixed + 1))
    fi
done < <(find "$PLUGINS_DIR" -name "hooks.json" 2>/dev/null)

if [[ $fixed -eq 0 ]]; then
    echo "No hooks.json files needed fixing."
else
    echo ""
    echo "Done. Restart Claude Code for hook changes to take effect."
fi
