#!/usr/bin/env bash
# Fresh-install smoke for heavy_admission.py, folded into retry-budget.py
# (MYC-5053).
#
# retry-budget.py is a PRE-EXISTING registered hook; this is not proving a
# NEW registration, it is proving the DEPENDENCY (hooks/_lib/heavy_admission.py)
# ships with its consumer and actually activates on a fresh install --
# ARTIFACT-WITHOUT-ACTIVATION's sibling bug, a hook importing a `_lib` module
# that install.sh never copies. File presence is therefore NOT the
# assertion -- registration in the installed settings.json is, plus proof
# the registered command actually DENIES a seeded heavy command.
#
# Asserts, by running the REAL installer against a sandboxed HOME:
#   0. NEGATIVE CONTROL: a pre-install settings.json has no retry-budget.py.
#   1. retry-budget.py is registered on PreToolUse(Bash) after install.
#   2. Both the registered script AND hooks/_lib/heavy_admission.py exist at
#      the installed path -- the dependency shipped with its consumer.
#   3. The command uses the `if [ -f ] && [ -r ]` form, not `2>/dev/null || echo <allow>`.
#   4. END-TO-END: with a real `node .../next/dist/bin/next build`-argv
#      process planted, the registered command DENIES `next build` (rc=2).
#   5. END-TO-END negative control: the same command allows `ls -la` (rc=0).
#   6. Idempotent: a second install does not duplicate the entry.
#
# Stdlib python3 + bash. No network. Tmpdir and planted process removed on exit.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALLER="$REPO_ROOT/scripts/install-hooks-user-level.py"
GUARD="retry-budget.py"

# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$REPO_ROOT/tests/integration/lib/sandbox_home.sh"

PASS=0; FAIL=0
TMP="$(mktemp -d)"
PLANT_PID=""
cleanup() {
  [ -n "$PLANT_PID" ] && kill "$PLANT_PID" >/dev/null 2>&1
  [ -n "$PLANT_PID" ] && wait "$PLANT_PID" 2>/dev/null
  rm -rf "$TMP"
}
trap cleanup EXIT
ok()  { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: $2"; }

PY=""
for c in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
  [ -x "$c" ] && "$c" -c 'import sys' >/dev/null 2>&1 && { PY="$c"; break; }
done
if [ -z "$PY" ]; then
  PY="$(command -v python3 || true)"
  [ -n "$PY" ] && ! "$PY" -c 'import sys' >/dev/null 2>&1 && PY=""
fi
[ -z "$PY" ] && { echo "SKIP: no usable python3"; exit 0; }

mkdir -p "$TMP/.claude/skills"
cp -R "$REPO_ROOT" "$TMP/.claude/skills/ai-brain-starter"
SETTINGS="$TMP/.claude/settings.json"
echo '{}' > "$SETTINGS"

registered_entries() {
  "$PY" - "$SETTINGS" "$1" <<'PY'
import json, sys
settings, needle = sys.argv[1], sys.argv[2]
try:
    hooks = json.load(open(settings)).get("hooks", {})
except Exception:
    hooks = {}
for event, blocks in hooks.items():
    for blk in blocks:
        for e in blk.get("hooks", []):
            cmd = e.get("command", "")
            if needle in cmd:
                print(event + "\t" + str(blk.get("matcher")) + "\t" + cmd)
PY
}

echo "=== 0. NEGATIVE CONTROL: guard absent before install ==="
if [ -z "$(registered_entries "$GUARD")" ]; then
  ok "guard not registered pre-install (control holds)"
else
  bad "pre-install control" "already present — the test cannot prove activation"
fi

echo "=== run the REAL installer against a sandboxed HOME ==="
run_sandboxed "$TMP" "$PY" "$INSTALLER" --quiet >/dev/null 2>&1
inst_rc=$?
if [ "$inst_rc" -ne 0 ]; then
  echo "note: installer exited $inst_rc (asserting on resulting settings.json)"
fi

ENTRIES="$(registered_entries "$GUARD")"

echo "=== 1. registered on PreToolUse with the Bash matcher ==="
MATCHER="$(printf '%s\n' "$ENTRIES" | awk -F'\t' '$1=="PreToolUse"{print $2; exit}')"
if [ "$MATCHER" = "Bash" ]; then
  ok "1. $GUARD registered on PreToolUse with matcher Bash"
else
  bad "1. registration" "PreToolUse matcher is '${MATCHER:-<none>}', expected Bash: ${ENTRIES:-<none>}"
fi

echo "=== 2. the FLAT-deployed script AND its _lib dependency exist ==="
# retry-budget.py is a HOME_HOOKS_INSTALLER_DEPLOYS hook: the registered
# command reads ~/.claude/hooks/retry-budget.py, not the skills/ mirror
# (which a bare `cp -R` of the whole repo would satisfy trivially and prove
# nothing). Its _lib deps ship the same way, individually -- this is the
# exact path a `HOME_HOOKS_LIB_DEPS` omission leaves silently empty.
INSTALLED_HOOK="$TMP/.claude/hooks/$GUARD"
INSTALLED_LIB="$TMP/.claude/hooks/_lib/heavy_admission.py"
INSTALLED_SHELL_PARSE="$TMP/.claude/hooks/_lib/shell_parse.py"
if [ -f "$INSTALLED_HOOK" ] && [ -f "$INSTALLED_LIB" ] && [ -f "$INSTALLED_SHELL_PARSE" ]; then
  ok "2. $GUARD and its _lib deps (heavy_admission.py, shell_parse.py) ship flat"
else
  bad "2. script path" "hook=$([ -f "$INSTALLED_HOOK" ] && echo yes || echo no) heavy_admission=$([ -f "$INSTALLED_LIB" ] && echo yes || echo no) shell_parse=$([ -f "$INSTALLED_SHELL_PARSE" ] && echo yes || echo no)"
fi

echo "=== 3. wired in the block-preserving form ==="
CMD="$(printf '%s\n' "$ENTRIES" | head -1 | cut -f3-)"
if printf '%s' "$CMD" | grep -q 'if \[ -f ' && printf '%s' "$CMD" | grep -q '\[ -r ' && ! printf '%s' "$CMD" | grep -q '2>/dev/null ||'; then
  ok "3. uses the \`if [ -f ] && [ -r ]\` form (exit 2 + stderr survive)"
else
  bad "3. wiring form" "a blocking hook wired without -r or with '2>/dev/null || echo allow' is inert or unsafe: $CMD"
fi

run_registered() {  # run_registered COMMAND_STRING
  payload="$("$PY" - "$1" <<'PY'
import json, sys
print(json.dumps({"session_id": "installer-smoke", "hook_event_name": "PreToolUse",
                   "tool_name": "Bash", "tool_input": {"command": sys.argv[1]},
                   "tool_use_id": "toolu_installer_smoke"}))
PY
)"
  printf '%s' "$payload" | run_sandboxed "$TMP" bash -c "${CMD//\[PYTHON\]/$PY}" >/dev/null 2>&1
  echo $?
}

echo "=== 4. END-TO-END: a planted next-build process + the registered command DENIES ==="
"$PY" -c "import time; time.sleep(30)" node /fake/path/next/dist/bin/next build >/dev/null 2>&1 &
PLANT_PID=$!
sleep 1
rc="$(run_registered 'next build')"
if [ "$rc" = "2" ]; then
  ok "4. shipped wiring DENIES \`next build\` at cap (rc=2)"
else
  bad "4. end-to-end deny" "registered command returned rc=$rc, expected 2"
fi
kill "$PLANT_PID" >/dev/null 2>&1
wait "$PLANT_PID" 2>/dev/null
PLANT_PID=""

echo "=== 5. END-TO-END negative control: a clean Bash command is allowed ==="
rc="$(run_registered 'ls -la')"
if [ "$rc" = "0" ]; then
  ok "5. shipped wiring ALLOWS a clean command (rc=0)"
else
  bad "5. end-to-end allow" "registered command returned rc=$rc on a clean command, expected 0"
fi

echo "=== 6. idempotent: a second install does not duplicate ==="
before="$(registered_entries "$GUARD" | wc -l | tr -d ' ')"
run_sandboxed "$TMP" "$PY" "$INSTALLER" --quiet >/dev/null 2>&1
after="$(registered_entries "$GUARD" | wc -l | tr -d ' ')"
if [ "$before" = "$after" ]; then
  ok "6. second install did not duplicate the entry ($after)"
else
  bad "6. idempotency" "entries went $before -> $after"
fi

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
