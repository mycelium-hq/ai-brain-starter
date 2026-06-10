#!/usr/bin/env bash
# test_dev_worktree_detached_gitdir.sh — negative-control test for the
# claude-dev-worktree wrapper against a DETACHED-GITDIR repo.
#
# The hazard (bug class WRAPPER-FAILS-ON-DETACHED-GITDIR): a repo whose
# `.git` is a pointer FILE (`gitdir: /path`, the cloud-sync-safe layout)
# (a) fails a naive `[[ -d .git ]]` repo check, and (b) carries
# `core.worktree` in the SHARED config, which every linked worktree
# inherits — so a new worktree silently resolves its work tree to the MAIN
# checkout and files created inside it are invisible to git.
#
# This test builds that exact layout in a sandbox and asserts the wrapper:
#   1. accepts the repo (rev-parse check, not -d .git),
#   2. auto-heals the shared core.worktree (per-worktree config migration),
#   3. hands over a worktree that resolves to ITSELF,
#   4. sees files created inside the worktree,
#   5. leaves the main checkout resolving correctly,
#   6. cleans up (worktree + branch gone).
#
# Run the OLD wrapper through this test to see it fail (the negative
# control): bash tests/integration/test_dev_worktree_detached_gitdir.sh /path/to/old/wrapper
#
# No network: origin is a local bare repo; `git fetch origin` stays on disk.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WRAPPER="${1:-$repo_root/skills/dev-repo-worktrees/claude-dev-worktree}"

sandbox="$(mktemp -d)"
cleanup() { rm -rf "$sandbox"; }
trap cleanup EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

[ -f "$WRAPPER" ] || fail "wrapper not found at $WRAPPER"

# ---- fixture: detached-gitdir repo with the core.worktree poison ----------
mkdir -p "$sandbox/dev"
main_repo="$sandbox/dev/myrepo"

git init -q -b main --separate-git-dir "$sandbox/gitdb" "$main_repo"
git -C "$main_repo" config user.email "test@example.invalid"
git -C "$main_repo" config user.name "Test"
# Set the poison explicitly (some git versions set it via --separate-git-dir,
# some don't — the fixture must be deterministic about reproducing the hazard).
git -C "$main_repo" config core.worktree "$main_repo"

echo "hello" > "$main_repo/README.md"
git -C "$main_repo" add README.md
git -C "$main_repo" commit -qm "init"

git init -q -b main --bare "$sandbox/origin.git"
git -C "$main_repo" remote add origin "$sandbox/origin.git"
git -C "$main_repo" push -q origin main

# Preconditions: the fixture really is the hazardous layout.
[ -f "$main_repo/.git" ] || fail "fixture: .git should be a pointer FILE"
[ -n "$(git -C "$main_repo" config --get core.worktree)" ] \
    || fail "fixture: shared core.worktree should be set"

# ---- 1+2+3: start must accept the repo, heal, and hand over a clean tree ---
wt_path=""
if ! wt_path="$(DEV_ROOT="$sandbox/dev" bash "$WRAPPER" start myrepo probe-fix 2>"$sandbox/start.log")"; then
    sed 's/^/    wrapper: /' "$sandbox/start.log" >&2 || true
    fail "wrapper 'start' exited non-zero on a detached-gitdir repo"
fi

expected_wt="$sandbox/dev/myrepo-probe-fix"
[ "$wt_path" = "$expected_wt" ] || fail "wrapper printed '$wt_path', expected '$expected_wt'"
[ -d "$expected_wt" ] || fail "worktree dir not created at $expected_wt"

want="$(cd "$expected_wt" && pwd -P)"
got="$(git -C "$expected_wt" rev-parse --show-toplevel 2>/dev/null || true)"
[ "$got" = "$want" ] || fail "worktree resolves to '$got', expected '$want' (core.worktree poison not healed)"

# ---- 4: files created in the worktree must be visible to git ---------------
touch "$expected_wt/probe.txt"
status_out="$(git -C "$expected_wt" status --porcelain)"
case "$status_out" in
    *"?? probe.txt"*) : ;;
    *) fail "probe.txt invisible to git in the worktree (status: '$status_out')" ;;
esac

# ---- 5: the main checkout must still resolve to itself ---------------------
main_want="$(cd "$main_repo" && pwd -P)"
main_got="$(git -C "$main_repo" rev-parse --show-toplevel)"
[ "$main_got" = "$main_want" ] || fail "main checkout resolves to '$main_got' after heal, expected '$main_want'"

# ---- 6: cleanup removes worktree + branch ----------------------------------
DEV_ROOT="$sandbox/dev" bash "$WRAPPER" cleanup myrepo probe-fix 2>/dev/null \
    || fail "wrapper 'cleanup' exited non-zero"
[ ! -e "$expected_wt" ] || fail "worktree dir still present after cleanup"
if git -C "$main_repo" show-ref --verify --quiet "refs/heads/claude/probe-fix"; then
    fail "branch claude/probe-fix still present after cleanup"
fi

echo "PASS: test_dev_worktree_detached_gitdir (wrapper: $WRAPPER)"
