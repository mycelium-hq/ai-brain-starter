#!/bin/bash
# Session End Hook — logs timestamp, cleans old files, runs aggregator
# Called by Claude Code Stop hook.
#
# NO STUBS: Claude writes session files directly during session close
# (see templates/rules/session-end-cascade.md Phase 2). This hook only:
#   1. Appends a timestamp to Session Log
#   2. Cleans up: deletes stubs >7d old, archives substantive files >7d old
#   3. Runs the aggregator to refresh Last Session.md
#   4. Emits the session-close prompt for Claude
#
# Prior versions wrote a "stub" file every time the hook fired, expecting
# Claude to fill it in. In practice most sessions end without running the
# full protocol (short sessions, abrupt exits, worktree subagents), and
# stubs piled up — one user had 966 of 1,046 files as empty stubs. This
# version trusts Claude to write the real file during session close.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT="${VAULT_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# Auto-detect the Meta folder (with or without emoji prefix)
META_DIR=""
for candidate in "$VAULT"/*Meta; do
  if [ -d "$candidate" ]; then
    META_DIR="$candidate"
    break
  fi
done
[ -z "$META_DIR" ] && META_DIR="$VAULT/Meta"

SESSIONS_DIR="$META_DIR/Sessions"
ARCHIVE_DIR="$SESSIONS_DIR/Archive"
SESSION_LOG="$META_DIR/Session Log.md"
AGGREGATE_SESSIONS="$META_DIR/scripts/aggregate-sessions.py"
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)
TIMESTAMP_FILE=$(date +%Y-%m-%dT%H-%M)

# Cutoff for retention (7 days back). BSD date (macOS) uses -v, GNU uses -d.
if date -v-7d +%Y-%m-%d >/dev/null 2>&1; then
  CUTOFF=$(date -v-7d +%Y-%m-%d)
else
  CUTOFF=$(date -d '7 days ago' +%Y-%m-%d)
fi

# Derive worktree name (3 methods: path match, .git file, PID fallback)
WORKTREE_NAME=""
PWD_PATH="$(pwd)"
case "$PWD_PATH" in
  *"/.claude/worktrees/"*)
    WORKTREE_NAME=$(echo "$PWD_PATH" | sed -n 's|.*/\.claude/worktrees/\([^/]*\).*|\1|p')
    ;;
esac
if [ -z "$WORKTREE_NAME" ] && [ -f "$PWD_PATH/.git" ]; then
  GITDIR=$(grep -o 'worktrees/[^ ]*' "$PWD_PATH/.git" 2>/dev/null | head -1)
  if [ -n "$GITDIR" ]; then
    WORKTREE_NAME=$(echo "$GITDIR" | sed 's|worktrees/||' | tr -d '[:space:]')
  fi
fi
if [ -z "$WORKTREE_NAME" ]; then
  WORKTREE_NAME="main-$$"
fi

SESSION_FILE="$SESSIONS_DIR/${TIMESTAMP_FILE}-${WORKTREE_NAME}.md"

mkdir -p "$SESSIONS_DIR"
mkdir -p "$ARCHIVE_DIR"

# Step 1: Append timestamp to Session Log (atomic for small writes)
echo "- $DATE $TIME — session ended ($WORKTREE_NAME)" >> "$SESSION_LOG"

# Step 2: Retention cleanup — delete stubs >7d, archive substantive >7d.
# Runs every hook invocation but only touches files past the cutoff.
for f in "$SESSIONS_DIR"/*.md; do
  [ -f "$f" ] || continue
  fname=$(basename "$f")
  fdate="${fname:0:10}"
  [[ "$fdate" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || \
  [[ "$fdate" =~ ^[0-9]{8} ]] || continue
  if [[ "$fdate" =~ ^[0-9]{8}$ ]]; then
    fdate="${fdate:0:4}-${fdate:4:2}-${fdate:6:2}"
  fi
  [[ "$fdate" > "$CUTOFF" || "$fdate" == "$CUTOFF" ]] && continue
  if grep -q 'session_label: "update pending"' "$f" 2>/dev/null; then
    rm "$f"
  else
    mv "$f" "$ARCHIVE_DIR/"
  fi
done

# Step 3: Run aggregator
if [ -f "$AGGREGATE_SESSIONS" ]; then
  VAULT_ROOT="$VAULT" python3 "$AGGREGATE_SESSIONS" >/dev/null 2>&1 || true
fi

# Step 4: Emit session-close prompt for Claude
cat <<EOF
{"continue":true,"stopReason":"session-end-cascade","systemMessage":"SESSION ENDING (${DATE} ${TIME}, worktree: ${WORKTREE_NAME}): Run session close protocol (⚙️ Meta/rules/session-end-cascade.md). Write session file to '${SESSION_FILE}' — do NOT write to Last Session.md (auto-generated). For any decisions, create per-decision files at '${META_DIR}/Decisions/${TIMESTAMP_FILE}-{slug}.md'. After writing, run: VAULT_ROOT='${VAULT}' python3 '${AGGREGATE_SESSIONS}' && VAULT_ROOT='${VAULT}' python3 '${META_DIR}/scripts/aggregate-decisions.py'."}
EOF
