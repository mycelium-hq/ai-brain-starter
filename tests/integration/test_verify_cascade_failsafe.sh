#!/usr/bin/env bash
# Test: verify-session-close-cascade.py is FAIL-SAFE and only hard-blocks when
# the session-close cascade is actually installed in the vault.
#
# Bug class: the hook is a hard-block Stop hook whose gate 2 requires a fresh
# /tmp/abs-session-close-runner.report. If session-close-runner.sh is NOT
# installed in the vault, that report can never exist, so gate 2 is permanently
# failed — the hook would block EVERY session close forever. The fix makes
# enforcement CONDITIONAL on the runner being installed: no runner -> never
# block (advisory at most); runner present -> full three-gate hard-block.
#
# Assertions (the matrix the follow-up brief asked for + the override knobs):
#   1. fresh vault (no Meta)                  -> never blocks            (exit 0)
#   2. runner absent (Meta but no runner)     -> never blocks            (exit 0)
#   3. runner present + incomplete cascade    -> BLOCKS                  (exit 2)
#   4. runner present + all three gates pass  -> allows close           (exit 0)
#   5. runner present + VERIFY_CASCADE_SOFT=1 -> advisory, never blocks  (exit 0)
#   6. runner present + VERIFY_CASCADE_BYPASS -> skipped entirely        (exit 0)
#   7. not a closing claim                    -> skipped                 (exit 0)
#   8. closing claim outside a worktree       -> skipped                 (exit 0)
#   9. runner absent + uncommitted artifacts  -> advisory WARNING        (exit 0)
#      (also exercises a PLAIN "Meta" vault, proving META_NAME parametrization)
#
# Self-contained: tmpdir fake vaults, ABS_RUNNER_REPORT redirected into the
# tmpdir so the shared /tmp report is never touched. Exit 0 = pass.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/verify-session-close-cascade.py"
if [ ! -f "$HOOK" ]; then
  echo "ERROR: $HOOK not found" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
REPORT="$TMP/runner.report"
TODAY="$(date +%Y-%m-%d)"

# run_hook VAULT CWD TEXT [EXTRA_ENV=val ...] -> echoes the hook's exit code.
# stdout/stderr land in $TMP/out.txt / $TMP/err.txt for inspection.
run_hook() {
  local vault="$1" cwd="$2" text="$3"; shift 3
  local tpath="$TMP/transcript.jsonl"
  python3 -c "import json,sys; open(sys.argv[1],'w',encoding='utf-8').write(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':sys.argv[2]}]}})+'\n')" "$tpath" "$text"
  local stdin_json
  stdin_json=$(python3 -c "import json,sys; print(json.dumps({'cwd':sys.argv[1],'transcript_path':sys.argv[2]}))" "$cwd" "$tpath")
  set +e
  printf '%s' "$stdin_json" | env -u VERIFY_CASCADE_BYPASS -u VERIFY_CASCADE_SOFT \
    VAULT_ROOT="$vault" ABS_RUNNER_REPORT="$REPORT" "$@" \
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

CLOSING="Closing the session now — that's all for today."
WORKTREE_CWD() { echo "$1/.claude/worktrees/$2"; }

# --- Fixtures -------------------------------------------------------------
# Fresh vault: nothing.
VFRESH="$TMP/fresh"; mkdir -p "$VFRESH"
# Runner-absent: decorated Meta exists, but no session-close-runner.sh.
VNORUN="$TMP/norunner"; mkdir -p "$VNORUN/⚙️ Meta/Sessions"
# Runner-present: the cascade is installed.
VRUN="$TMP/runner"; mkdir -p "$VRUN/⚙️ Meta/scripts" "$VRUN/⚙️ Meta/Sessions"
: > "$VRUN/⚙️ Meta/scripts/session-close-runner.sh"
# Runner-present + all gates satisfied (git-clean, session file, fresh report).
VPASS="$TMP/pass"; mkdir -p "$VPASS/⚙️ Meta/scripts" "$VPASS/⚙️ Meta/Sessions"
: > "$VPASS/⚙️ Meta/scripts/session-close-runner.sh"
echo "session" > "$VPASS/⚙️ Meta/Sessions/${TODAY}T120000-slugpass.md"
git -C "$VPASS" init -q
git -C "$VPASS" -c user.email=t@t -c user.name=t add -A
git -C "$VPASS" -c user.email=t@t -c user.name=t commit -qm init
# Advisory: PLAIN "Meta" vault (ASCII), git repo, no runner, uncommitted session
# artifact -> proves the advisory warning path + plain-Meta parametrization.
# Commit a skeleton FIRST so the repo has tracked history; otherwise an
# entirely-untracked tree collapses to "?? Meta/" under `git status --short`
# (real vaults always have history, so a new session file shows individually).
VADV="$TMP/advisory"; mkdir -p "$VADV/Meta/Sessions"
git -C "$VADV" init -q
: > "$VADV/Meta/Sessions/.gitkeep"
git -C "$VADV" -c user.email=t@t -c user.name=t add -A
git -C "$VADV" -c user.email=t@t -c user.name=t commit -qm init
echo "session" > "$VADV/Meta/Sessions/${TODAY}T120000-slugadv.md"   # left untracked

# --- 1. fresh vault: never blocks ----------------------------------------
rm -f "$REPORT"
rc=$(run_hook "$VFRESH" "$(WORKTREE_CWD "$VFRESH" slug1)" "$CLOSING")
assert_rc "fresh vault never blocks" 0 "$rc"

# --- 2. runner absent: never blocks (even with no session file) -----------
rc=$(run_hook "$VNORUN" "$(WORKTREE_CWD "$VNORUN" slug1)" "$CLOSING")
assert_rc "runner absent never blocks" 0 "$rc"

# --- 3. runner present + incomplete cascade: BLOCKS -----------------------
rm -f "$REPORT"   # gate 2: no fresh report
rc=$(run_hook "$VRUN" "$(WORKTREE_CWD "$VRUN" slug1)" "$CLOSING")
assert_rc "runner present + incomplete cascade blocks" 2 "$rc"
if ! grep -q "BLOCKED by verify-session-close-cascade" "$TMP/err.txt"; then
  echo "FAIL: block message missing from stderr" >&2; exit 1
fi
echo "PASS: block emits the diagnostic message"

# --- 4. runner present + all three gates pass: allows close ---------------
# Fresh report with a no-colon %z offset — also exercises the offset-normalize fix.
printf 'RUNNER COMPLETE @ %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" > "$REPORT"
rc=$(run_hook "$VPASS" "$(WORKTREE_CWD "$VPASS" slugpass)" "$CLOSING")
assert_rc "runner present + all gates pass allows close" 0 "$rc"

# --- 5. runner present + SOFT: advisory, never blocks ---------------------
rm -f "$REPORT"
rc=$(run_hook "$VRUN" "$(WORKTREE_CWD "$VRUN" slug1)" "$CLOSING" VERIFY_CASCADE_SOFT=1)
assert_rc "VERIFY_CASCADE_SOFT never blocks" 0 "$rc"

# --- 6. runner present + BYPASS: skipped entirely -------------------------
rc=$(run_hook "$VRUN" "$(WORKTREE_CWD "$VRUN" slug1)" "$CLOSING" VERIFY_CASCADE_BYPASS=1)
assert_rc "VERIFY_CASCADE_BYPASS skips" 0 "$rc"

# --- 7. not a closing claim: skipped --------------------------------------
rc=$(run_hook "$VRUN" "$(WORKTREE_CWD "$VRUN" slug1)" "Here is the analysis you requested.")
assert_rc "non-closing claim skipped" 0 "$rc"

# --- 8. closing claim outside a worktree: skipped -------------------------
rc=$(run_hook "$VRUN" "$VRUN" "$CLOSING")
assert_rc "closing claim outside worktree skipped" 0 "$rc"

# --- 9. runner absent + uncommitted artifacts: advisory WARNING -----------
rc=$(run_hook "$VADV" "$(WORKTREE_CWD "$VADV" slugadv)" "$CLOSING")
assert_rc "advisory mode never blocks on uncommitted artifacts" 0 "$rc"
if ! grep -qi "advisory" "$TMP/err.txt"; then
  echo "FAIL: expected an advisory warning about uncommitted artifacts" >&2
  echo "  --- stderr ---" >&2; sed 's/^/  /' "$TMP/err.txt" >&2
  exit 1
fi
echo "PASS: advisory mode surfaces uncommitted artifacts without blocking"

echo
echo "All assertions passed. verify-session-close-cascade.py fail-safe holds."
