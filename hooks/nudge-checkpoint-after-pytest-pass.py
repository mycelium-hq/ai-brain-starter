#!/usr/bin/env python3
"""PostToolUse on Bash: when pytest passes on a module-in-flight, nudge to commit.

Triggers on:
- tool_name == "Bash"
- command contains "pytest" (or "python -m pytest")
- exit code == 0
- the active repo has 3+ untracked source files in a single directory
- AND no commit has landed in the active repo within the last 30 minutes

Emits a strong systemMessage nudge: "your tests passed, your work isn't
committed, here's the exact commit command. Use it now or the next branch
switch can lose the work."

Does NOT auto-commit. The user retains full control over commit shape +
message + branch. The nudge is the forcing function.
"""

from __future__ import annotations

import json
import re
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


PYTEST_RE = re.compile(r"\b(pytest|python(?:3)?\s+-m\s+pytest)\b")


def _emit(message: str | None = None) -> None:
    if message:
        print(json.dumps({"systemMessage": message}))
    else:
        print(json.dumps({}))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        _emit()

    if data.get("tool_name") != "Bash":
        _emit()

    cmd = (data.get("tool_input") or {}).get("command", "") or ""
    if not PYTEST_RE.search(cmd):
        _emit()

    # Tool exit code (PostToolUse provides this)
    response = data.get("tool_response") or {}
    exit_code = response.get("returncode")
    # Fall back: detect "passed" + no "failed" in stdout
    stdout = (response.get("stdout") or "")[:4000]
    if exit_code is None:
        looks_green = (
            "passed" in stdout
            and " failed" not in stdout
            and " error" not in stdout
        )
        if not looks_green:
            _emit()
    elif exit_code != 0:
        _emit()

    repos = find_active_repos()
    if not repos:
        _emit()

    findings = []
    for repo in repos:
        if has_recent_session_commits(repo, minutes=10):
            # User just committed; don't nag
            continue
        findings.extend(find_modules_in_flight(repo))

    if not findings:
        _emit()

    f = findings[0]
    repo = f.repo
    module = f.module_dir
    file_count = f.file_count
    other = len(findings) - 1

    msg_lines = [
        "**[nudge-checkpoint-after-pytest-pass]**",
        "",
        f"Tests passed AND `{repo.name}` has {file_count} untracked source files "
        f"in `{module}` (uncommitted). Best-of-best workflow says "
        "checkpoint-commit NOW, before the next branch switch / stash / pull.",
        "",
        "Suggested commit:",
        "",
        "```bash",
        f"cd {repo}",
        f"git checkout -b feat/<slug>  # if not already on a feature branch",
        f"git add {module}  # plus tests/ paths",
        f"git commit -m 'feat: <module> with passing tests (wip checkpoint)'",
        f"git push -u origin HEAD  # if private repo",
        "```",
    ]
    if other > 0:
        msg_lines.append(
            f"\n(Plus {other} other module(s) in flight — see Stop hook output for full list.)"
        )
    msg_lines += [
        "",
        "Codified 2026-05-10 (CLAUDE.md (see canonical rule)). "
        "Bypass: noop, this is a nudge, not a block.",
    ]
    _emit("\n".join(msg_lines))


if __name__ == "__main__":
    main()
