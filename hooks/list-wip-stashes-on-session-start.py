#!/usr/bin/env python3
"""SessionStart hook: surface WIP / parking stashes from prior sessions.

Without this surfacing, a stashed-and-orphaned build (the 2026-05-09
voice-module pattern) is invisible until somebody runs `git stash list`
manually. Surfacing on every session start makes the loss recoverable
within minutes instead of hours.

Pairs with the other three hooks in the branch-switch-safety pack.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from _lib.dev_repo_scan import (  # type: ignore
        find_active_repos,
        find_wip_stashes,
    )
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

    repos = find_active_repos()
    if not repos:
        _emit()

    findings = []
    for repo in repos:
        findings.extend(find_wip_stashes(repo))

    if not findings:
        _emit()

    lines = [
        "[wip-stash-surface]",
        "",
        f"Found {len(findings)} WIP/parking stash(es) across active "
        f"~/dev/* repos. Recover before starting fresh work in those "
        f"repos OR drop the stash explicitly if the work is obsolete.",
        "",
    ]
    for s in findings[:8]:
        lines.append(
            f"- `{s.repo.name}` :: `{s.stash_ref}` on `{s.branch}` — "
            f"{s.message[:120]}"
        )
    if len(findings) > 8:
        lines.append(f"- ... and {len(findings) - 8} more")

    lines += [
        "",
        "Recover (use `git stash apply` to keep the stash, `pop` to drop it):",
        "",
        "```bash",
        "cd <repo>",
        "git stash show -u <stash_ref> --stat   # inspect first",
        "git stash apply <stash_ref>            # restore + KEEP stash",
        "# or",
        "git stash drop <stash_ref>             # delete if obsolete",
        "```",
        "",
        "Codified 2026-05-10 (branch-switch-safety pack).",
    ]

    _emit("\n".join(lines))


if __name__ == "__main__":
    main()
