#!/bin/bash
# Weekly git worktree prune for the vault. Self-locates so it survives a vault move.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ROOT="${VAULT_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/../logs}"
LOG="$LOG_DIR/worktree-prune.log"
mkdir -p "$(dirname "$LOG")"
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') prune $VAULT_ROOT ==="
  cd "$VAULT_ROOT" || { echo "ERR: cannot cd to vault"; exit 1; }

  # Remove stale worktree refs (directories already deleted)
  git worktree prune -v 2>&1

  # Delete claude/ branches whose worktree directory no longer exists AND
  # whose commits are fully reachable from master.
  #
  # Two safety gates (defense-in-depth against the worktree session-loss class
  # documented in issue #65):
  #   1. Worktree directory must be gone (active sessions are safe).
  #   2. Branch must have zero commits not reachable from master. If a
  #      session committed to claude/<slug> without those commits landing on
  #      master — which happens when session-end-hook resolves VAULT to the
  #      worktree path instead of the main vault — deletion would orphan the
  #      commits. Refuse loudly so a human can recover via reflog or the
  #      recover-orphan-claude-branches.py script.
  DELETED=0
  REFUSED=0
  while IFS= read -r branch; do
    slug="${branch#claude/}"
    wt_dir="$VAULT_ROOT/.claude/worktrees/$slug"
    [ -d "$wt_dir" ] && continue

    UNMERGED=$(git rev-list --count "master..$branch" 2>/dev/null || echo "?")
    if [ "$UNMERGED" = "0" ]; then
      git branch -D "$branch" 2>&1 && DELETED=$((DELETED + 1))
    else
      echo "REFUSE: $branch has $UNMERGED commit(s) not on master — not deleting."
      echo "  Inspect:  git log master..$branch --oneline"
      echo "  Recover:  python3 \"$SCRIPT_DIR/recover-orphan-claude-branches.py\""
      REFUSED=$((REFUSED + 1))
    fi
  done < <(git branch | grep 'claude/' | sed 's/^[* ]*//')
  echo "Deleted $DELETED orphaned claude/ branch(es)"
  if [ "$REFUSED" -gt 0 ]; then
    echo "Refused $REFUSED branch(es) with unmerged commits — run recover-orphan-claude-branches.py"
  fi

  echo "--- remaining worktrees ---"
  git worktree list 2>&1 | wc -l | xargs echo "count:"
  echo "--- remaining claude/ branches ---"
  git branch | grep -c 'claude/' 2>/dev/null | xargs echo "count:" || echo "count: 0"
  echo
} >> "$LOG" 2>&1
