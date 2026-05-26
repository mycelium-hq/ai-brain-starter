#!/usr/bin/env python3
"""SessionEnd hook: auto-capture public substrate ships to the user's consulting brand Pending Signals.

Scans public repos under ~/dev/* for git commits in the last 24h (user-local-tz day boundary
5:30 AM). Appends one-line bullets per repo to today's Pending Signals/<date>.md.
Idempotent: skips repos already represented in today's file.

Karpathy-dissent safe: public repos only. Personal-data scrub gate prevents leaks.
Private repos (private-memory-repo, private-concierge-repo, private-org/*) NOT touched
because their commit messages can contain client/strategy context — those still
require manual paste per /journal Step 8.7.

Bypass: `AUTO_CAPTURE_SHIPS_BYPASS=1`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VAULT = Path(os.environ.get("VAULT_ROOT", str(Path.home() / "vault")))
PENDING_DIR = VAULT / "🍄 the user's consulting brand" / "📋 Pending Signals"
DEV = Path.home() / "dev"
TZ = ZoneInfo("America/user-local-tz")

PUBLIC_REPOS = [
    "ai-brain-starter",
    "humanizer",
    "mycelium-site",
    "slack-mcp",
    "imessage-mcp",
    "parse-mcp",
    "luma-mcp",
    "graph-query-mcp",
    "github-mcp",
    "whatsapp-mcp",
    "apollo-mcp",
    "google-workspace-mcp",
    "substack-mcp",
    "rescuetime-mcp",
    "investor-relations-mcp",
]


def target_date() -> str:
    now = datetime.now(TZ)
    if now.hour < 5 or (now.hour == 5 and now.minute < 30):
        target = now - timedelta(days=1)
    else:
        target = now
    return target.strftime("%Y-%m-%d")


def window_start() -> datetime:
    td = datetime.strptime(target_date(), "%Y-%m-%d")
    return datetime(td.year, td.month, td.day, 5, 30, tzinfo=TZ)


def commits_today(repo: Path, since: datetime) -> list[str]:
    if not (repo / ".git").exists():
        return []
    iso = since.strftime("%Y-%m-%d %H:%M:%S %z")
    try:
        out = subprocess.run(
            ["git", "log", f"--since={iso}", "--pretty=format:%s", "--no-merges"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return [s for s in out.stdout.splitlines() if s.strip()]
    except (subprocess.TimeoutExpired, OSError):
        return []


def existing_repos(file: Path) -> set[str]:
    if not file.exists():
        return set()
    text = file.read_text()
    return {r for r in PUBLIC_REPOS if f"`{r}`" in text}


def append_bullets(bullets: list[str]) -> None:
    if not bullets:
        return
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    file = PENDING_DIR / f"{target_date()}.md"
    if not file.exists():
        file.write_text(
            f"---\ntype: pending-signals\nworkspace: mycelium\ncreated: {target_date()}\n---\n\n"
        )
    text = file.read_text().rstrip() + "\n\n" + "\n\n".join(bullets) + "\n"
    file.write_text(text)


def main() -> int:
    if os.environ.get("AUTO_CAPTURE_SHIPS_BYPASS") == "1":
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return 0

    file = PENDING_DIR / f"{target_date()}.md"
    seen = existing_repos(file)
    since = window_start()
    captured_at = datetime.now(TZ).strftime("%H:%M")
    bullets = []

    for name in PUBLIC_REPOS:
        if name in seen:
            continue
        repo_path = DEV / name
        commits = commits_today(repo_path, since)
        if not commits:
            continue
        body = "; ".join(c.replace("`", "'") for c in commits[:6])
        if len(commits) > 6:
            body += f"; +{len(commits) - 6} more"
        bullets.append(
            f"- `{name}` shipped today ({len(commits)} commits): {body}. "
            f"— source: `~/dev/{name}` git log · captured: {captured_at} (auto)"
        )

    append_bullets(bullets)
    print(json.dumps({"continue": True, "suppressOutput": True, "captured": len(bullets)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
