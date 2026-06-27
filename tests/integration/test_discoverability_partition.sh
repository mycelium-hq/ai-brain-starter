#!/usr/bin/env bash
# test_discoverability_partition.sh — the MYC-766 ours/theirs gap partition for
# hooks/verify-discoverability-on-close.py.
#
# Bug class (MYC-766, 2026-06-10): the hook used to hard-block the close on ANY
# gap the discoverability-verifier returned — including gaps on artifacts a
# SIBLING session (or a pre-existing commit) authored. In a many-concurrent-
# session workflow that false-blocked unrelated sessions' closes, and the only
# escape was the bypass env var, which then masked the closing session's OWN
# real gaps (over-strict-verification-teaches-bypass).
#
# The fix partitions the verifier's gaps by whether THIS session's transcript
# authored the artifact (Write/Edit/MultiEdit/NotebookEdit file_path, or a
# write-style Bash command naming it):
#   - OURS   (session-authored) -> HARD-BLOCK (exit 2)
#   - THEIRS (sibling/pre-existing) -> SOFT note on stderr, NEVER block (exit 0)
#
# Self-contained: a stub verifier (injected via DISCOVERABILITY_VERIFIER_PATH)
# emits a controlled gap list read from $STUB_GAPS_FILE, so the test is
# independent of any live vault state. Exit 0 = pass.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/verify-discoverability-on-close.py"
if [ ! -f "$HOOK" ]; then
  echo "ERROR: $HOOK not found" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
VAULT="$TMP/vault"; mkdir -p "$VAULT"

# Stub verifier: ignores its args, prints whatever JSON sits in $STUB_GAPS_FILE.
STUB="$TMP/stub-verifier.py"
cat > "$STUB" <<'PY'
import os, sys
p = os.environ.get("STUB_GAPS_FILE", "")
sys.stdout.write(open(p).read() if p and os.path.exists(p) else '{"gaps": []}')
PY

# A gap whose artifact resolves (repo=vault) to $VAULT/<rel>.
gap_json() {  # rel suggestion
  python3 -c "import json,sys; print(json.dumps({'artifact':{'repo':'vault','path':sys.argv[1],'kind':'skill','commit':'abc','name':sys.argv[1]},'suggestion':sys.argv[2]}))" "$1" "$2"
}

# run_hook CLOSING_TEXT WROTE_ABS GAPS_JSON_ARRAY [EXTRA_ENV=v ...] -> exit code
run_hook() {
  local text="$1" wrote="$2" gaps="$3"; shift 3
  local tpath="$TMP/transcript.jsonl"
  # Transcript: an assistant text message (the closing claim) + a tool_use that
  # WROTE $wrote (empty string = wrote nothing this session).
  python3 -c "
import json,sys
text, wrote = sys.argv[1], sys.argv[2]
recs = [{'type':'assistant','message':{'content':[{'type':'text','text':text}]}}]
if wrote:
    recs.append({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Write','input':{'file_path':wrote}}]}})
with open(sys.argv[3],'w',encoding='utf-8') as f:
    for r in recs: f.write(json.dumps(r)+'\n')
" "$text" "$wrote" "$tpath"
  printf '{"gaps": %s}' "$gaps" > "$TMP/gaps.json"
  local stdin_json
  stdin_json=$(python3 -c "import json,sys; print(json.dumps({'transcript_path':sys.argv[1]}))" "$tpath")
  set +e
  printf '%s' "$stdin_json" | env -u DISCOVERABILITY_VERIFIER_BYPASS \
    VAULT_ROOT="$VAULT" \
    DISCOVERABILITY_VERIFIER_PATH="$STUB" \
    STUB_GAPS_FILE="$TMP/gaps.json" "$@" \
    python3 "$HOOK" >"$TMP/out.txt" 2>"$TMP/err.txt"
  local rc=$?
  set -e
  echo "$rc"
}

assert_rc() {  # label expected actual
  if [ "$2" != "$3" ]; then
    echo "FAIL: $1 — expected exit $2, got $3" >&2
    echo "  --- stderr ---" >&2; sed 's/^/  /' "$TMP/err.txt" >&2
    exit 1
  fi
  echo "PASS: $1 (exit $3)"
}

CLOSING="Closing the session now and writing the artifact."
OURS_ABS="$VAULT/skills/ours.md"
GAP_OURS="$(gap_json "skills/ours.md" "ln -sfn <dir> ~/.claude/skills/ours")"
GAP_THEIRS="$(gap_json "skills/sibling.md" "sibling session must wire this")"

# 1. Sibling-only gap (NOT authored this session) -> soft note, never block.
#    This is the MYC-766 discriminator: the pre-fix hook hard-blocked here.
rc=$(run_hook "$CLOSING" "" "[$GAP_THEIRS]")
assert_rc "sibling-only gap soft-notes, never blocks" 0 "$rc"
if ! grep -qi "non-blocking" "$TMP/err.txt"; then
  echo "FAIL: expected a non-blocking soft note for the sibling gap" >&2
  sed 's/^/  /' "$TMP/err.txt" >&2; exit 1
fi
echo "PASS: sibling gap surfaces a soft note"

# 2. Session-authored gap -> HARD-BLOCK.
rc=$(run_hook "$CLOSING" "$OURS_ABS" "[$GAP_OURS]")
assert_rc "session-authored gap hard-blocks" 2 "$rc"
if ! grep -q "BLOCKED by verify-discoverability-on-close" "$TMP/err.txt"; then
  echo "FAIL: expected the BLOCKED diagnostic for the session-authored gap" >&2
  sed 's/^/  /' "$TMP/err.txt" >&2; exit 1
fi
echo "PASS: block emits the diagnostic message"

# 3. Both gaps -> blocks (ours present), still soft-notes theirs.
rc=$(run_hook "$CLOSING" "$OURS_ABS" "[$GAP_OURS,$GAP_THEIRS]")
assert_rc "ours+theirs blocks on ours" 2 "$rc"

# 4. No gaps -> allows close.
rc=$(run_hook "$CLOSING" "" "[]")
assert_rc "no gaps allows close" 0 "$rc"

# 5. Not a closing claim -> skipped (verifier never consulted).
rc=$(run_hook "Here is the analysis you asked for." "$OURS_ABS" "[$GAP_OURS]")
assert_rc "non-closing claim skipped" 0 "$rc"

# 6. Bypass -> skipped even with an authored gap.
rc=$(run_hook "$CLOSING" "$OURS_ABS" "[$GAP_OURS]" DISCOVERABILITY_VERIFIER_BYPASS=1)
assert_rc "DISCOVERABILITY_VERIFIER_BYPASS skips" 0 "$rc"

echo
echo "All assertions passed. verify-discoverability-on-close partition (MYC-766) holds."
