#!/usr/bin/env python3
"""SessionStart hook: surface vault-relocation drift back to an old path (the visible half).

The every-session canary for the relocation watchdog. After a vault is moved off a
cloud-sync folder (scripts/relocate-vault.sh), tooling that still hardcodes the OLD
path silently `mkdir`s a phantom folder there / breaks every run. scripts/relocate-
sweep.py --watch is the tested detection core (it reads the install's recorded move(s)
from the manifest and classifies residual references); this hook names the drift at
the NEXT session start so a re-introduced hardcode surfaces fast instead of riding a
symlink unseen for days.

WALK-FREE BY CONSTRUCTION: it reads two small JSON files (the relocation manifest +
the cached watch verdict) and does ONE stat() per recorded move. It never walks a
corpus, so it stays bounded under concurrency (the SessionStart freeze class, the
incident scripts/audit-sessionstart-boundedness.py guards). The heavy residual scan
lives in relocate-sweep.py --watch, run by the daily-maintenance cron AND by a
cooldown-gated, single-spawn, DETACHED refresh fired here when the cache is stale —
never inline.

Output: silent when nothing was ever relocated, or when every recorded move is clean.
One systemMessage block when an old path was recreated as a real directory, the
relocated vault root is missing, or the last full scan found executed residual refs.

Bypass: RELOCATE_WATCH_SURFACE_BYPASS=1 in env.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
MANIFEST = CONFIG_DIR / "relocations.json"
CACHE = CONFIG_DIR / "relocate-watch-state.json"
REFRESH_STAMP = CONFIG_DIR / ".relocate-watch-refresh.stamp"
REFRESH_COOLDOWN_S = 20 * 3600  # refresh the heavy scan at most ~once/day
# The watch engine ships alongside this hook: hooks/ and scripts/ are siblings under
# the installed skill dir. Resolve relative to __file__ so it works at any install path.
SWEEP = Path(__file__).resolve().parent.parent / "scripts" / "relocate-sweep.py"


def _quiet() -> int:
    print(json.dumps({"continue": True, "suppressOutput": True}))
    return 0


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _recreated(old: str) -> bool:
    """A REAL directory at the old path (not the post-relocation symlink, not absent)
    means a tool that still hardcodes it mkdir'd a phantom folder."""
    try:
        return os.path.exists(old) and not os.path.islink(old) and os.path.isdir(old)
    except OSError:
        return False


def _refresh_started_at() -> float:
    try:
        return float(REFRESH_STAMP.read_text().strip())
    except (OSError, ValueError):
        return 0.0


def _maybe_spawn_refresh(cache) -> None:
    """Cooldown-gated, single-spawn, DETACHED refresh of the heavy scan. The cooldown is
    claimed AT START (the stamp is written BEFORE the spawn) so a session that starts
    mid-refresh sees the fresh stamp and skips — preventing the N-concurrent-walks
    freeze class. The spawned process writes the cache this hook reads next session."""
    if os.environ.get("RELOCATE_WATCH_SURFACE_NO_REFRESH"):
        return  # test seam: surface from the cache without firing a real background scan
    if not SWEEP.is_file():
        return
    last = max(float((cache or {}).get("ts", 0) or 0), _refresh_started_at())
    if time.time() - last < REFRESH_COOLDOWN_S:
        return  # a recent scan or a recent refresh already covers it
    try:
        REFRESH_STAMP.write_text(str(time.time()))  # claim the cooldown BEFORE spawning
    except OSError:
        return
    try:
        devnull = open(os.devnull, "w")
        subprocess.Popen(
            [sys.executable, str(SWEEP), "--watch", "--config-dir", str(CONFIG_DIR)],
            stdout=devnull, stderr=devnull, stdin=subprocess.DEVNULL, start_new_session=True,
        )
    except Exception:
        pass


def main() -> int:
    if os.environ.get("RELOCATE_WATCH_SURFACE_BYPASS"):
        return _quiet()

    # SessionStart payload arrives on stdin (JSON). Drain so we never block.
    try:
        sys.stdin.read()
    except Exception:
        pass

    # Fail silent on ANY error: a watchdog must never break session start.
    try:
        manifest = _load(MANIFEST)
        if not isinstance(manifest, list) or not manifest:
            return _quiet()  # nothing was ever relocated → nothing to watch
        cache = _load(CACHE)
        cache = cache if isinstance(cache, dict) else None
        recreated = [
            e for e in manifest
            if isinstance(e, dict) and e.get("old") and _recreated(os.path.expanduser(e["old"]))
        ]
        cached_alarm = cache if (cache and cache.get("verdict") == "ALARM") else None
        _maybe_spawn_refresh(cache)
    except Exception:
        return _quiet()

    if not recreated and not cached_alarm:
        return _quiet()

    lines = []
    for e in recreated:
        lines.append(
            f"  - RECREATED: a real directory reappeared at the old vault path "
            f"{e['old']} — a tool that still hardcodes it ran. Repoint it to {e.get('new', '<new>')}."
        )
    if cached_alarm:
        for p in cached_alarm.get("missing_roots") or []:
            lines.append(f"  - VAULT ROOT MISSING: {p} — the relocated vault is not where the manifest says.")
        findings = cached_alarm.get("findings") or []
        for loc in findings[:8]:
            lines.append(f"  - EXECUTED REF still resolves an old path: {loc}")
        extra = (cached_alarm.get("executed", 0) or 0) - min(8, len(findings))
        if extra > 0:
            lines.append(f"  - … and {extra} more executed reference(s).")

    if not lines:
        return _quiet()

    msg = (
        "[relocate-watch] vault-relocation drift detected — a hardcoded OLD vault path "
        "is back (it mkdir's a phantom folder / breaks tooling every run):\n"
        + "\n".join(lines)
        + "\n\nRepoint each reference to the relocated vault, or remove the recreated folder. "
        "Full scan: scripts/relocate-sweep.py --watch (also runs in daily maintenance)."
    )
    print(json.dumps({"systemMessage": msg}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
