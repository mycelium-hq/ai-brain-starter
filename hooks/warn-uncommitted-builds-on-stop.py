#!/usr/bin/env python3
"""Stop hook: scan ~/dev/* for uncommitted module-in-flight work, surface it loudly.

Stop hook fires when Claude wants to end the turn. Cannot block reliably,
but emits a systemMessage that the next user prompt sees, so even if the
session is closed, the warning is durable in the transcript.

Pairs with:
- block-branch-switch-with-untracked-build.py (preventive)
- nudge-checkpoint-after-pytest-pass.py (in-flight reminder)
- list-wip-stashes-on-session-start.py (recovery surface)

Together they form a four-layer defense against the
2026-05-09 voice-module near-loss pattern.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from _lib.dev_repo_scan import (  # type: ignore
        find_active_repos,
        find_modules_in_flight,
        has_recent_session_commits,
    )
except Exception:
    print(json.dumps({}))
    sys.exit(0)


def _emit(message: str | None = None) -> None:
    if message:
        print(json.dumps({"systemMessage": message}))
    else:
        print(json.dumps({}))
    sys.exit(0)


def main() -> None:
    try:
        # Stop hook input shape; we ignore the body for this scan
        json.load(sys.stdin)
    except Exception:
        pass

    repos = find_active_repos()
    if not repos:
        _emit()

    findings = []
    for repo in repos:
        if has_recent_session_commits(repo, minutes=5):
            continue
        findings.extend(find_modules_in_flight(repo))

    if not findings:
        _emit()

    lines = [
        "**[warn-uncommitted-builds-on-stop]**",
        "",
        f"Closing this turn with {len(findings)} module(s)-in-flight "
        f"uncommitted in ~/dev/* repos. The next branch switch, stash, "
        f"or pull from another session can silently lose this work — only "
        f"`__pycache__` artifacts may survive.",
        "",
        "Found:",
    ]
    for f in findings[:5]:
        lines.append(
            f"- `{f.repo.name}` :: `{f.module_dir}` "
            f"({f.file_count} untracked source files)"
        )
        for p in f.files[:4]:
            lines.append(f"    - {p}")
        if f.file_count > 4:
            lines.append(f"    - ... and {f.file_count - 4} more")
    if len(findings) > 5:
        lines.append(f"- ... and {len(findings) - 5} more module(s)")

    lines += [
        "",
        "**Commit before close** (best-of-best workflow):",
        "",
        "```bash",
        "cd <repo> && git checkout -b feat/<slug>",
        "git add <explicit paths>  # never -A in vault contexts",
        "git commit -m 'feat: ...'",
        "git push -u origin HEAD  # if private + remote",
        "```",
        "",
        "Or stash WITH untracked files (default `git stash` strips them):",
        "",
        "```bash",
        "cd <repo> && git stash push -u -m 'wip: <slug>'",
        "```",
        "",
        "Permanent-fix-pattern guard. See `⚙️ Meta/rules/branch-switch-safety.md`.",
    ]

    _emit("\n".join(lines))


if __name__ == "__main__":
    main()
