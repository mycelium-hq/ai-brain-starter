#!/usr/bin/env python3
"""check-cd-outside-worktree.py

PreToolUse(Bash) hook. When the session is rooted in a git worktree
(`<repo>/.claude/worktrees/<slug>/...`), block any `cd` / `pushd` whose
resolved target lands in the MAIN checkout tree but OUTSIDE the worktrees
subtree.

Why: CONCURRENT-SESSION-HEAD-DRIFT. A worktree has its own HEAD; the main
checkout has a different HEAD shared with every other main-checkout session.
`cd` into the main checkout from a worktree-spawned session, then a commit /
branch op lands on whatever branch the MAIN checkout (or a parallel session)
currently points at — not the worktree's `claude/<slug>` branch. Observed
repeatedly in long multi-session workflows (a ~30-minute reflog rescue in one
real incident) despite a codified worktree-isolation rule. The rule existed; the
enforcement layer did not. This is that layer.

Detection:
  - cwd (from payload) matches `<main>/.claude/worktrees/<slug>` → worktree
    session; `<main>` is the shared main checkout.
  - Each `cd`/`pushd` target in the command is resolved against cwd
    (absolute targets ignore cwd; relative `..` climbs resolve too).
  - Block if the resolved target is `<main>` itself OR under `<main>/` but NOT
    under `<main>/.claude/worktrees/` (staying anywhere inside the worktrees
    subtree is fine; that's still HEAD-isolated).

Recommended instead: stay in the worktree, or use `git -C <path> ...` for
read-only queries against the main checkout (no cwd change, no drift).

Known gaps (documented, low-incidence): `cd` nested inside `bash -c "..."` or
other quoting layers is not parsed; env-var targets beyond `~`/`$HOME` are not
expanded. The real-world incident that motivated this was a bare absolute
`cd`, which this catches.

Bypass: `WORKTREE_CD_BYPASS=1` (document why — e.g. a deliberate one-off
read-only op in the main checkout).
"""

from __future__ import annotations

import json
import os
import re
import sys

WORKTREE_RE = re.compile(r"^(?P<main>.+?)/\.claude/worktrees/(?P<slug>[^/]+)(?:/|$)")

# Split a command into sequential segments on shell separators so each `cd`
# is evaluated in order (mirrors how the shell would run them).
SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;\n|]")
CD_RE = re.compile(r"^(?:cd|pushd)\s+(?P<arg>.+)$")


def _first_token(arg: str) -> str:
    """First shell word of a cd argument, respecting simple quoting."""
    arg = arg.strip()
    if not arg:
        return ""
    if arg[0] in ("'", '"'):
        q = arg[0]
        end = arg.find(q, 1)
        return arg[1:end] if end != -1 else arg[1:]
    # unquoted: up to first whitespace
    return arg.split()[0]


def _expand(path: str) -> str:
    if path == "~" or path.startswith("~/"):
        path = os.path.expanduser(path)
    elif path.startswith("$HOME"):
        path = os.environ.get("HOME", os.path.expanduser("~")) + path[len("$HOME"):]
    return path


def main() -> int:
    if os.environ.get("WORKTREE_CD_BYPASS") == "1":
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    m = WORKTREE_RE.match(cwd)
    if not m:
        return 0  # not a worktree-rooted session

    main_root = os.path.normpath(m.group("main"))
    slug = m.group("slug")
    worktrees_prefix = main_root + "/.claude/worktrees/"

    command = (payload.get("tool_input", {}) or {}).get("command", "") or ""
    if not command.strip():
        return 0

    for seg in SEGMENT_SPLIT_RE.split(command):
        seg = seg.strip()
        cm = CD_RE.match(seg)
        if not cm:
            continue
        target = _first_token(cm.group("arg"))
        if not target:
            continue
        target = _expand(target)
        # resolve relative targets against the session cwd; absolute targets
        # make os.path.join ignore cwd.
        resolved = os.path.normpath(os.path.join(cwd, target))

        in_main_tree = resolved == main_root or resolved.startswith(main_root + "/")
        in_worktrees = resolved.startswith(worktrees_prefix)
        if in_main_tree and not in_worktrees:
            sys.stderr.write(
                "BLOCKED: this session is rooted in a git worktree\n"
                f"  {cwd}\n"
                f"but the command `cd`s into the MAIN checkout:\n"
                f"  {resolved}\n\n"
                "The main checkout shares one .git/HEAD with every other "
                "main-checkout session. A commit or branch op after this cd "
                "lands on the wrong branch (CONCURRENT-SESSION-HEAD-DRIFT — "
                "a ~30-minute reflog rescue in a real multi-session "
                "incident).\n\n"
                "Do instead:\n"
                f"  - stay in the worktree ({slug}); or\n"
                "  - use `git -C <path> <cmd>` for read-only queries against "
                "the main checkout (no cwd change, no drift).\n\n"
                "Bypass (document why): WORKTREE_CD_BYPASS=1\n"
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
