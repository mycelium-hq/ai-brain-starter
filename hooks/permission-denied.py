#!/usr/bin/env python3
"""PermissionDenied hook: append JSON line to log for permission-prompt analysis.

Fires on AUTO-MODE denials only (not manual denies). Cannot reverse the denial.
We do NOT set retry:true — denial stands, we just capture data for later review
of which tool calls keep getting auto-denied so you can refine settings.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

LOG = Path.home() / ".claude" / "hooks" / "permission-denied.log"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": payload.get("tool_name"),
        "input": payload.get("tool_input"),
        "reason": payload.get("reason"),
        "cwd": payload.get("cwd"),
    }
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
