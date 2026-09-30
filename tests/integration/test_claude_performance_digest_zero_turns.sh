#!/usr/bin/env bash
# Regression guard: scripts/claude_performance_digest.py must still write its
# weekly report when no session in the lookback window has an assistant turn.
#
# THE BUG
#
# generate_report()'s Project Allocation table divided each project's turn count
# by total_turns with no guard. total_turns counts "assistant" records only, but
# every session file in the window still gets a row, because
# `project_turns[project] += 0` creates the key. So when no session in the
# window had an assistant record, the run died with ZeroDivisionError before it
# wrote the report or reached apply_prescriptions(). The Activity Distribution
# and Model Mix tables beside it already guarded their denominators with `or 1`.
#
# Such sessions are real: a prompt that never got a reply leaves a transcript
# with user records and no assistant record (1 of 204 recent sessions on one
# machine, measured 2026-09-25). The crash needs EVERY session in the window to
# look like that, so it is likeliest when the window holds few sessions, as on
# a fresh install.
#
# HARNESS
#
# The script locates everything from where it sits (VAULT_ROOT is
# SCRIPT_DIR.parent.parent) and from Path.home() (PROJECTS_ROOT, MEMORY_FILE),
# so each case runs a COPY of it inside its own root, under a sandboxed home.
# hooks/_lib rides along so any shared helper the script imports from
# SCRIPT_DIR.parent/hooks resolves as it does in a checkout or installed skill:
#
#   $TMP/<case>/skill/scripts/claude_performance_digest.py   SCRIPT_DIR
#   $TMP/<case>/skill/hooks/_lib/                             shared helpers
#   $TMP/<case>/⚙️ Meta/Performance/weekly-<date>.md          the report
#   $TMP/<case>/home/.claude/projects/<project>/*.jsonl      PROJECTS_ROOT
#
# CASES
#
# (a) REGRESSION: two sessions, neither with an assistant record. One is a
#     prompt that never got a reply (the shape found in the wild), the other a
#     lone tool_result line (the shape the bug was reported with). The run must
#     exit 0 with no traceback, write a report that says total_turns: 0 (an
#     `or 1` on the displayed total would fabricate a 1), show both projects at
#     0%, and print main()'s closing "Done.", which only comes after
#     apply_prescriptions(). Fails on the pre-fix script.
# (b) CONTROL: the no-reply session beside a normal one-turn session. Passes
#     before and after the fix. It pins that the guard leaves real percentages
#     alone, and it shows the harness really runs the digest, so a red (a) is
#     the division and not a broken setup.
#
# Uses the `python3` on PATH, as the rest of this suite does. By hand on a
# machine whose python3 is a shim: . tests/integration/lib/real_python.sh &&
# ensure_real_python

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_SRC="$ROOT/scripts/claude_performance_digest.py"

# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$ROOT/tests/integration/lib/sandbox_home.sh"

[ -f "$SCRIPT_SRC" ] || { echo "::error::script not found at $SCRIPT_SRC"; exit 1; }

fail=0
pass() { echo "  PASS  $1"; }
bad() { echo "  FAIL  $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# new_case NAME: a fresh root holding its own copy of the script and hooks/_lib.
new_case() {
  local c="$TMP/$1"
  mkdir -p "$c/skill/scripts" "$c/skill/hooks" "$c/home/.claude/projects"
  cp "$SCRIPT_SRC" "$c/skill/scripts/claude_performance_digest.py"
  cp -R "$ROOT/hooks/_lib" "$c/skill/hooks/_lib"
  printf '%s' "$c"
}

# A prompt that never got a reply: a user record and no assistant record.
write_no_reply_session() {
  mkdir -p "$1"
  printf '%s\n' '{"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {"role": "user", "content": "hello"}}' > "$1/no-reply.jsonl"
}

# Nothing but one tool_result line.
write_tool_result_session() {
  mkdir -p "$1"
  printf '%s\n' '{"type": "tool_result", "message": {"content": [{"type": "text", "text": "ok", "tool_use_id": "toolu_01"}]}}' > "$1/tool-result.jsonl"
}

# A normal session: one assistant turn.
write_one_turn_session() {
  mkdir -p "$1"
  printf '%s\n' '{"type": "assistant", "timestamp": "2026-01-01T00:00:00Z", "message": {"model": "claude-sonnet-4-5", "content": [{"type": "text", "text": "hi"}]}}' > "$1/one-turn.jsonl"
}

# run_digest ROOT: run ROOT's copy under ROOT's sandboxed home. Sets RC, LOG and
# REPORT, and never aborts the test on a non-zero exit.
run_digest() {
  local r
  LOG="$1/digest.log"
  RC=0
  run_sandboxed "$1/home" python3 "$1/skill/scripts/claude_performance_digest.py" --days 7 >"$LOG" 2>&1 || RC=$?
  REPORT=""
  for r in "$1/⚙️ Meta/Performance/"weekly-*.md; do
    if [ -f "$r" ]; then REPORT="$r"; fi
  done
}

# expect_line LABEL FILE LINE: FILE holds LINE as a whole line, byte for byte.
expect_line() {
  if grep -qxF -- "$3" "$2"; then
    pass "$1"
  else
    bad "$1 (no line '$3' in $(basename "$2"))"
  fi
}

show_log() {
  echo "    --- digest output ---"
  sed 's/^/    /' "$LOG" || true
}

# --- (a) REGRESSION: no session in the window has an assistant turn ----------
echo "(a) no session has an assistant turn"
A="$(new_case zero)"
write_no_reply_session "$A/home/.claude/projects/interrupted"
write_tool_result_session "$A/home/.claude/projects/toolresults"
run_digest "$A"
fail_before=$fail

if [ "$RC" -eq 0 ]; then pass "(a.1) digest exits 0"; else bad "(a.1) digest exited $RC"; fi
if grep -q 'Traceback' "$LOG"; then bad "(a.2) traceback in digest output"; else pass "(a.2) no traceback"; fi
if [ -n "$REPORT" ]; then
  pass "(a.3) weekly report written"
  expect_line "(a.4) report says total_turns: 0" "$REPORT" 'total_turns: 0'
  expect_line "(a.5) no-reply project row reads 0%" "$REPORT" '| interrupted | 0 | 0% |'
  expect_line "(a.6) tool-result project row reads 0%" "$REPORT" '| toolresults | 0 | 0% |'
else
  bad "(a.3) no weekly report under $A/⚙️ Meta/Performance"
fi
expect_line "(a.7) run reached the end of main(), after apply_prescriptions()" "$LOG" 'Done.'
if [ "$fail" != "$fail_before" ]; then show_log; fi

# --- (b) CONTROL: a zero-turn session beside a normal one ---------------------
echo "(b) a zero-turn session beside a one-turn session"
B="$(new_case mixed)"
write_no_reply_session "$B/home/.claude/projects/interrupted"
write_one_turn_session "$B/home/.claude/projects/normal"
run_digest "$B"
fail_before=$fail

if [ "$RC" -eq 0 ]; then pass "(b.1) digest exits 0"; else bad "(b.1) digest exited $RC"; fi
if [ -n "$REPORT" ]; then
  pass "(b.2) weekly report written"
  expect_line "(b.3) report says total_turns: 1" "$REPORT" 'total_turns: 1'
  expect_line "(b.4) the one-turn project holds 100%" "$REPORT" '| normal | 1 | 100% |'
  expect_line "(b.5) the zero-turn project holds 0%" "$REPORT" '| interrupted | 0 | 0% |'
else
  bad "(b.2) no weekly report under $B/⚙️ Meta/Performance"
fi
if [ "$fail" != "$fail_before" ]; then show_log; fi

echo
if [ "$fail" = "0" ]; then
  echo "test_claude_performance_digest_zero_turns: all assertions passed"
else
  echo "::error::test_claude_performance_digest_zero_turns: one or more assertions failed"
fi
exit "$fail"
