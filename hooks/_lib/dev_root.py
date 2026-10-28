"""Where this install keeps its code repos: $ABS_DEV_ROOT, else `dev_root` in
~/.claude/dev-hygiene.json, else ~/dev.

Stdlib only, so a hook that runs on every tool call can ask without paying for
dev_repo_scan's imports. dev_repo_scan.resolve_dev_root() delegates here, so
there is one rule. Fail-open: a missing or malformed config means the default.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def resolve_dev_root(config_path: Path | None = None) -> Path:
    env = os.environ.get("ABS_DEV_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    path = config_path or Path.home() / ".claude" / "dev-hygiene.json"
    try:
        configured = json.loads(path.read_text(encoding="utf-8")).get("dev_root")
        if isinstance(configured, str) and configured.strip():
            return Path(configured).expanduser()
    except (OSError, ValueError, AttributeError, RuntimeError):  # absent, malformed, ~nobody
        pass
    return Path.home() / "dev"
