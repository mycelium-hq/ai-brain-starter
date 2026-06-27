#!/usr/bin/env python3
"""SessionStart hook (MYC-1893): surface bare ~/dev hubs that need a human.

CHEAP by construction — reads the state file the launchd `dev-hub-refresh --apply`
job writes (NO git, NO fetch on the interactive path). The launchd leg owns the
expensive fetch + fast-forward; this leg is the human-visible backstop that says
"these hubs are far behind / dirty / off-branch — the auto-ff couldn't touch them".

Stays SILENT unless something genuinely needs attention (surfaced hub, or a hub
>= THRESHOLD commits behind — a sign the launchd refresh has stalled). Fail-open:
a missing / garbled state file prints nothing (a fresh install seeds it at login;
daemon-liveness is surface-stale-automation-failures.py's job, not this hook's).

Bug class: STALE-BARE-CHECKOUT-READ (MYC-670 / MYC-1127 / MYC-1893).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

STATE_PATH = Path(
    os.environ.get("DEV_HUB_REFRESH_STATE")
    or (Path.home() / ".claude" / ".dev-hub-refresh-state.json")
)
THRESHOLD = 50  # a hub >= this many commits behind is "loud" even though it is auto-fixable

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _lib.dev_repo_scan import format_hub_surface_line
except Exception:
    print(json.dumps({}))
    sys.exit(0)


def _emit(message: str | None = None) -> None:
    if message:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": message,
            }
        }))
    else:
        print(json.dumps({}))
    sys.exit(0)


def main() -> None:
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    try:
        data = json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        _emit()  # no state yet (fresh install / launchd not run) → silent

    summary = data.get("summary") if isinstance(data, dict) else None
    if not isinstance(summary, dict):
        _emit()

    _emit(format_hub_surface_line(summary, threshold=THRESHOLD))


if __name__ == "__main__":
    main()
