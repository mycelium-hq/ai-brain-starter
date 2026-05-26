#!/bin/bash
# Weekly git worktree prune for the vault. Self-locates so it survives a vault move.
#
# Also prunes orphan snapshot dirs created by the
# snapshot-pending-work-on-stop hook (when installed): once a worktree is
# archived AND its snapshot dir has gone untouched for >
# SNAPSHOT_RETENTION_DAYS, the snapshot is removed. Live-worktree
# snapshots and recent orphans (still within the recovery window) are
# kept. SNAPSHOT_RETENTION_DAYS is env-overridable; 30-day default is
# conservative because work-loss recovery is higher-stakes than
# session-history archival. The block silently no-ops when no snapshot
# dir exists, so this is safe to ship before the matching hooks land.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ROOT="${VAULT_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/../logs}"
LOG="$LOG_DIR/worktree-prune.log"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$VAULT_ROOT/⚙️ Meta/Worktree Snapshots}"
WT_DIR="${WT_DIR:-$VAULT_ROOT/.claude/worktrees}"
SNAPSHOT_RETENTION_DAYS="${SNAPSHOT_RETENTION_DAYS:-30}"
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

  # Prune orphan snapshot dirs (worktree archived AND past recovery window).
  # No-op when SNAPSHOT_DIR doesn't exist (e.g. snapshot hooks not installed).
  if [ -d "$SNAPSHOT_DIR" ]; then
    echo "--- snapshot prune (retention=${SNAPSHOT_RETENTION_DAYS}d) ---"
    snap_deleted=0
    snap_kept_active=0
    snap_kept_recoverable=0
    while IFS= read -r snap_path; do
      [ -z "$snap_path" ] && continue
      slug="$(basename "$snap_path")"
      if [ -d "$WT_DIR/$slug" ]; then
        echo "keeping snapshot (worktree live): $slug"
        snap_kept_active=$((snap_kept_active + 1))
        continue
      fi
      stale=$(find "$snap_path" -maxdepth 0 -mtime +"$SNAPSHOT_RETENTION_DAYS" 2>/dev/null)
      if [ -n "$stale" ]; then
        files_dropped=$(find "$snap_path" -type f 2>/dev/null | wc -l | tr -d ' ')
        echo "deleting orphan snapshot (idle >${SNAPSHOT_RETENTION_DAYS}d, ${files_dropped} file(s)): $slug"
        rm -rf "$snap_path"
        snap_deleted=$((snap_deleted + 1))
      else
        echo "keeping orphan snapshot (within ${SNAPSHOT_RETENTION_DAYS}d window): $slug"
        snap_kept_recoverable=$((snap_kept_recoverable + 1))
      fi
    done < <(find "$SNAPSHOT_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
    echo "snapshots: deleted=$snap_deleted kept_active=$snap_kept_active kept_recoverable=$snap_kept_recoverable"
  fi
  echo
} >> "$LOG" 2>&1
