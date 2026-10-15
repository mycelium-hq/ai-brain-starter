#!/usr/bin/env bash
# Fresh-install smoke for heavy_admission.py, folded into retry-budget.py
# (MYC-5053). The installer deploys hooks FLAT to ~/.claude/hooks/ and
# check-home-hook-deploy.py cannot see past a hook's first import, so this runs
# the REAL installer against a sandboxed HOME and asserts:
#   1. retry-budget.py is registered on PreToolUse(Bash) (premise for 3-4);
#   2. heavy_admission.py's whole _lib import closure ships beside it, naming
#      every missing file;
#   3. END-TO-END: with a REAL process whose argv is `.../next/dist/bin/next
#      build` (perl renamed via bash `exec -a`), the registered command DENIES
#      `next build` (rc=2) -- a missing dependency lands here as rc=0;
#   4. negative control: the same command allows `ls -la` (rc=0).
# Stdlib python3 + bash + perl (step 3 skips without perl, or off darwin/linux).
# No network. Tmpdir and plant removed on exit.
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
  [ -n "$PLANT_PID" ] && kill "$PLANT_PID" >/dev/null 2>&1 && wait "$PLANT_PID" 2>/dev/null
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

echo "=== run the REAL installer against a sandboxed HOME ==="
run_sandboxed "$TMP" "$PY" "$INSTALLER" --quiet >/dev/null 2>&1 || echo "note: installer exited $? (asserting on the result)"

ENTRY="$("$PY" - "$SETTINGS" "$GUARD" <<'PY'
import json, sys
for blk in json.load(open(sys.argv[1])).get("hooks", {}).get("PreToolUse", []):
    for e in blk.get("hooks", []):
        if sys.argv[2] in e.get("command", ""):
            print(str(blk.get("matcher")) + "\t" + e["command"])
            raise SystemExit
PY
)"
CMD="${ENTRY#*$'\t'}"

echo "=== 1. registered on PreToolUse with the Bash matcher ==="
if [ "${ENTRY%%$'\t'*}" = "Bash" ]; then
  ok "1. $GUARD registered on PreToolUse with matcher Bash"
else
  bad "1. registration" "expected a PreToolUse Bash entry, got: ${ENTRY:-<none>}"
fi

echo "=== 2. heavy_admission's import closure ships FLAT beside the hook ==="
missing=""
for f in "$GUARD" _lib/__init__.py _lib/heavy_admission.py _lib/shell_parse.py _lib/cmd_env.py _lib/guard_telemetry.py; do
  [ -f "$TMP/.claude/hooks/$f" ] || missing="$missing $f"
done
if [ -z "$missing" ]; then ok "2. $GUARD and its _lib closure ship flat"; else bad "2. flat deploy" "missing under ~/.claude/hooks:$missing"; fi

run_registered() {  # run_registered COMMAND_STRING
  "$PY" -c 'import json, sys; print(json.dumps({"session_id": "installer-smoke", "tool_name": "Bash",
    "tool_input": {"command": sys.argv[1]}, "tool_use_id": "toolu_installer_smoke"}))' "$1" \
    | run_sandboxed "$TMP" bash -c "${CMD//\[PYTHON\]/$PY}" >/dev/null 2>&1
  echo $?
}

if command -v perl >/dev/null 2>&1 && case "$(uname -s)" in Darwin|Linux) true ;; *) false ;; esac; then
  echo "=== 3. END-TO-END: a REAL next-build-shaped process + the registered command DENIES ==="
  mkdir -p "$TMP/plant" && echo 'sleep 30;' > "$TMP/plant/build"
  bash -c 'cd "$1" && exec -a "$1/next/dist/bin/next" perl build' _ "$TMP/plant" >/dev/null 2>&1 &
  PLANT_PID=$!
  sleep 1
  rc="$(run_registered 'next build')"
  [ "$rc" = "2" ] && ok "3. shipped wiring DENIES \`next build\` at cap (rc=2)" || bad "3. end-to-end deny" "rc=$rc, expected 2"
  kill "$PLANT_PID" >/dev/null 2>&1; wait "$PLANT_PID" 2>/dev/null; PLANT_PID=""
else
  echo "SKIP 3: needs perl on darwin/linux (the module admits by design elsewhere)"
fi

echo "=== 4. END-TO-END negative control: a clean Bash command is allowed ==="
rc="$(run_registered 'ls -la')"
[ "$rc" = "0" ] && ok "4. shipped wiring ALLOWS a clean command (rc=0)" || bad "4. end-to-end allow" "rc=$rc, expected 0"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
