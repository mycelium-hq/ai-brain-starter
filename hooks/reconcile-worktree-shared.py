#!/usr/bin/env python3
"""SessionEnd hook: reconcile worktree's shared-canonical files against main vault.

Wire into ~/.claude/settings.json SessionEnd hooks so it runs every session close.

Problem this fixes:
- When you use git worktrees inside an Obsidian vault and have a PreToolUse
  guard that routes "shared-canonical" file edits (e.g. .claude/hookify.*.local.md)
  to MAIN VAULT path, the worktree's filesystem copy gets synced (via cp / auto-
  commit hooks) but the worktree's GIT INDEX never gets updated.
- Result: `git status` in the worktree shows `M` / `??` for files that are
  already preserved at main vault. Worktree-archive UI fires "N uncommitted
  changes will be discarded" warnings on every session close.
- The warning is a false positive but trains the eye to ignore it, which would
  mask a real loss the day a worktree edit ISN'T also at main.

This hook handles each identical-to-main shared-canonical file two ways:
- git knows it (tracked on the branch, or committed on master/main): stage it;
  a fast-forward merge reconciles it onto the worktree branch with no orphan
  commit.
- no git ref knows it (a genuine orphan duplicate): prune the worktree copy --
  the real content already lives at main vault, so this is a zero-data-loss
  cleanup of a false `??`.
Real divergences are surfaced for human review and left alone.

CONFIG (per user, once):
1. Set VAULT_ROOT below to your vault root, OR rely on auto-detect (walks up
   from cwd looking for the .claude/worktrees/ pattern).
2. Edit SHARED_PATTERNS to match your worktree-discipline rules.
3. Wire into ~/.claude/settings.json BOTH SessionEnd AND Stop hooks. SessionEnd
   alone leaves a race window between when the hook fires and when the
   worktree-archive prompt runs (other committers, like hookify-auto-commit
   or auto-snapshot, can land commits on master in between). Stop fires after
   every assistant turn and closes that window:
     "SessionEnd": [
       {"matcher": "", "hooks": [{
         "type": "command",
         "command": "python3 ~/.claude/hooks/reconcile-worktree-shared.py 2>/dev/null || echo '{\"continue\":true,\"suppressOutput\":true}'"
       }]}
     ],
     "Stop": [
       {"hooks": [{
         "type": "command",
         "command": "python3 ~/.claude/hooks/reconcile-worktree-shared.py 2>/dev/null || echo '{\"continue\":true,\"suppressOutput\":true}'"
       }]}
     ]

4. (Optional, recommended) For zero-window race closure, have your commit
   wrappers call scripts/post-commit-ff-worktrees.sh after each successful
   commit on main. The helper enumerates active claude/* worktree branches
   and FFs them to master, so an upcoming archive prompt never sees the
   stale state in the first place.

BYPASS: WORKTREE_RECONCILE_BYPASS=1
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Glob patterns of shared-canonical files (relative to worktree root).
# Add patterns matching your own worktree-edit-discipline rules.
SHARED_PATTERNS = [
    ".claude/hookify.*.local.md",
    # Common candidates to add as the same false-warning surfaces:
    # "⚙️ Meta/rules/*.md",
    # "scripts/*.py",
    # "scripts/*.sh",
    # ".mcp.json",
    # "CLAUDE.md",
]


def find_main_vault(cwd: Path) -> Path | None:
    """Walk up cwd looking for the parent that contains .claude/worktrees/<this-slug>/.

    Returns the parent (i.e. the main vault root). Returns None if not in a worktree.
    """
    parts = cwd.parts
    try:
        idx = parts.index(".claude")
    except ValueError:
        return None
    if len(parts) <= idx + 1 or parts[idx + 1] != "worktrees":
        return None
    return Path(*parts[:idx])


def worktree_root(cwd: Path) -> Path | None:
    """Return the worktree root (.../.claude/worktrees/<slug>/), or None."""
    parts = cwd.parts
    try:
        idx = parts.index(".claude")
        if len(parts) > idx + 2 and parts[idx + 1] == "worktrees":
            return Path(*parts[: idx + 3])
    except ValueError:
        pass
    return None


def files_identical(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except (OSError, UnicodeDecodeError):
        return False


def reconcilable_via_git(wt: Path, rel_path: str) -> bool:
    """True if git can reconcile this file via stage + fast-forward.

    True when the file is tracked on the worktree branch, OR committed on
    master/main (a later FF-merge restores it as tracked + clean). False only
    when no git ref knows the file at all -- a genuine orphan duplicate that
    FF cannot clean, so it must be pruned instead.
    """
    # Tracked on the current (worktree) branch?
    if subprocess.run(
        ["git", "-C", str(wt), "ls-files", "--error-unmatch", "--", rel_path],
        capture_output=True,
    ).returncode == 0:
        return True
    # Committed on master/main? An FF-merge will restore + track it.
    for branch in ("master", "main"):
        if subprocess.run(
            ["git", "-C", str(wt), "cat-file", "-e", f"{branch}:{rel_path}"],
            capture_output=True,
        ).returncode == 0:
            return True
    return False


def main() -> None:
    if os.environ.get("WORKTREE_RECONCILE_BYPASS"):
        return

    try:
        sys.stdin.read()
    except Exception:
        pass

    cwd = Path.cwd()
    main_vault = find_main_vault(cwd)
    wt = worktree_root(cwd)

    if main_vault is None or wt is None:
        return  # Not in a worktree, nothing to reconcile

    reconciled: list[str] = []
    divergent: list[str] = []
    pruned: list[str] = []

    for pattern in SHARED_PATTERNS:
        for wt_file in wt.glob(pattern):
            rel = wt_file.relative_to(wt)
            main_file = main_vault / rel
            if not main_file.exists():
                # No main copy: genuine worktree-only content. Leave alone --
                # the real stranding case; needs human review.
                continue
            if not files_identical(wt_file, main_file):
                divergent.append(str(rel))
                continue
            # Identical to the main vault copy. Two sub-cases:
            if reconcilable_via_git(wt, str(rel)):
                # git knows this file (tracked on the branch, or committed on
                # master/main). Stage it; the FF/commit step below makes it
                # clean by advancing the branch to a tip that contains it.
                res = subprocess.run(
                    ["git", "-C", str(wt), "add", "--", str(rel)],
                    capture_output=True,
                )
                if res.returncode == 0:
                    reconciled.append(str(rel))
            else:
                # No git ref knows this file -> a genuine orphan duplicate
                # (created this session, written to main, not yet committed
                # anywhere). FF cannot clean it and `git add` would only turn
                # a `??` into a staged `A` that still trips the archive
                # warning. The content is safe at the main vault (main_file
                # exists + verified identical) and the worktree is a throwaway
                # checkout, so delete the worktree copy. Zero data loss.
                try:
                    wt_file.unlink()
                    pruned.append(str(rel))
                except OSError:
                    pass

    # Report prunes + real divergences regardless of whether any tracked file
    # needs an FF/commit reconcile below.
    if pruned:
        print(json.dumps({
            "systemMessage": (
                f"[reconcile-worktree-shared] pruned {len(pruned)} redundant "
                f"untracked duplicate(s) from the worktree -- byte-identical to "
                f"main vault, which keeps its copy (zero data loss): "
                f"{', '.join(pruned[:5])}"
            )
        }))
    if divergent:
        print(json.dumps({
            "systemMessage": (
                f"[reconcile-worktree-shared] {len(divergent)} shared-canonical "
                f"file(s) DIVERGE from main vault: {', '.join(divergent[:5])}"
            )
        }), file=sys.stderr)

    if not reconciled:
        return

    # PRIMARY PATH: fast-forward the worktree branch to the main branch tip.
    # If the worktree branch is a strict ancestor of master/main (the normal
    # case — worktrees are created from master HEAD and don't accumulate
    # their own commits when hooks route writes to main), FF-merge advances
    # the worktree branch pointer without creating any new commit. The
    # "modified" files become "clean" naturally because HEAD now matches
    # the working tree byte-for-byte. No orphan commit ever appears on
    # `claude/<slug>`.
    #
    # FALLBACK: if FF fails (worktree branch diverged from main — a real
    # session-end-hook commit landed there, or the user committed manually),
    # fall back to the prior auto-commit behavior so the archive prompt
    # still sees a clean state. This is the rare case and is exactly what
    # generates orphans, but we prefer one orphan now to repeatedly warning
    # about uncommitted bytes that already live on main.
    main_branch = "master"
    has_master = subprocess.run(
        ["git", "-C", str(wt), "show-ref", "--verify", "--quiet", "refs/heads/master"],
    ).returncode == 0
    if not has_master:
        # Repo uses "main" as default branch
        main_branch = "main"

    ff_result = subprocess.run(
        ["git", "-C", str(wt), "merge", "--ff-only", "--no-edit", main_branch],
        capture_output=True,
        text=True,
    )

    if ff_result.returncode == 0:
        # FF succeeded: worktree branch now points at main's tip. Files that
        # were "modified vs HEAD" are now "clean" because HEAD has the new
        # content. No commit was created. Issue #65-family orphan-commit
        # accumulation prevented.
        print(json.dumps({
            "systemMessage": (
                f"[reconcile-worktree-shared] fast-forwarded worktree branch "
                f"to {main_branch} ({len(reconciled)} file(s) reconciled with "
                f"no orphan commit)."
            )
        }))
    else:
        # FF failed: worktree branch has diverged from main (real session
        # commits or manual work landed there). Fall back to auto-commit
        # on the worktree branch so the archive prompt still sees clean
        # state. This is the rare path.
        msg = (
            f"auto: reconcile-worktree-shared synced {len(reconciled)} "
            f"shared-canonical file(s) to match main vault (FF to "
            f"{main_branch} not possible — branch diverged)\n\n"
            + "\n".join(f"- {f}" for f in reconciled)
        )
        commit_result = subprocess.run(
            ["git", "-C", str(wt), "commit", "-m", msg, "--quiet"],
            capture_output=True,
        )
        if commit_result.returncode == 0:
            print(json.dumps({
                "systemMessage": (
                    f"[reconcile-worktree-shared] FF to {main_branch} not "
                    f"possible; committed {len(reconciled)} file(s) on "
                    f"worktree branch instead. Branch will need recovery "
                    f"via scripts/recover-orphan-claude-branches.py."
                )
            }))


if __name__ == "__main__":
    main()
