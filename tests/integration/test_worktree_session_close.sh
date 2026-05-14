#!/usr/bin/env bash
# Test the worktree session-close invariant: session commits land on master,
# not on `claude/<slug>` branches that get pruned later.
#
# Catches issue #65: when session-end-hook.sh resolved VAULT via
# `$SCRIPT_DIR/../..` from inside a worktree's checkout of the script, every
# commit went to the worktree branch, then `worktree-prune.sh` deleted the
# branch and the commits became orphaned.
#
# Two assertions:
#   1. session-end-hook.sh's VAULT resolution returns the MAIN vault path
#      when invoked from a worktree, not the worktree path.
#   2. worktree-prune.sh REFUSES to delete a `claude/*` branch that has
#      commits not reachable from master (refuses, doesn't auto-merge).
#
# Self-contained: creates a tmpdir vault, runs the assertions, cleans up.
# Exit 0 = pass. Exit 1 = fail with details on stderr.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/scripts/session-end-hook.sh"
PRUNE="$REPO_ROOT/scripts/worktree-prune.sh"

if [ ! -f "$HOOK" ]; then
  echo "ERROR: $HOOK not found" >&2
  exit 1
fi
if [ ! -f "$PRUNE" ]; then
  echo "ERROR: $PRUNE not found" >&2
  exit 1
fi

# Use a tmpdir for the fake vault. Trap clean up on exit.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

VAULT="$TMP/vault"
mkdir -p "$VAULT"
cd "$VAULT"
git init --quiet --initial-branch=master
git config user.email "test@example.com"
git config user.name "Test"

# Lay down a Meta/scripts/ checkout so the worktree carries its own copy of
# session-end-hook.sh (replicating the actual install layout where the script
# lives at <vault>/⚙️ Meta/scripts/session-end-hook.sh).
mkdir -p "Meta/scripts"
cp "$HOOK" "Meta/scripts/session-end-hook.sh"
chmod +x "Meta/scripts/session-end-hook.sh"
echo "# vault" > README.md
git add -A
git commit --quiet -m "init"

# Create a worktree at .claude/worktrees/test-slug/
mkdir -p .claude/worktrees
git worktree add --quiet -b claude/test-slug ".claude/worktrees/test-slug"

WORKTREE_PATH="$VAULT/.claude/worktrees/test-slug"
WORKTREE_SCRIPT="$WORKTREE_PATH/Meta/scripts/session-end-hook.sh"

if [ ! -f "$WORKTREE_SCRIPT" ]; then
  echo "FAIL: worktree did not carry Meta/scripts/session-end-hook.sh" >&2
  exit 1
fi

# ─── Assertion 1: VAULT resolution from inside the worktree ────────────────
# Source the helper function from the hook script and call it directly with
# the worktree's SCRIPT_DIR. The function should strip from
# `.claude/worktrees/<slug>/...` onward and return the main vault path.

# Extract the resolve_main_vault function definition by sourcing the script
# up to the function-end line (we can't source the whole script because it
# tries to read stdin and write to $HOME).
RESOLVE_FN_BODY=$(awk '
  /^resolve_main_vault\(\) \{/ {capture=1}
  capture {print}
  capture && /^\}$/ {exit}
' "$WORKTREE_SCRIPT")

if [ -z "$RESOLVE_FN_BODY" ]; then
  echo "FAIL: resolve_main_vault() not found in $WORKTREE_SCRIPT" >&2
  echo "  The fix for #65 should add this function." >&2
  exit 1
fi

# shellcheck disable=SC1090
eval "$RESOLVE_FN_BODY"

WORKTREE_SCRIPT_DIR="$WORKTREE_PATH/Meta/scripts"
WORKTREE_CANDIDATE="$(cd "$WORKTREE_SCRIPT_DIR/../.." && pwd)"
RESOLVED="$(resolve_main_vault "$WORKTREE_CANDIDATE")"

if [ "$RESOLVED" != "$VAULT" ]; then
  echo "FAIL: resolve_main_vault did not strip worktree path" >&2
  echo "  input:    $WORKTREE_CANDIDATE" >&2
  echo "  expected: $VAULT" >&2
  echo "  got:      $RESOLVED" >&2
  exit 1
fi
echo "PASS: resolve_main_vault strips worktree path correctly"

# Also assert that a non-worktree path passes through unchanged.
NORMAL_RESOLVED="$(resolve_main_vault "/some/normal/path")"
if [ "$NORMAL_RESOLVED" != "/some/normal/path" ]; then
  echo "FAIL: resolve_main_vault changed a non-worktree path" >&2
  echo "  expected: /some/normal/path" >&2
  echo "  got:      $NORMAL_RESOLVED" >&2
  exit 1
fi
echo "PASS: resolve_main_vault leaves non-worktree paths unchanged"

# ─── Assertion 2: worktree-prune refuses to delete a branch with unmerged commits ─
# Simulate the bug scenario: the worktree has been removed from disk, but the
# claude/test-slug branch has a commit not on master. The pruner must refuse.

# Add a commit on the worktree branch
cd "$WORKTREE_PATH"
echo "orphan content" > orphan.md
git add orphan.md
git commit --quiet -m "session work that didn't make it to master"

# Remove the worktree directory (simulating archive)
cd "$VAULT"
git worktree remove --force ".claude/worktrees/test-slug" 2>/dev/null || true
rm -rf ".claude/worktrees/test-slug"

# Run worktree-prune.sh against this vault
PRUNE_OUTPUT="$(VAULT_ROOT="$VAULT" LOG_DIR="$TMP/logs" bash "$PRUNE" 2>&1 || true)"
PRUNE_LOG="$TMP/logs/worktree-prune.log"

# Inspect log: must contain REFUSE for claude/test-slug, must NOT have deleted it
if [ ! -f "$PRUNE_LOG" ]; then
  echo "FAIL: prune log not written at $PRUNE_LOG" >&2
  echo "stdout: $PRUNE_OUTPUT" >&2
  exit 1
fi

if ! grep -q "REFUSE: claude/test-slug" "$PRUNE_LOG"; then
  echo "FAIL: worktree-prune did not REFUSE claude/test-slug" >&2
  echo "log:" >&2
  cat "$PRUNE_LOG" >&2
  exit 1
fi

# Verify the branch still exists in git
if ! git show-ref --verify --quiet refs/heads/claude/test-slug; then
  echo "FAIL: claude/test-slug was deleted despite having unmerged commits" >&2
  exit 1
fi
echo "PASS: worktree-prune refused to delete branch with unmerged commits"

# ─── Assertion 3: worktree-prune DOES delete fully-merged orphan branches ──
# Create a second branch, fully merged into master, with no worktree dir.
git checkout master --quiet
git branch claude/fully-merged-slug master

# Confirm the directory doesn't exist
mkdir -p .claude/worktrees  # keep the dir, just no slug subdir

PRUNE_OUTPUT2="$(VAULT_ROOT="$VAULT" LOG_DIR="$TMP/logs2" bash "$PRUNE" 2>&1 || true)"
PRUNE_LOG2="$TMP/logs2/worktree-prune.log"

if ! grep -q "Deleted 1 orphaned" "$PRUNE_LOG2"; then
  echo "FAIL: worktree-prune did not delete the fully-merged orphan branch" >&2
  echo "log:" >&2
  cat "$PRUNE_LOG2" >&2
  exit 1
fi

if git show-ref --verify --quiet refs/heads/claude/fully-merged-slug; then
  echo "FAIL: claude/fully-merged-slug still exists after prune (should have been deleted)" >&2
  exit 1
fi
echo "PASS: worktree-prune deleted fully-merged orphan branch"

echo
echo "All assertions passed. Issue #65 invariant holds."
