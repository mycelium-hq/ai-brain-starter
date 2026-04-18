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

  # Delete claude/ branches whose worktree directory no longer exists.
  # These are safe to remove: session work is already on master.
  # Only deletes branches with NO matching directory — active sessions are safe.
  DELETED=0
  while IFS= read -r branch; do
    slug="${branch#claude/}"
    wt_dir="$VAULT_ROOT/.claude/worktrees/$slug"
    if [ ! -d "$wt_dir" ]; then
      git branch -D "$branch" 2>&1 && DELETED=$((DELETED + 1))
    fi
  done < <(git branch | grep 'claude/' | sed 's/^[* ]*//')
  echo "Deleted $DELETED orphaned claude/ branch(es)"

  echo "--- remaining worktrees ---"
  git worktree list 2>&1 | wc -l | xargs echo "count:"
  echo "--- remaining claude/ branches ---"
  git branch | grep -c 'claude/' 2>/dev/null | xargs echo "count:" || echo "count: 0"
  echo
} >> "$LOG" 2>&1
