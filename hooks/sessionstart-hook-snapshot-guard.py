#!/usr/bin/env python3
"""
sessionstart-hook-snapshot-guard.py — warn if the SessionStart hook list shrank.

Fixed 2026-05-19 after my website-audit-freshness hook silently disappeared
from settings.json (linter or parallel session pruned it). The strip was
invisible until Mission Control v3 was rebuilt and I re-discovered it.

Behavior:
  - Snapshot the SessionStart `hooks[].command` strings to
    ~/.claude/state/sessionstart-hooks-snapshot.json
  - On each fire, diff current hooks against snapshot
  - If any prior hook is MISSING from current, surface inline warning
  - If new hooks added, update snapshot silently (additions are fine)
  - Idempotent: first run captures baseline silently
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
STATE = Path.home() / ".claude" / "state" / "sessionstart-hooks-snapshot.json"


def extract_sessionstart_commands(settings_path: Path) -> set[str]:
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    out: set[str] = set()
    for block in (data.get("hooks", {}).get("SessionStart") or []):
        for hook in (block.get("hooks") or []):
            cmd = hook.get("command", "").strip()
            if cmd:
                out.add(cmd)
    return out


def main() -> int:
    current = extract_sessionstart_commands(SETTINGS)
    if not current:
        return 0  # settings malformed or no hooks; don't false-alarm

    STATE.parent.mkdir(parents=True, exist_ok=True)
    if not STATE.exists():
        STATE.write_text(json.dumps(sorted(current), indent=2), encoding="utf-8")
        return 0

    try:
        prior = set(json.loads(STATE.read_text(encoding="utf-8")))
    except Exception:
        # Corrupted snapshot — rewrite from current, no warning
        STATE.write_text(json.dumps(sorted(current), indent=2), encoding="utf-8")
        return 0

    missing = prior - current
    if missing:
        # WARN — print to stdout so SessionStart shows it inline
        print(f"[sessionstart-hook-guard] WARNING: {len(missing)} SessionStart hook(s) missing since last snapshot:")
        for cmd in sorted(missing):
            # Show only the script name, not the full path (more readable)
            scripts = [p for p in cmd.split() if "/" in p and p.endswith((".py", ".sh"))]
            label = scripts[0].split("/")[-1] if scripts else cmd[:80]
            print(f"  - {label}")
        print("[sessionstart-hook-guard] If intentional: rerun this script to refresh snapshot. If not: re-add the missing hook(s).")
        # Do NOT update snapshot — leave it so the warning persists until reconciled

    # Update snapshot with any NEW additions (silent — additions are fine)
    additions = current - prior
    if additions and not missing:
        STATE.write_text(json.dumps(sorted(current), indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
