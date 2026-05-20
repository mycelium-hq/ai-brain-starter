#!/usr/bin/env bash
# Test post-commit-ff-worktrees.sh - the helper that closes the commit-time
# race for reconcile-worktree-shared.py.
#
# Bug class this guards against:
# Reconcile fires at SessionEnd. Between SessionEnd and worktree-archive
# prompt, OTHER committers (hookify-auto-commit, auto-snapshot, the user's
# vault-safe-commit equivalent) can land commits on master, leaving the
# active worktree branch behind master. The archive prompt then surfaces
# byte-identical files as false-positive uncommitted changes. The helper
# script lets any committer FF active claude/* worktrees post-commit.
#
# Three assertions:
#   1. Helper FFs a claude/* worktree branch when master moves ahead of it
#      and the worktree branch is a strict ancestor.
#   2. Helper handles worktree paths containing spaces (the real-world
#      bug - AWK $2 truncates "/path/with spaces/..." silently).
#   3. Helper leaves diverged worktree branches alone (FF-only fails
#      cleanly; the reconcile fallback handles those).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="$REPO_ROOT/scripts/post-commit-ff-worktrees.sh"

if [ ! -f "$HELPER" ]; then
  echo "ERROR: $HELPER not found" >&2
  exit 1
fi

# Use a tmpdir name with a space to exercise the space-safe parse
TMP="$(mktemp -d -t 'starter-ff-XXXXXX')/ff test dir"
mkdir -p "$TMP"
trap 'rm -rf "$(dirname "$TMP")"' EXIT

VAULT="$TMP/vault with spaces"
mkdir -p "$VAULT"
cd "$VAULT"
git init --quiet --initial-branch=master
git config user.email "test@example.com"
git config user.name "Test"

# Seed: one shared-canonical file at main vault
mkdir -p .claude
echo "v1" > .claude/hookify.test.local.md
git add -A
git commit --quiet -m "init"
MASTER_SHA_INIT=$(git rev-parse HEAD)

# Create claude/* worktree off master HEAD
mkdir -p .claude/worktrees
git worktree add --quiet -b claude/test-ff ".claude/worktrees/test-ff"
WT_SHA_INIT=$(git -C ".claude/worktrees/test-ff" rev-parse HEAD)

if [ "$MASTER_SHA_INIT" != "$WT_SHA_INIT" ]; then
  echo "FAIL: worktree branch did not start at master tip" >&2
  exit 1
fi

# Advance master with a new commit (simulating hookify-auto-commit / auto-snapshot)
echo "v2" > .claude/hookify.test.local.md
git add .claude/hookify.test.local.md
git commit --quiet -m "auto-commit: hookify drift"
MASTER_SHA_POST=$(git rev-parse HEAD)

if [ "$MASTER_SHA_INIT" = "$MASTER_SHA_POST" ]; then
  echo "FAIL: master did not advance" >&2
  exit 1
fi

# Run the helper
bash "$HELPER" "$VAULT" >/dev/null 2>&1

# Assertion 1: worktree branch FF'd to master
WT_SHA_AFTER_FF=$(git rev-parse refs/heads/claude/test-ff)
if [ "$WT_SHA_AFTER_FF" != "$MASTER_SHA_POST" ]; then
  echo "FAIL: worktree branch did not FF to master after helper ran" >&2
  echo "  master:        $MASTER_SHA_POST" >&2
  echo "  worktree:      $WT_SHA_AFTER_FF" >&2
  exit 1
fi
echo "PASS: helper FF'd worktree branch to master"

# Assertion 2: space-safe parse worked end-to-end. The vault path is
# "$TMP/vault with spaces" (4 spaces). If the helper truncated on space,
# Assertion 1 would have silently no-op'd. The fact that it passed proves
# the parse handled spaces correctly.
echo "PASS: space-safe parse of worktree paths"

# Assertion 3: diverged worktree branch left alone
git worktree add --quiet -b claude/test-diverged ".claude/worktrees/test-diverged"

cd ".claude/worktrees/test-diverged"
echo "divergent" > divergent.md
git add divergent.md
git commit --quiet -m "diverged: worktree-local commit"
DIVERGED_SHA_PRE=$(git rev-parse HEAD)
cd "$VAULT"

# Advance master once more
echo "v3" > .claude/hookify.test.local.md
git add .claude/hookify.test.local.md
git commit --quiet -m "auto-commit: another drift"
MASTER_SHA_POST_2=$(git rev-parse HEAD)

# Helper should attempt FF, fail silently on diverged, advance the other
bash "$HELPER" "$VAULT" >/dev/null 2>&1

DIVERGED_SHA_POST=$(git rev-parse refs/heads/claude/test-diverged)
if [ "$DIVERGED_SHA_POST" != "$DIVERGED_SHA_PRE" ]; then
  echo "FAIL: helper modified diverged worktree branch (should have left alone)" >&2
  echo "  pre:  $DIVERGED_SHA_PRE" >&2
  echo "  post: $DIVERGED_SHA_POST" >&2
  exit 1
fi
echo "PASS: diverged worktree branch left alone (FF-only failed cleanly)"

# Sanity: the non-diverged worktree advanced again
WT_SHA_FINAL=$(git rev-parse refs/heads/claude/test-ff)
if [ "$WT_SHA_FINAL" != "$MASTER_SHA_POST_2" ]; then
  echo "FAIL: non-diverged worktree did not FF on second helper run" >&2
  exit 1
fi
echo "PASS: non-diverged worktree FF'd on second helper run"

echo
echo "All assertions passed. Post-commit FF helper closes the race correctly."
