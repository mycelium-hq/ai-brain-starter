#!/usr/bin/env python3
"""block-worktree-shared-edit.py

PreToolUse hook for Edit / Write / MultiEdit. Blocks edits to shared-canonical
vault files when the path points at a worktree copy instead of the main vault.

Failure mode this prevents: editing files at
`<vault>/.claude/worktrees/<slug>/⚙️ Meta/<file>.md` silently diverges from
master because vault-safe-commit.sh runs from main vault root and stages the
main-vault copy of the same path. Two physically separate files; the worktree
edit is committed only if commit happens from inside the worktree, which the
session-close protocol does not do.

Codified 2026-05-08 after the slack-mcp build session where my Run 7 entry
on MCP Build Runbook landed only in the worktree copy. Discovered at archive
time by Claude Code's "uncommitted changes" prompt. Resolved by manually
applying the entry to main vault and committing as Run 11.

Extended 2026-05-17: also blocks session artifacts (Sessions/, Decisions/,
Handoffs/, Pending Team Broadcasts/, Session Captures.md, Time Tracking.md)
at worktree paths, reversing the prior WORKTREE_OK allow-list. Those strand
on the throwaway claude/<slug> branch and are discarded when the worktree is
archived. Resolves the contradiction with CLAUDE.md (see canonical rule).

Extended 2026-06-03: same block on the vault's automation log dir,
`<vault>/⚙️ Meta/logs/*.{log,err}`. Each name has exactly one canonical
writer (worktree-prune, enforce-worktree-cap, remove-ended-worktree,
session-end-hook, auto-snapshot, decision-outcome-check, traffic-snapshot).
A worktree-path write to one of these is either a script computing its log
path against SCRIPT_DIR (and so anchored at the worktree copy of itself) or
an LLM hand-writing a line at the wrong root; both lose data when the
worktree archives. Bug class:
WORKTREE-CWD-RELATIVE-LOG-PATH-STRANDS-DATA.

Bypass: `WORKTREE_VAULT_EDIT_BYPASS=1` (rare; document why).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

VAULT_ROOT = os.environ.get("VAULT_ROOT", str(Path.home() / "vault"))

# Match worktree paths: <vault>/.claude/worktrees/<slug>/<rest>
WORKTREE_RE = re.compile(
    r"^" + re.escape(VAULT_ROOT) + r"/\.claude/worktrees/([^/]+)/(.+)$"
)

# Files where worktree-path edits silently diverge from master.
# Editing these MUST happen at main vault path so vault-safe-commit picks them up.
SHARED_PATTERNS = [
    re.compile(r"^⚙️ Meta/rules/.+\.md$"),
    re.compile(r"^⚙️ Meta/MCP Build Runbook\.md$"),
    re.compile(r"^⚙️ Meta/Build Standards\.md$"),
    re.compile(r"^⚙️ Meta/Graphify .+\.md$"),
    re.compile(r"^⚙️ Meta/Critical Failure Inventory\.md$"),
    re.compile(r"^⚙️ Meta/scripts/.+\.(py|sh)$"),
    re.compile(r"^\.claude/hookify\..+\.local\.md$"),
    re.compile(r"^\.mcp\.json$"),
    re.compile(r"^CLAUDE\.md$"),
]

# Session artifacts. Writing these at a worktree path strands them on the
# throwaway claude/<slug> branch, which is discarded when the worktree is
# archived (incident 2026-05-17). They MUST go to the main vault. The close
# cascade resolves them there automatically (resolve_main_vault in
# detect-closing-signal.py); this list is the belt-and-suspenders guard and
# reverses the prior WORKTREE_OK allow-list, which permitted exactly what
# CLAUDE.md (see canonical rule) forbids.
SESSION_ARTIFACT_PATTERNS = [
    re.compile(r"^⚙️ Meta/Sessions/.+\.md$"),
    re.compile(r"^⚙️ Meta/Decisions/.+\.md$"),
    re.compile(r"^⚙️ Meta/Handoffs/.+\.md$"),
    re.compile(r"^⚙️ Meta/Pending Team Broadcasts/.+\.md$"),
    re.compile(r"^⚙️ Meta/Session Captures\.md$"),
    re.compile(r"^⚙️ Meta/Time Tracking\.md$"),
]

# Vault automation logs. Each filename has exactly one canonical writer; a
# worktree-side write is always either a SCRIPT_DIR-relative path bug or an
# LLM hand-writing at the wrong root. In both cases the entries strand on
# the claude/<slug> branch and are discarded at archive. Match `*.log` and
# `*.err` under the canonical logs directory.
LOG_PATH_PATTERNS = [
    re.compile(r"^⚙️ Meta/logs/.+\.(log|err)$"),
]


def main() -> int:
    if os.environ.get("WORKTREE_VAULT_EDIT_BYPASS") == "1":
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in ("Edit", "Write", "MultiEdit"):
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return 0

    m = WORKTREE_RE.match(file_path)
    if not m:
        return 0

    slug, rel = m.groups()

    for pat in SESSION_ARTIFACT_PATTERNS:
        if pat.match(rel):
            main_path = f"{VAULT_ROOT}/{rel}"
            print(
                f"BLOCKED: '{rel}' is a session artifact. Writing it at a "
                f"worktree path strands it on the claude/{slug} branch and it "
                f"is discarded when the worktree is archived. Session artifacts "
                f"MUST be written to the main vault:\n"
                f"  {main_path}\n"
                f"The close cascade resolves these automatically "
                f"(resolve_main_vault in detect-closing-signal.py); this guard "
                f"catches a hand-written or stale-hook worktree path.\n"
                f"Bypass: WORKTREE_VAULT_EDIT_BYPASS=1 (document why).",
                file=sys.stderr,
            )
            return 2

    for pat in SHARED_PATTERNS:
        if pat.match(rel):
            main_path = f"{VAULT_ROOT}/{rel}"
            print(
                f"BLOCKED: '{rel}' is a shared-canonical vault file. "
                f"Editing at worktree path silently diverges from master "
                f"because vault-safe-commit stages from main vault root.\n"
                f"Edit at the main vault path instead:\n"
                f"  {main_path}\n"
                f"Worktree slug: {slug}\n"
                f"Bypass: WORKTREE_VAULT_EDIT_BYPASS=1 (document why).",
                file=sys.stderr,
            )
            return 2

    for pat in LOG_PATH_PATTERNS:
        if pat.match(rel):
            main_path = f"{VAULT_ROOT}/{rel}"
            print(
                f"BLOCKED: '{rel}' is a vault automation log. Writes belong "
                f"at the main vault path so the canonical log accumulates "
                f"all entries; a worktree-side write strands the entries on "
                f"the claude/{slug} branch and they are discarded at "
                f"worktree archive.\n"
                f"Write at the main vault path instead:\n"
                f"  {main_path}\n"
                f"If a script computed this path against SCRIPT_DIR, source "
                f"scripts/_resolve_main_vault.sh and pass the path through "
                f"resolve_main_vault before anchoring LOG_DIR.\n"
                f"Bypass: WORKTREE_VAULT_EDIT_BYPASS=1 (document why).",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
