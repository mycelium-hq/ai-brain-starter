#!/usr/bin/env bash
# Test the reconcile-worktree-shared FF invariant: when the worktree branch
# is a strict ancestor of master AND shared-canonical files in the worktree
# are byte-identical to main vault, the hook fast-forwards the worktree
# branch instead of committing on it. Worktree branch SHA == master SHA
# afterward, no new commits on `claude/*`.
#
# Sibling to test_worktree_session_close.sh. Same bug family as issue #65:
# both fixes guard against orphan-commit accumulation on worktree branches.
# This test specifically guards PR #68 (reconcile FF), the way
# test_worktree_session_close.sh guards PR #66 (session-end-hook routing).
#
# Three assertions:
#   1. Hook FF-merges the worktree branch to master when files are
#      byte-identical and worktree branch is a strict ancestor.
#   2. After the hook, worktree branch tip == master tip (no orphan commit).
#   3. Hook falls back to commit-on-branch when FF is impossible (worktree
#      branch has diverged with its own commits).
#
# Self-contained: creates a tmpdir vault, runs the assertions, cleans up.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/reconcile-worktree-shared.py"

if [ ! -f "$HOOK" ]; then
  echo "ERROR: $HOOK not found" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

VAULT="$TMP/vault"
mkdir -p "$VAULT"
cd "$VAULT"
git init --quiet --initial-branch=master
git config user.email "test@example.com"
git config user.name "Test"

# Lay down a shared-canonical file at main vault path
mkdir -p .claude
cat > .claude/hookify.test-rule.local.md <<EOF
# Original content
This is the original version of the rule.
EOF
git add -A
git commit --quiet -m "init: add hookify test rule"
MASTER_SHA_INIT=$(git rev-parse HEAD)

# Create worktree at .claude/worktrees/test-slug/ — points at master HEAD
mkdir -p .claude/worktrees
git worktree add --quiet -b claude/test-slug ".claude/worktrees/test-slug"
WT_BRANCH_SHA_INIT=$(git -C ".claude/worktrees/test-slug" rev-parse HEAD)

# Sanity: worktree branch starts at master tip
if [ "$MASTER_SHA_INIT" != "$WT_BRANCH_SHA_INIT" ]; then
  echo "FAIL: worktree branch did not start at master tip" >&2
  exit 1
fi

# Now: simulate the bug-class scenario.
# 1. Edit the shared-canonical file at MAIN vault path (the canonical
#    location per worktree-edit-discipline)
cat > .claude/hookify.test-rule.local.md <<EOF
# Updated content
This is the new version of the rule.
EOF
# 2. Hookify-auto-commit hook would commit on master. Simulate that:
git add .claude/hookify.test-rule.local.md
git commit --quiet -m "auto-commit: hookify rule update"
# shellcheck disable=SC2034  # snapshot of master after the edit; documents the step (not asserted)
MASTER_SHA_AFTER_EDIT=$(git rev-parse HEAD)

# 3. The worktree's filesystem ALSO has a copy of this file (because
#    worktrees check out their branch's tree). When the worktree was
#    created, its file matched master's pre-edit content. Now master
#    has new content; the worktree's filesystem still has old content.
#    To simulate the actual production scenario (where some mechanism
#    syncs the new bytes into the worktree FS), copy the new content into
#    the worktree FS.
cp .claude/hookify.test-rule.local.md ".claude/worktrees/test-slug/.claude/hookify.test-rule.local.md"

# Now the worktree's FS has the new bytes, but the worktree's git INDEX
# still points at the old commit. `git status` in the worktree shows the
# file as MODIFIED. The reconcile hook should resolve this.

# Sanity: worktree shows the file as modified
WT_STATUS=$(git -C ".claude/worktrees/test-slug" status --short)
if [ -z "$WT_STATUS" ]; then
  echo "FAIL: worktree did not show modified state pre-hook" >&2
  exit 1
fi

# ─── Run the reconcile hook from inside the worktree ──────────────────
cd ".claude/worktrees/test-slug"
# Hook reads stdin (JSON). Feed it empty {}.
echo '{}' | python3 "$HOOK" >/dev/null 2>&1 || true
cd "$VAULT"

# ─── Assertion 1: worktree branch SHA == master SHA (FF happened) ────
WT_BRANCH_SHA_POST=$(git rev-parse refs/heads/claude/test-slug)
MASTER_SHA_POST=$(git rev-parse refs/heads/master)

if [ "$WT_BRANCH_SHA_POST" != "$MASTER_SHA_POST" ]; then
  echo "FAIL: worktree branch SHA did not advance to master after FF" >&2
  echo "  master:        $MASTER_SHA_POST" >&2
  echo "  worktree branch: $WT_BRANCH_SHA_POST" >&2
  echo "" >&2
  echo "Expected the reconcile hook to do `git merge --ff-only master`," >&2
  echo "advancing claude/test-slug to master's tip with NO new commit." >&2
  exit 1
fi
echo "PASS: reconcile hook fast-forwarded worktree branch to master"

# ─── Assertion 2: no new commits on claude/test-slug beyond master ────
UNMERGED=$(git rev-list --count master..refs/heads/claude/test-slug 2>/dev/null || echo "?")
if [ "$UNMERGED" != "0" ]; then
  echo "FAIL: reconcile hook created $UNMERGED orphan commit(s) on claude/test-slug" >&2
  echo "  Expected 0 — FF should advance the branch pointer without a new commit." >&2
  git log master..refs/heads/claude/test-slug --oneline >&2
  exit 1
fi
echo "PASS: no orphan commits created on claude/test-slug"

# ─── Assertion 3: fallback path when FF is impossible ────────────────
# Create a second worktree, give it its OWN commit (so its branch
# diverges from master), then trigger reconcile. The hook should fall
# back to the commit-on-branch path.
mkdir -p .claude/worktrees
git worktree add --quiet -b claude/diverged-slug ".claude/worktrees/diverged-slug"

# Make a commit on the diverged worktree branch
cd ".claude/worktrees/diverged-slug"
echo "divergent content" > divergent.md
git add divergent.md
git commit --quiet -m "diverged: worktree-local commit"
cd "$VAULT"

# Advance master with a new shared-canonical file edit
cat > .claude/hookify.another-rule.local.md <<EOF
Another rule.
EOF
git add .claude/hookify.another-rule.local.md
git commit --quiet -m "auto-commit: second hookify rule update"

# Sync the new bytes into the diverged worktree's FS
cp .claude/hookify.another-rule.local.md ".claude/worktrees/diverged-slug/.claude/hookify.another-rule.local.md"

DIVERGED_BRANCH_SHA_PRE=$(git rev-parse refs/heads/claude/diverged-slug)
# shellcheck disable=SC2034  # snapshot of master pre-fallback; documents the pre-state (not asserted)
MASTER_SHA_PRE_FALLBACK=$(git rev-parse refs/heads/master)

cd ".claude/worktrees/diverged-slug"
echo '{}' | python3 "$HOOK" >/dev/null 2>&1 || true
cd "$VAULT"

# FF would fail because the diverged branch has its own commit. The hook
# should have committed on the diverged branch (fallback path). Assert:
# - The branch HEAD advanced (a commit was created)
# - The branch still has its diverged commit (not lost)
DIVERGED_BRANCH_SHA_POST=$(git rev-parse refs/heads/claude/diverged-slug)
if [ "$DIVERGED_BRANCH_SHA_POST" = "$DIVERGED_BRANCH_SHA_PRE" ]; then
  echo "FAIL: hook fallback did not commit on diverged worktree branch" >&2
  echo "  branch SHA unchanged: $DIVERGED_BRANCH_SHA_POST" >&2
  exit 1
fi

# Verify the diverged commit is still reachable from the branch
if ! git merge-base --is-ancestor "$DIVERGED_BRANCH_SHA_PRE" "$DIVERGED_BRANCH_SHA_POST"; then
  echo "FAIL: hook fallback lost the worktree branch's prior diverged commit" >&2
  exit 1
fi
echo "PASS: reconcile hook fell back to commit-on-branch when FF was impossible"

echo
echo "All assertions passed. Reconcile FF invariant holds."
