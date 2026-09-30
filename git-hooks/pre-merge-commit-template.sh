#!/usr/bin/env bash
# pre-merge-commit-template.sh
#
# Chains the session-artifact strand guard onto git's pre-merge-commit hook.
#
# WHY A SEPARATE FILE: pre-commit-template.sh (this directory) already chains
# the same guard onto `pre-commit`, but git dispatches hooks by EXACT FILENAME
# under core.hooksPath, and `pre-commit` never fires for a conflict-free,
# non-fast-forward `git merge` that git can commit on its own -- that merge
# fires `pre-merge-commit` instead (githooks(5)). Without this file, a
# conflict-free `git merge topic` silently strands topic's own session
# artifacts on the current branch with NO guard running at all (this is what
# the guard's own header calls the SESSIONCLOSE-COMMITS-TO-CURRENT-BRANCH-NOT-
# MAIN class; a plain `git merge origin/main` was never the risk -- a plain
# `git merge <topic-with-its-own-artifacts>` was).
#
# What still works here, and what does not:
#   - The origin/<default> exemption route inside the guard does not read
#     MERGE_HEAD at all, so it is unaffected and still exempts content already
#     on origin/<default>.
#   - The MERGE_HEAD exemption route is INACTIVE at this hook. Measured
#     2026-09-25 against git 2.50.1: `.git/MERGE_HEAD` does not exist yet when
#     pre-merge-commit runs (the hook fires before write_merge_state()), so
#     `git rev-parse --verify MERGE_HEAD` fails and the guard's existing
#     "unresolvable ref grants nothing" fail-closed path takes over on its
#     own -- no guard code change was needed for this hook to be safe. Net
#     effect: a plain `git merge <local-branch-ahead-of-origin>` that carries
#     ONLY content already on that local branch (and not yet on
#     origin/<default>) is refused here, where it would previously have gone
#     through the MERGE_HEAD route via a manual `git merge --no-commit` +
#     `git commit` (pre-commit, where MERGE_HEAD IS written by then) --
#     that manual two-step path still works unchanged.
#
# INSTALL: copy this file to the SAME hooks directory as pre-commit-
# template.sh, under git's exact expected filename (no .sh, and no chmod
# needed beyond what cp already preserves if the source is +x):
#   cp pre-merge-commit-template.sh ~/.git-hooks/pre-merge-commit
#   chmod +x ~/.git-hooks/pre-merge-commit
# guard-session-artifacts-on-default-branch.sh must already be alongside it
# (pre-commit-template.sh's own install step already puts it there).
#
# BYPASS: SESSION_ARTIFACT_BRANCH_BYPASS=1 git merge ...   (or --no-verify).
set -euo pipefail

_HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -x "${_HOOK_DIR}/guard-session-artifacts-on-default-branch.sh" ]]; then
  "${_HOOK_DIR}/guard-session-artifacts-on-default-branch.sh" || exit 1
fi
exit 0
