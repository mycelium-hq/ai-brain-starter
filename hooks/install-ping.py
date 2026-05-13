#!/usr/bin/env python3
"""One-time install signal to myceliumai.co.

Idempotent (one sentinel per plugin per machine), silent, fire-and-forget.
Sends ONLY plugin name + version. No PII, no IP storage post-dedup.

Opt out by setting environment variable MYCELIUM_NO_PING=1 before launching
Claude Code. See README "Telemetry" section for details.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

PLUGIN_NAME = "ai-brain-starter"
VERSION = "1.3.1"


def main():
    # Opt-out via env var
    if os.environ.get("MYCELIUM_NO_PING"):
        return 0
    sentinel_dir = Path.home() / ".mycelium"
    sentinel = sentinel_dir / f"onboarded-{PLUGIN_NAME}"
    if sentinel.exists():
        return 0
    try:
        sentinel_dir.mkdir(exist_ok=True)
        sentinel.touch()
    except Exception:
        return 0
    try:
        data = json.dumps({"plugin": PLUGIN_NAME, "version": VERSION}).encode()
        req = urllib.request.Request(
            "https://myceliumai.co/api/install",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
