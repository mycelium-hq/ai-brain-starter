#!/usr/bin/env bash
# Regression guard for hooks/post-tool-use-learnings.py — the closed-loop
# episodic-capture PostToolUse hook.
#
# Proves the 2026-06-25 fix: a SUCCESSFUL subagent (Agent/Task) return is the
# tool's PRODUCT (free-form prose/code that routinely contains "error",
# "exception", "failed"), NOT a failure signal. Before the fix the generic
# substring scan misclassified successful repo-evaluation transcripts as
# failures and stuffed them — plus the audited third-party content — into an
# error_excerpt Learning. 46 false captures landed across two vaults.
#
# Four assertions (negative + positive controls, per "a guard earns trust only
# by failing on the thing it catches"):
#   (a) the inline unit self-test passes (detect_failure cases),
#   (b) NEGATIVE CONTROL: a successful Agent return with error vocabulary writes
#       NO Learning file,
#   (c) POSITIVE CONTROL: a genuine Agent isError failure DOES write a file
#       (the hook still captures real failures — the fix is not "ignore Agent"),
#   (d) LEAK CONTROL: that genuine-failure file carries the bounded error signal
#       but NOT the raw subagent prompt body (untrusted third-party content).
#
# Bash-script test per the tests/integration/ convention; wired into scripts/ci.sh.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$ROOT/hooks/post-tool-use-learnings.py"

fail=0
pass() { echo "  PASS  $1"; }
bad() { echo "  FAIL  $1"; fail=1; }

[ -f "$HOOK" ] || { echo "::error::hook not found at $HOOK"; exit 1; }

# --- (a) inline unit self-test --------------------------------------------
if python3 "$HOOK" --self-test >/dev/null 2>&1; then
  pass "(a) detect_failure self-test exits 0"
else
  bad "(a) detect_failure self-test FAILED (run: python3 $HOOK --self-test)"
fi

# Scratch vault: a directory whose child folder is named 'Meta' so the hook's
# find_vault_root resolves it on the first iteration (no walk-up ambiguity).
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
VAULT="$TMP/vault"
mkdir -p "$VAULT/Meta"
LEARN="$VAULT/Meta/Learnings"

run_hook() { printf '%s' "$1" | python3 "$HOOK" >/dev/null 2>&1 || true; }
count_md() { find "$LEARN" -name '*.md' 2>/dev/null | wc -l | tr -d ' '; }

# --- (b) NEGATIVE CONTROL: successful Agent return must NOT be captured -----
rm -rf "$LEARN"
run_hook "$(cat <<JSON
{"tool_name":"Agent","cwd":"$VAULT","session_id":"s","tool_call_id":"neg1",
 "tool_input":{"description":"audit","prompt":"read /tmp/thirdparty/foo.py"},
 "tool_response":{"status":"completed","content":"Candidate list: the code handles errors via try/except, fails gracefully on exception, logs fatal conditions."}}
JSON
)"
if [ "$(count_md)" = "0" ]; then
  pass "(b) successful Agent return wrote NO Learning file"
else
  bad "(b) successful Agent return WAS captured ($(count_md) file(s)) — false-positive bug is back"
fi

# --- (c)+(d) POSITIVE + LEAK CONTROL: genuine isError failure --------------
SENTINEL="SENTINEL_THIRDPARTY_a1b2c3d4"
rm -rf "$LEARN"
run_hook "$(cat <<JSON
{"tool_name":"Agent","cwd":"$VAULT","session_id":"s","tool_call_id":"pos1",
 "tool_input":{"description":"audit","prompt":"$SENTINEL untrusted audited repo content"},
 "tool_response":{"isError":true,"error":"agent crashed: API error after 3 retries"}}
JSON
)"
if [ "$(count_md)" = "1" ]; then
  pass "(c) genuine Agent isError failure DID write a Learning file"
  CAP="$(find "$LEARN" -name '*.md' | head -1)"
  if grep -q "agent crashed" "$CAP"; then
    pass "(d.1) capture carries the bounded error signal"
  else
    bad "(d.1) capture is missing the error signal"
  fi
  if grep -q "$SENTINEL" "$CAP"; then
    bad "(d.2) LEAK: raw subagent prompt body persisted ($SENTINEL found in capture)"
  else
    pass "(d.2) raw subagent prompt body NOT persisted (no third-party leak)"
  fi
  if grep -q "Omitted for Agent/Task captures" "$CAP"; then
    pass "(d.3) redaction note present"
  else
    bad "(d.3) redaction note missing"
  fi
else
  bad "(c) genuine Agent isError failure was NOT captured ($(count_md) file(s)) — hook over-suppresses"
fi

echo
if [ "$fail" = "0" ]; then
  echo "test_post_tool_use_learnings: all assertions passed"
else
  echo "::error::test_post_tool_use_learnings: one or more assertions failed"
fi
exit "$fail"
