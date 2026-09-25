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
#   (f)-(j) MYC-4703: secrets never reach the synced sink from any tool, in any
#       position (line start, after a colour code), and redaction stays bounded.
#
# Bash-script test per the tests/integration/ convention; wired into scripts/ci.sh.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$ROOT/hooks/post-tool-use-learnings.py"
# shellcheck source=tests/integration/lib/real_python.sh
. "$ROOT/tests/integration/lib/real_python.sh"
ensure_real_python

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
  # (e) sink self-protection: the episodic sink must carry a .gitignore that
  # excludes everything, so captures never enter a vault's git history
  # regardless of the vault's root .gitignore or the operator's git habits.
  if [ -f "$LEARN/.gitignore" ] && grep -qx '\*' "$LEARN/.gitignore" && grep -qx '!.gitignore' "$LEARN/.gitignore"; then
    pass "(e) sink self-protects with a .gitignore (machinery never syncs)"
  else
    bad "(e) sink .gitignore missing/incomplete — captures could be committed to a remote"
  fi
else
  bad "(c) genuine Agent isError failure was NOT captured ($(count_md) file(s)) — hook over-suppresses"
fi

# --- (f) LEAK CONTROL: Bash argv (Authorization: Bearer header) is redacted -
# MYC-4703: credentials live in Bash argv (curl -H 'Authorization: Bearer ...'),
# and before the fix only the Agent/Task body was redacted — Bash was not.
# Built at runtime by concatenation so no secret-shaped literal sits in source.
BEARER_TOKEN="Zz9$(printf 'Q%.0s' $(seq 1 40))"
rm -rf "$LEARN"
run_hook "$(cat <<JSON
{"tool_name":"Bash","cwd":"$VAULT","session_id":"s","tool_call_id":"bashA",
 "tool_input":{"command":"curl -H 'Authorization: Bearer $BEARER_TOKEN' https://api.example.com/v1/widgets"},
 "tool_response":{"exitCode":22,"stderr":"curl: (22) The requested URL returned error: 401","stdout":""}}
JSON
)"
if [ "$(count_md)" = "1" ]; then
  CAP="$(find "$LEARN" -name '*.md' | head -1)"
  if grep -q '\[REDACTED-bearer\]' "$CAP"; then
    pass "(f.1) Bash argv Authorization: Bearer header is redacted"
  else
    bad "(f.1) Bash argv Bearer header redaction marker missing"
  fi
  if grep -q "$BEARER_TOKEN" "$CAP"; then
    bad "(f.2) LEAK: raw Bearer token persisted in Bash capture"
  else
    pass "(f.2) raw Bearer token NOT persisted"
  fi
else
  bad "(f) Bash exitCode!=0 was not captured ($(count_md) file(s))"
fi

# --- (g) LEAK CONTROL: Bash stderr key-shaped secret is redacted -----------
NPM_TOKEN="npm_$(printf 'B%.0s' $(seq 1 40))"
rm -rf "$LEARN"
run_hook "$(cat <<JSON
{"tool_name":"Bash","cwd":"$VAULT","session_id":"s","tool_call_id":"bashB",
 "tool_input":{"command":"npm publish"},
 "tool_response":{"exitCode":1,"stderr":"npm ERR! 403 Forbidden - token $NPM_TOKEN rejected","stdout":""}}
JSON
)"
if [ "$(count_md)" = "1" ]; then
  CAP="$(find "$LEARN" -name '*.md' | head -1)"
  if grep -q '\[REDACTED-npm-access-token\]' "$CAP"; then
    pass "(g.1) Bash stderr npm token is redacted"
  else
    bad "(g.1) Bash stderr npm token redaction marker missing"
  fi
  if grep -q "$NPM_TOKEN" "$CAP"; then
    bad "(g.2) LEAK: raw npm token persisted in Bash capture"
  else
    pass "(g.2) raw npm token NOT persisted"
  fi
else
  bad "(g) Bash exitCode!=0 was not captured ($(count_md) file(s))"
fi

# --- (h) NEGATIVE CONTROL: benign Bash failure survives byte-identical -----
# A redactor that mangles real values (paths, URLs) is its own bug.
rm -rf "$LEARN"
BENIGN_CMD="curl -sS https://api.example.com/v1/status?project=demo"
BENIGN_ERR="curl: (7) Failed to connect to api.example.com port 443: Connection refused"
run_hook "$(cat <<JSON
{"tool_name":"Bash","cwd":"$VAULT","session_id":"s","tool_call_id":"benign1",
 "tool_input":{"command":"$BENIGN_CMD"},
 "tool_response":{"exitCode":7,"stderr":"$BENIGN_ERR","stdout":""}}
JSON
)"
if [ "$(count_md)" = "1" ]; then
  CAP="$(find "$LEARN" -name '*.md' | head -1)"
  if grep -qF "$BENIGN_CMD" "$CAP" && grep -qF "$BENIGN_ERR" "$CAP"; then
    pass "(h.1) benign command + error text survive byte-identical"
  else
    bad "(h.1) benign content was altered by redaction (over-matching bug)"
  fi
  if grep -q '\[REDACTED' "$CAP"; then
    bad "(h.2) benign capture unexpectedly carries a redaction marker"
  else
    pass "(h.2) no false-positive redaction on benign content"
  fi
else
  bad "(h) benign Bash exitCode!=0 was not captured ($(count_md) file(s))"
fi

# --- (i) LEAK CONTROL: a key at the start of a line or after a colour code -
# json.dumps / repr turn a newline into a backslash + "n", and a colour code
# ends in "m"; either letter in front of a key defeats patterns anchored on a
# non-word character, so redaction must run on each string BEFORE serialization.
NPM2="npm_$(printf 'C%.0s' $(seq 1 36))"
rm -rf "$LEARN"
run_hook "$(cat <<JSON
{"tool_name":"Bash","cwd":"$VAULT","session_id":"s","tool_call_id":"bashI",
 "tool_input":{"command":"printf 'x\\n'\n$NPM2"},
 "tool_response":{"exitCode":1,"stdout":"starting\n$NPM2\n","stderr":"\u001b[32m$NPM2\u001b[0m"}}
JSON
)"
if [ "$(count_md)" = "1" ]; then
  CAP="$(find "$LEARN" -name '*.md' | head -1)"
  if grep -q "$NPM2" "$CAP"; then
    bad "(i) LEAK: a line-start or colour-prefixed key reached the capture"
  else
    pass "(i) line-start and colour-prefixed keys are redacted in every section"
  fi
else
  bad "(i) Bash exitCode!=0 was not captured ($(count_md) file(s))"
fi

# --- (j) BOUNDED: an adversarial 30 KB output cannot stall the hook ----------
ADV="$(printf 'a.%.0s' $(seq 1 15000))"
rm -rf "$LEARN"
START=$(date +%s)
run_hook "{\"tool_name\":\"Bash\",\"cwd\":\"$VAULT\",\"session_id\":\"s\",\"tool_call_id\":\"bashJ\",\"tool_input\":{\"command\":\"x\"},\"tool_response\":{\"exitCode\":1,\"stdout\":\"$ADV\",\"stderr\":\"\"}}"
ELAPSED=$(( $(date +%s) - START ))
if [ "$ELAPSED" -lt 10 ]; then
  pass "(j) 30 KB adversarial output handled in ${ELAPSED}s (was 39s)"
else
  bad "(j) redaction took ${ELAPSED}s on 30 KB of adversarial output"
fi

# --- (k) LEAK CONTROL: `tput sgr0` charset code and a gh CLI (gho_) token ---
NPM3="npm_$(printf 'D%.0s' $(seq 1 36))"
GHO="gho_$(printf 'E%.0s' $(seq 1 36))"
rm -rf "$LEARN"
run_hook "$(cat <<JSON
{"tool_name":"Bash","cwd":"$VAULT","session_id":"s","tool_call_id":"bashK",
 "tool_input":{"command":"gh api user"},
 "tool_response":{"exitCode":1,"stdout":"token: $GHO","stderr":"\u001b(B\u001b[m$NPM3"}}
JSON
)"
if [ "$(count_md)" = "1" ]; then
  CAP="$(find "$LEARN" -name '*.md' | head -1)"
  if grep -q "$NPM3" "$CAP" || grep -q "$GHO" "$CAP"; then
    bad "(k) LEAK: a key after ESC(B, or a gho_ token, reached the capture"
  else
    pass "(k) keys after a charset code and gho_ tokens are redacted"
  fi
else
  bad "(k) Bash exitCode!=0 was not captured ($(count_md) file(s))"
fi

# --- (j2) BOUNDED at the registry: every other consumer of the shared patterns
# (scrubbers, scanners) redacts without this hook's windows, so the patterns
# themselves must stay linear on a hostile "a://b:" run.
REG_SECONDS="$(python3 -c "import sys, time; sys.path.insert(0, '$ROOT/hooks'); from _lib.secret_patterns import redact; t = time.time(); redact('a://b:' * 5000); print(int(time.time() - t))")"
if [ "$REG_SECONDS" -lt 2 ]; then
  pass "(j2) the shared registry redacts 30 KB of repeated URL fragments in ${REG_SECONDS}s"
else
  bad "(j2) the shared registry took ${REG_SECONDS}s on 30 KB of repeated URL fragments"
fi

# --- (j3) BOUNDED: dropping a token cut at the window edge stays linear -------
# A long unbroken run followed by a space made a trailing-run regex quadratic
# (3.7 s via stdout, 6.4 s via a <learning> note).
RUN_A="$(printf 'a%.0s' $(seq 1 11000))"; RUN_B="$(printf 'b%.0s' $(seq 1 5000))"
rm -rf "$LEARN"
START=$(date +%s)
run_hook "{\"tool_name\":\"Bash\",\"cwd\":\"$VAULT\",\"session_id\":\"s\",\"tool_call_id\":\"bashJ3\",\"tool_input\":{\"command\":\"x\"},\"tool_response\":{\"exitCode\":1,\"stdout\":\"$RUN_A $RUN_B\",\"stderr\":\"<learning>$RUN_A $RUN_B</learning>\"}}"
ELAPSED=$(( $(date +%s) - START ))
if [ "$ELAPSED" -lt 5 ]; then  # old code: 13 s; whole-second clock on a loaded box
  pass "(j3) a long run cut at the window edge is dropped in ${ELAPSED}s"
else
  bad "(j3) dropping an edge-cut run took ${ELAPSED}s"
fi

echo
if [ "$fail" = "0" ]; then
  echo "test_post_tool_use_learnings: all assertions passed"
else
  echo "::error::test_post_tool_use_learnings: one or more assertions failed"
fi
exit "$fail"
