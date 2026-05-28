#!/usr/bin/env bash
# Regression test for the session-coordination guard hooks:
#   hooks/check-cd-outside-worktree.py   (blocks cd into main from a worktree)
#   hooks/check-py-import-precommit.py   (blocks committing F821 / missing imports)
#   hooks/session-lock.py                (warns when two sessions share a repo)
#
# Fails on revert: if any hook's logic, bypass env, or fail-open behavior
# regresses, an assertion below flips and the script exits non-zero.
#
# Deterministic with or without ruff on PATH: the F821 block assertion is
# conditional (ruff present -> must block; absent -> must fail-open + nudge).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOKS="$REPO_ROOT/hooks"
CD_HOOK="$HOOKS/check-cd-outside-worktree.py"
PY_HOOK="$HOOKS/check-py-import-precommit.py"
LOCK_HOOK="$HOOKS/session-lock.py"

PASS=0
FAIL=0
TMPDIRS=()
cleanup() { for d in "${TMPDIRS[@]:-}"; do [ -n "$d" ] && rm -rf "$d"; done; }
trap cleanup EXIT

# run_hook <hook.py> <json-payload> [env-assignments...] ; sets RC + OUT
run_hook() {
  local hook="$1"; local json="$2"; shift 2
  OUT="$(printf '%s' "$json" | env "$@" python3 "$hook" 2>/tmp/_sc_err.$$)"
  RC=$?
  ERR="$(cat /tmp/_sc_err.$$ 2>/dev/null)"; rm -f /tmp/_sc_err.$$
  return 0
}
ok()  { PASS=$((PASS+1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL+1)); echo "FAIL  $1 :: $2"; }
assert_rc() { [ "$RC" = "$2" ] && ok "$1" || bad "$1" "rc=$RC want $2 (err=${ERR:0:80})"; }

newrepo() { local d; d="$(mktemp -d)"; TMPDIRS+=("$d"); ( cd "$d" && git init -q && git config user.email t@t.co && git config user.name t ); echo "$d"; }

echo "=== precondition: hooks exist ==="
for h in "$CD_HOOK" "$PY_HOOK" "$LOCK_HOOK"; do
  [ -f "$h" ] && ok "exists: $(basename "$h")" || bad "exists: $(basename "$h")" "missing"
done

echo "=== check-cd-outside-worktree.py ==="
WT="/tmp/sc-test-repo/.claude/worktrees/test-slug"
MAIN="/tmp/sc-test-repo"
run_hook "$CD_HOOK" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd $MAIN\"},\"cwd\":\"$WT\"}"
assert_rc "CD blocks bare cd into main from worktree" 2
run_hook "$CD_HOOK" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd $WT/src\"},\"cwd\":\"$WT\"}"
assert_rc "CD allows cd within worktree" 0
run_hook "$CD_HOOK" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd /etc\"},\"cwd\":\"/tmp/not-a-worktree\"}"
assert_rc "CD allows when session not in a worktree" 0
run_hook "$CD_HOOK" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd $MAIN\"},\"cwd\":\"$WT\"}" WORKTREE_CD_BYPASS=1
assert_rc "CD bypass env disables block" 0
run_hook "$CD_HOOK" "{ not json"
assert_rc "CD fail-open on malformed json" 0
run_hook "$CD_HOOK" "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$MAIN\"},\"cwd\":\"$WT\"}"
assert_rc "CD ignores non-Bash tool" 0

echo "=== check-py-import-precommit.py ==="
REPO="$(newrepo)"
printf 'def go():\n    return undefined_name_xyz + 1\n' > "$REPO/bad.py"
( cd "$REPO" && git add bad.py )
run_hook "$PY_HOOK" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git commit -m x\"},\"cwd\":\"$REPO\"}"
if command -v ruff >/dev/null 2>&1; then
  assert_rc "PY blocks commit with F821 (ruff present)" 2
else
  assert_rc "PY fail-open when ruff absent" 0
fi
REPO2="$(newrepo)"
printf 'import os\n\n\ndef go():\n    return os.getcwd()\n' > "$REPO2/good.py"
( cd "$REPO2" && git add good.py )
run_hook "$PY_HOOK" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git commit -m x\"},\"cwd\":\"$REPO2\"}"
assert_rc "PY allows clean commit" 0
run_hook "$PY_HOOK" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git status\"},\"cwd\":\"$REPO\"}"
assert_rc "PY ignores non-commit command" 0
run_hook "$PY_HOOK" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git commit -m x\"},\"cwd\":\"$REPO\"}" PRECOMMIT_F821_BYPASS=1
assert_rc "PY bypass env disables block" 0

echo "=== session-lock.py ==="
LREPO="$(newrepo)"
LOCKFILE="$LREPO/.claude/.session-lock.json"
run_hook "$LOCK_HOOK" "{\"hook_event_name\":\"SessionStart\",\"session_id\":\"sess-1\",\"cwd\":\"$LREPO\"}"
assert_rc "LOCK SessionStart exits 0" 0
printf '%s' "$OUT" | python3 -c 'import json,sys; json.loads(sys.stdin.read())' 2>/dev/null \
  && ok "LOCK SessionStart emits valid JSON" || bad "LOCK SessionStart emits valid JSON" "out=${OUT:0:80}"
[ -f "$LOCKFILE" ] && ok "LOCK writes lock file" || bad "LOCK writes lock file" "absent"
python3 -c "import json; assert json.load(open('$LOCKFILE'))['session_id']=='sess-1'" 2>/dev/null \
  && ok "LOCK records session_id" || bad "LOCK records session_id" "mismatch"
run_hook "$LOCK_HOOK" "{\"hook_event_name\":\"SessionStart\",\"session_id\":\"sess-2\",\"cwd\":\"$LREPO\"}"
case "$OUT" in *session-lock*sess-1*) ok "LOCK second session warns about sess-1" ;; *) bad "LOCK second session warns about sess-1" "out=${OUT:0:100}" ;; esac
run_hook "$LOCK_HOOK" "{\"hook_event_name\":\"SessionStart\",\"session_id\":\"sess-3\",\"cwd\":\"$LREPO\"}" SIBLING_SESSION_LOCK_BYPASS=1
case "$OUT" in *session-lock*) bad "LOCK bypass suppresses warn" "warned" ;; *) ok "LOCK bypass suppresses warn" ;; esac
PLAIN="$(mktemp -d)"; TMPDIRS+=("$PLAIN")
run_hook "$LOCK_HOOK" "{\"hook_event_name\":\"SessionStart\",\"session_id\":\"sx\",\"cwd\":\"$PLAIN\"}"
{ [ ! -f "$PLAIN/.claude/.session-lock.json" ] && [ "$RC" = 0 ]; } \
  && ok "LOCK no lock in non-git cwd" || bad "LOCK no lock in non-git cwd" "rc=$RC"
run_hook "$LOCK_HOOK" "}{not json"
{ [ "$RC" = 0 ] && case "$OUT" in *continue*) true;; *) false;; esac; } \
  && ok "LOCK fail-open on malformed json" || bad "LOCK fail-open on malformed json" "rc=$RC out=${OUT:0:60}"

echo ""
echo "=== SUMMARY: $PASS passed, $FAIL failed ==="
[ "$FAIL" = 0 ]
