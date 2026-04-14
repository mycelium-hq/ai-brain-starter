#!/bin/bash
# Session End Hook — writes per-worktree session file, then runs aggregator
# Called by Claude Code Stop hook.
#
# PER-WORKTREE META WRITES:
# Instead of writing to the shared Last Session.md (which races on concurrent
# worktrees), each session now gets its own file in Meta/Sessions/ named
# by timestamp + worktree. After the stub is created, the aggregator script
# rebuilds Last Session.md from all Sessions/ files. Concurrent writes to
# Sessions/ cannot collide (unique filenames); concurrent aggregator runs
# produce deterministic output (same sorted input -> same bytes).

# Auto-detect vault root from script location or $VAULT_ROOT
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
SESSION_LOG="$META_DIR/Session Log.md"
AGGREGATE_SESSIONS="$META_DIR/scripts/aggregate-sessions.py"
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)
TIMESTAMP_FILE=$(date +%Y-%m-%dT%H-%M)

# Derive worktree name. The Stop hook runs in a subshell whose cwd is
# usually the Claude Code primary working directory.
WORKTREE_NAME=""
PWD_PATH="$(pwd)"
case "$PWD_PATH" in
  *"/.claude/worktrees/"*)
    WORKTREE_NAME=$(echo "$PWD_PATH" | sed -n 's|.*/\.claude/worktrees/\([^/]*\).*|\1|p')
    ;;
esac

# Fallback: try reading the .git file if we're inside a git worktree
if [ -z "$WORKTREE_NAME" ] && [ -f "$PWD_PATH/.git" ]; then
  GITDIR=$(grep -o 'worktrees/[^ ]*' "$PWD_PATH/.git" 2>/dev/null | head -1)
  if [ -n "$GITDIR" ]; then
    WORKTREE_NAME=$(echo "$GITDIR" | sed 's|worktrees/||' | tr -d '[:space:]')
  fi
fi

# Last-resort fallback: unique PID-based label
if [ -z "$WORKTREE_NAME" ]; then
  WORKTREE_NAME="main-$$"
fi

SESSION_FILE="$SESSIONS_DIR/${TIMESTAMP_FILE}-${WORKTREE_NAME}.md"

# Ensure the Sessions folder exists
mkdir -p "$SESSIONS_DIR"

# Step 1: Write a guaranteed timestamp to Session Log
echo "- $DATE $TIME — session ended ($WORKTREE_NAME)" >> "$SESSION_LOG"

# Step 2: Write a stub session file if one doesn't already exist
if [ ! -f "$SESSION_FILE" ]; then
  cat > "$SESSION_FILE" <<EOF
---
creationDate: ${DATE}T${TIME}
type: session
worktree: ${WORKTREE_NAME}
session_date: ${DATE}
session_label: "update pending"
aliases: [Session ${DATE} ${WORKTREE_NAME}]
---

# Session -- update pending (${DATE} ${TIME}, \`${WORKTREE_NAME}\` worktree)

**Date:** ${DATE} ${TIME}
**Session:** *stub written by session-end-hook.sh -- Claude to fill in*

## Status

This file is a placeholder. Claude should replace the body with a full
session summary: what was worked on, what shipped, what's pending, any
open threads. Keep the frontmatter fields valid -- \`creationDate\`,
\`type: session\`, \`worktree\`, \`session_date\`.
EOF
fi

# Step 3: Run the aggregator to refresh Last Session.md from Sessions/.
if [ -f "$AGGREGATE_SESSIONS" ]; then
  python3 "$AGGREGATE_SESSIONS" >/dev/null 2>&1 || true
fi

# Step 4: Emit a continuation message for Claude to fill in the session file
cat <<EOF
{"continue":true,"stopReason":"session-end-cascade","systemMessage":"SESSION ENDING (${DATE} ${TIME}, worktree: ${WORKTREE_NAME}): A per-worktree session stub was created at '${SESSION_FILE}'. REPLACE the stub body with a full session summary -- keep the frontmatter fields (creationDate, type: session, worktree, session_date) valid and update the session_label and the '# Session -- ...' heading to match the real work. WRITE ONLY TO '${SESSION_FILE}' -- do NOT write to Last Session.md directly (it is auto-generated from Sessions/ by aggregate-sessions.py). VERBATIM RULE: for any commitments made during this session, capture the EXACT words used. For any decisions made, ALSO create a per-decision file at '${META_DIR}/Decisions/${TIMESTAMP_FILE}-{slug}.md' with the decision template (What/Why/Floor/Stakes/Speed/Outcome/Pattern). After writing the session and decision files, run: python3 '${META_DIR}/scripts/aggregate-sessions.py' && python3 '${META_DIR}/scripts/aggregate-decisions.py'."}
EOF
