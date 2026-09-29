#!/usr/bin/env bash
# Fresh-install smoke for heavy_admission.py, folded into retry-budget.py
# (MYC-5053). retry-budget.py's own registration is pinned by
# hooks/test_retry_budget.py (C2, C8, D2, D3); what this adds is its _lib
# dependency closure, which the installer deploys FLAT to ~/.claude/hooks/ and
# check-home-hook-deploy.py cannot see past the first import.
#
# Asserts, by running the REAL installer against a sandboxed HOME:
#   1. retry-budget.py is registered on PreToolUse(Bash) (premise for 3-4).
#   2. heavy_admission.py's whole import closure ships flat beside it. On a
#      miss this NAMES every missing file, not just "something's missing".
#   3. END-TO-END: with a REAL process running at a path ending
#      .../next/dist/bin/next, the registered command DENIES `next build`
#      (rc=2). Any missing dependency lands here too, as rc=0 (the import
#      falls back to a no-op).
#   4. END-TO-END negative control: the same command allows `ls -la` (rc=0).
#
# Step 3 plants a tiny binary COMPILED with cc, not a python interpreter with
# extra argv appended: the classifier reads a process's own argv[0], and a
# python process's argv[0] is python, never "next", regardless of what
# trailing arguments it was started with. Skips step 3 (not the whole file)
# when no C compiler is present.
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

CC="$(command -v cc || command -v gcc || true)"
if [ -n "$CC" ]; then
  mkdir -p "$TMP/plant/next/dist/bin"
  cat > "$TMP/plant/sleeper.c" <<'C'
#include <unistd.h>
int main(void) { sleep(30); return 0; }
C
  "$CC" -o "$TMP/plant/next/dist/bin/next" "$TMP/plant/sleeper.c" 2>/dev/null
fi
if [ -x "$TMP/plant/next/dist/bin/next" ]; then
  echo "=== 3. END-TO-END: a REAL next-build-shaped process + the registered command DENIES ==="
  "$TMP/plant/next/dist/bin/next" build >/dev/null 2>&1 &
  PLANT_PID=$!
  sleep 1
  rc="$(run_registered 'next build')"
  [ "$rc" = "2" ] && ok "3. shipped wiring DENIES \`next build\` at cap (rc=2)" || bad "3. end-to-end deny" "rc=$rc, expected 2"
  kill "$PLANT_PID" >/dev/null 2>&1; wait "$PLANT_PID" 2>/dev/null; PLANT_PID=""
else
  echo "SKIP 3: no C compiler available to build the plant"
fi

echo "=== 4. END-TO-END negative control: a clean Bash command is allowed ==="
rc="$(run_registered 'ls -la')"
[ "$rc" = "0" ] && ok "4. shipped wiring ALLOWS a clean command (rc=0)" || bad "4. end-to-end allow" "rc=$rc, expected 0"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
