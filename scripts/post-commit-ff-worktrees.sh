#!/usr/bin/env bash
# post-commit-ff-worktrees.sh - fast-forward active claude/* worktree branches
# to the main branch tip after a commit lands on main.
#
# Purpose:
# Closes the commit-time race between (a) any committer that lands a commit on
# master/main and (b) the reconcile-worktree-shared.py SessionEnd hook. Without
# this, every commit on main leaves active worktree branches stale, surfacing
# as false-positive "N uncommitted changes will be discarded" warnings at the
# worktree-archive prompt - even when the worktree's filesystem is byte-
# identical to main.
#
# Usage (call AFTER a successful commit on main):
#   bash /path/to/post-commit-ff-worktrees.sh /path/to/main/vault
#
# Argument: the absolute path to the main vault (= the repo root). The script
# enumerates worktrees from this repo and FFs each claude/* branch to the main
# branch tip. The main vault itself is never touched.
#
# Behavior:
# - Detects master vs main automatically (master first, falls back to main).
# - Iterates `git worktree list --porcelain` line-by-line via bash `case`,
#   never `awk $2`. AWK's default field split breaks at the first space in a
#   worktree path with spaces (e.g. paths containing words like "My Notes")
#   and silently truncates every path. Bash `case` matches the literal
#   "worktree " prefix and strips it without splitting.
# - For each worktree on a claude/* branch (NOT the main vault itself):
#   try `git merge --ff-only --no-edit <main_branch>`.
# - Silent on success (FF advances branch pointer with no new commit).
# - Silent on FF failure (worktree branch genuinely diverged - that's the
#   reconcile-on-SessionEnd fallback's job, not ours).
#
# Bypass: POST_COMMIT_FF_BYPASS=1

set -euo pipefail

if [ "${POST_COMMIT_FF_BYPASS:-0}" = "1" ]; then
    exit 0
fi

MAIN_VAULT="${1:-}"
if [ -z "$MAIN_VAULT" ]; then
    echo "usage: post-commit-ff-worktrees.sh <main-vault-path>" >&2
    exit 2
fi

if [ ! -d "$MAIN_VAULT/.git" ] && [ ! -f "$MAIN_VAULT/.git" ]; then
    echo "post-commit-ff-worktrees: $MAIN_VAULT is not a git repo root" >&2
    exit 0
fi

# Detect the main branch name (master vs main). Match the same logic used
# in reconcile-worktree-shared.py.
MAIN_BRANCH="master"
if ! git -C "$MAIN_VAULT" show-ref --verify --quiet refs/heads/master; then
    MAIN_BRANCH="main"
fi

current_wt=""
git -C "$MAIN_VAULT" worktree list --porcelain 2>/dev/null \
    | while IFS= read -r line; do
        case "$line" in
            "worktree "*)
                current_wt="${line#worktree }"
                ;;
            "branch refs/heads/claude/"*)
                if [ -n "$current_wt" ] && [ "$current_wt" != "$MAIN_VAULT" ]; then
                    git -C "$current_wt" merge --ff-only --no-edit "$MAIN_BRANCH" \
                        >/dev/null 2>&1 || true
                fi
                current_wt=""
                ;;
            "")
                current_wt=""
                ;;
        esac
    done
