#!/usr/bin/env python3
"""
sessionstart-hook-snapshot-guard.py - warn if a SessionStart hook DISAPPEARED.

A SessionStart hook can silently vanish from settings.json - a linter, a manual
edit, or a parallel session can prune one, and the loss stays invisible until you
happen to notice the missing behavior. This guard snapshots which SessionStart
hooks are wired and warns inline when one disappears.

De-noised: the original diffed exact command STRINGS, so any cosmetic reword by a
concurrent session - `python3` <-> `/usr/bin/python3`, `~/` <-> absolute path,
adding/removing a `2>/dev/null || echo {...}` wrapper or a `[ -f X ] &&` guard -
false-flagged a hook as "missing" when the SAME SCRIPT was still wired. Cry-wolf
is how the ONE real drop gets scrolled past, so the guard now diffs SCRIPT
IDENTITY (script basename + normalized args) instead of raw command text.

Behavior:
  - Snapshot SessionStart hook IDENTITIES to
    ~/.claude/state/sessionstart-hooks-snapshot.json (versioned: {"v":2,...}).
  - On each fire, diff current identities against the snapshot.
  - Any prior identity MISSING from current -> inline warning (snapshot NOT
    updated, so the warning persists until reconciled).
  - New identities only -> update snapshot silently (additions are fine).
  - First run / corrupt / legacy snapshot -> (re)baseline silently.
  - `--refresh` -> force-rewrite the snapshot to current and exit 0 (this is what
    "if intentional, refresh" means; the old in-band rerun never refreshed
    because the missing-branch skips the update).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
STATE = Path.home() / ".claude" / "state" / "sessionstart-hooks-snapshot.json"


def _script_identity(cmd: str) -> str:
    """Normalize a hook command to a stable identity: 'basename' or
    'basename||args'. Collapses python-path / tilde-vs-absolute / [ -f X ] &&
    guard / 2>redirect / || fallback variants of the same script."""
    c = (cmd or "").strip()
    c = re.sub(r"^\[\s*-[fe]\s+[^\]]*\]\s*&&\s*", "", c)   # leading [ -f X ] && guard
    c = re.split(r"\s*\|\|\s*", c)[0]                       # trailing || true / || echo {...}
    c = re.sub(r"\s*2>\S+", "", c).strip()                  # 2>/dev/null
    m = re.search(r"([~/][^\s'\"]*\.(?:py|sh))", c)
    if not m:
        return c[:100]                                      # non-script command: trimmed text
    p = m.group(1)
    after = c[c.find(p) + len(p):].strip()
    return f"{Path(p).name}||{after}" if after else Path(p).name


def extract_sessionstart_commands(settings_path: Path) -> list[str]:
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[str] = []
    for block in (data.get("hooks", {}).get("SessionStart") or []):
        for hook in (block.get("hooks") or []):
            cmd = (hook.get("command") or "").strip()
            if cmd:
                out.append(cmd)
    return out


def _current_identities() -> set[str]:
    return {_script_identity(c) for c in extract_sessionstart_commands(SETTINGS)}


def _load_prior() -> set[str] | None:
    """Prior identities, or None if missing/corrupt. Legacy snapshots (a bare
    list of raw command strings) are normalized once on read; v2 snapshots
    (already identities) are used verbatim - re-normalizing them would be lossy."""
    try:
        raw = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, dict) and raw.get("v") == 2:
        return set(raw.get("identities", []))
    if isinstance(raw, list):
        return {_script_identity(c) for c in raw}
    return None


def _save(identities: set[str]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"v": 2, "identities": sorted(identities)}, indent=2),
                     encoding="utf-8")


def _label(identity: str) -> str:
    bn, _, args = identity.partition("||")
    return f"{bn} {args}".strip()


def main() -> int:
    if "--refresh" in sys.argv:
        _save(_current_identities())
        print("[sessionstart-hook-guard] snapshot refreshed to current SessionStart hooks.")
        return 0

    current = _current_identities()
    if not current:
        return 0  # settings malformed or no hooks; don't false-alarm

    prior = _load_prior()
    if prior is None:
        _save(current)                       # baseline / migrate / repair, silent
        return 0

    missing = prior - current
    if missing:
        print(f"[sessionstart-hook-guard] WARNING: {len(missing)} SessionStart hook(s) missing since last snapshot:")
        for ident in sorted(missing):
            print(f"  - {_label(ident)}")
        print("[sessionstart-hook-guard] If intentional: `python3 ~/.claude/hooks/sessionstart-hook-snapshot-guard.py --refresh`. If not: re-add the missing hook(s).")
        # Do NOT update snapshot - leave it so the warning persists until reconciled.
        return 0

    additions = current - prior
    if additions:
        _save(current)                       # additions are fine - absorb silently
    return 0


if __name__ == "__main__":
    sys.exit(main())
