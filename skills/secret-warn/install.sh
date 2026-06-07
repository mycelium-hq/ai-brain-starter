#!/usr/bin/env bash
# secret-warn — public substrate version installer (MIT)
# Idempotent. Reads from this folder. Writes to:
#   ~/.claude/secret-warn/   (skill files + audit log)
#   ~/.claude/settings.json  (hook registration, non-destructive merge)

set -euo pipefail

SKILL_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DEST="${SECRET_WARN_ROOT:-$HOME/.claude/secret-warn}"

echo "[secret-warn] installing to $SKILL_DEST"

mkdir -p "$SKILL_DEST"
cp "$SKILL_SRC/hooks/secret_warn.py" "$SKILL_DEST/secret_warn.py"
cp "$SKILL_SRC/hooks/pattern_registry.json" "$SKILL_DEST/pattern_registry.json"
cp "$SKILL_SRC/hooks/hooks.json" "$SKILL_DEST/hooks.json"
chmod +x "$SKILL_DEST/secret_warn.py"

# Merge hook entries into ~/.claude/settings.json (non-destructive)
python3 - <<PYMERGE
import json, os
from pathlib import Path

settings_path = Path(os.path.expanduser("~/.claude/settings.json"))
hooks_src = Path("$SKILL_DEST/hooks.json")
new_hooks = json.loads(hooks_src.read_text())

settings_path.parent.mkdir(parents=True, exist_ok=True)
if settings_path.exists():
    settings = json.loads(settings_path.read_text())
else:
    settings = {}

settings.setdefault("hooks", {})
for event in ("PreToolUse", "PostToolUse"):
    existing = settings["hooks"].setdefault(event, [])
    incoming = new_hooks.get(event, [])
    existing_descs = set()
    for entry in existing:
        for h in entry.get("hooks", []):
            if h.get("description"):
                existing_descs.add(h["description"])
    for entry in incoming:
        kept = [h for h in entry.get("hooks", []) if h.get("description") not in existing_descs]
        if kept:
            new_entry = dict(entry)
            new_entry["hooks"] = kept
            existing.append(new_entry)

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print(f"[secret-warn] merged hook entries into {settings_path}")
PYMERGE

echo "[secret-warn] install complete"
echo "[secret-warn] verify: python3 $SKILL_DEST/secret_warn.py < /dev/null && echo OK"
echo "[secret-warn] bypass: SECRET_WARN_BYPASS=1 <your-command>"
echo "[secret-warn] upgrade: https://myceliumai.co"
