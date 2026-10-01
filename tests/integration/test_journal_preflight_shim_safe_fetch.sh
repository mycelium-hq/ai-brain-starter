#!/usr/bin/env bash
# journal-preflight must launch its message fetcher with the interpreter it is
# itself running under, never with a bare `python3` looked up on PATH.
#
# THE BUG THIS LOCKS OUT
#
# Some machines carry a `python3` shim at the FRONT of PATH (a Python-tooling
# plugin ships one for interactive sessions). It refuses exactly one invocation
# shape, `python3 <script path>`: advice on stderr, exit 1, nothing run. It
# forwards `-c`, `-m` and `-`. journal-preflight.py started
# journal-messages-fetch.py as `python3 <path>`, so on such a machine the fetch
# exited 1, the MESSAGES section of the /journal digest was the shim's advice
# text, and the marker filed `messages` under sources_failed. The same file
# already handed sys.executable to its RescueTime fetcher a few lines later, so
# it disagreed with itself. Messages are the most important context the
# preflight pulls, and the failure was one quiet section of a long digest, not
# an error anyone was shown.
#
# Controls (a harness earns trust only by FAILING on the thing it catches):
#   0. The fake shim is faithful: it refuses a script path AND forwards `-c`.
#      A shim that refused everything would not model the machine; one that
#      refused nothing would let every later assertion pass for free.
#   1. With that shim first on PATH, the shipped preflight still runs the
#      fetcher: the stub's output reaches the digest with --since/--until
#      intact, and the marker files messages under sources_pulled.
#   2. NEGATIVE: the same harness against a copy with the bare `python3` put
#      back goes red the way a real machine does: the stub never runs, the
#      shim's advice is in the digest, messages sit under sources_failed. If the
#      shipped call site is ever reshaped so this control can no longer be
#      rebuilt, the test fails loudly instead of skipping the control.
#
# Hermetic: throwaway HOME and vault. The repo's script is COPIED into the vault
# and its fetcher is a stub, so nothing real is read or written. Stdlib python
# and bash only.
#
# By hand on a machine whose own python3 is shimmed this still works: it opts in
# to lib/real_python.sh itself (a no-op wherever python3 already runs a script).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PREFLIGHT_SRC="$REPO_ROOT/scripts/journal-preflight.py"
# The home directory alone does not sandbox "~" on Windows; see lib/sandbox_home.sh.
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$SCRIPT_DIR/lib/sandbox_home.sh"
# shellcheck source=tests/integration/lib/real_python.sh
. "$SCRIPT_DIR/lib/real_python.sh"

case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*)
    echo "SKIP: the fake PATH shim is a POSIX sh script, which a native Windows interpreter cannot launch by the bare name python3"
    exit 0
    ;;
esac

PASS=0
FAIL=0
# Every check below must report exactly once. Asserted at the bottom, because
# `set -u` without `-e` lets a check that cannot EVALUATE vanish instead of
# failing. Bump this when adding a check.
EXPECTED_CHECKS=12
TMP="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP"
  if [ -n "${REAL_PYTHON_SHIM_DIR:-}" ]; then rm -rf "$REAL_PYTHON_SHIM_DIR"; fi
}
trap cleanup EXIT
ok()  { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: $2"; }

if [ ! -f "$PREFLIGHT_SRC" ]; then
  echo "FAIL  precondition :: missing $PREFLIGHT_SRC"
  exit 1
fi
ensure_real_python || { echo "FAIL  precondition :: no interpreter on this machine runs a script file"; exit 1; }
REAL_PY="$(command -v python3 || true)"
case "$REAL_PY" in
  /*) ;;
  *) echo "FAIL  precondition :: python3 did not resolve to an absolute path ([$REAL_PY])"; exit 1 ;;
esac

# --- the fake shim: three invocation forms pass through, a script path does not
FAKEBIN="$TMP/fakebin"
mkdir -p "$FAKEBIN" "$TMP/home"
cat > "$FAKEBIN/python3.in" <<'SH'
#!/bin/sh
case "${1:-}" in
  -c|-m|-) exec "__REAL_PY__" "$@" ;;
esac
echo "ERROR: Use \`uv run python $*\` instead of \`python3 $*\`" >&2
exit 1
SH
sed "s|__REAL_PY__|$REAL_PY|" "$FAKEBIN/python3.in" > "$FAKEBIN/python3"
rm -f "$FAKEBIN/python3.in"
cp "$FAKEBIN/python3" "$FAKEBIN/python"
chmod +x "$FAKEBIN/python3" "$FAKEBIN/python"
HOSTILE_PATH="$FAKEBIN:$PATH"

# --- a throwaway vault holding the shipped preflight and a stub fetcher
make_vault() {
  local v="$1"
  mkdir -p "$v/Meta/scripts"
  cp "$PREFLIGHT_SRC" "$v/Meta/scripts/journal-preflight.py"
  cat > "$v/Meta/scripts/journal-messages-fetch.py" <<'PY'
import sys
print("FETCH_STUB_RAN argv=" + " ".join(sys.argv[1:]))
PY
  # Only the messages source is on: the other sources read git, the clock, mail
  # exports and the user's real ~/.local/bin, none of which this test is about.
  cat > "$v/Meta/journal-config.md" <<'CFG'
---
data_sources:
  whatsapp_24h: on
  imessage_24h: on
  live_refresh: off
  rescuetime: off
  session_captures: off
  todays_activity: off
  email: off
  slack: off
  calendar: off
  body_health: off
---
CFG
}

SINCE="2026-09-28"
UNTIL="2026-10-01"

# Digest on stdout (stderr folded in), shim first on PATH, sandboxed HOME.
run_preflight() {
  run_sandboxed "$TMP/home" env PATH="$HOSTILE_PATH" \
    "$REAL_PY" "$1/Meta/scripts/journal-preflight.py" --since "$SINCE" --until "$UNTIL" 2>&1
}

# What the marker says about the messages source: pulled | failed | ambiguous | no-marker.
marker_verdict() {
  "$REAL_PY" - "$1/Meta/.journal-context/$UNTIL.json" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
except (OSError, ValueError):
    print("no-marker")
    raise SystemExit(0)
pulled = "messages" in d.get("sources_pulled", [])
failed = "messages" in d.get("sources_failed", [])
if pulled and not failed:
    print("pulled")
elif failed and not pulled:
    print("failed")
else:
    print("ambiguous")
PY
}

V_FIXED="$TMP/vault_shipped"
V_MUT="$TMP/vault_reverted"
make_vault "$V_FIXED"
make_vault "$V_MUT"

echo "=== 0. the fake shim models the real failure (control for the harness itself) ==="
shim_out="$(env PATH="$HOSTILE_PATH" sh -c 'python3 "$1"' _ "$V_FIXED/Meta/scripts/journal-messages-fetch.py" 2>&1)"
shim_rc=$?
if [ "$shim_rc" -ne 0 ]; then
  ok "shim refuses python3 <script path> (exit $shim_rc)"
else
  bad "shim refuses a script path" "it exited 0, so every assertion below would prove nothing"
fi
case "$shim_out" in
  *"ERROR: Use"*) ok "the refusal carries the shim's advice text" ;;
  *) bad "shim advice text" "got [$shim_out]" ;;
esac
fwd="$(env PATH="$HOSTILE_PATH" sh -c 'python3 -c "print(7)"' 2>&1)"
if [ "$fwd" = "7" ]; then
  ok "shim forwards -c (the asymmetry that hides this bug from a -c probe)"
else
  bad "shim forwards -c" "got [$fwd]"
fi

echo "=== 1. shipped preflight, shim first on PATH: the fetcher still runs ==="
out="$(run_preflight "$V_FIXED")"
rc=$?
if [ "$rc" -eq 0 ]; then ok "preflight exits 0"; else bad "preflight exit status" "rc=$rc"; fi
case "$out" in
  *"FETCH_STUB_RAN argv=--since $SINCE --until $UNTIL"*)
    ok "the fetcher ran under the shim-first PATH, since/until intact" ;;
  *)
    bad "the fetcher ran" "stub output missing from the digest. First 600 bytes: $(printf '%s' "$out" | head -c 600)" ;;
esac
case "$out" in
  *"ERROR: Use"*) bad "no shim advice in the digest" "the digest carries the shim's refusal text" ;;
  *) ok "no shim advice in the digest" ;;
esac
verdict="$(marker_verdict "$V_FIXED")"
if [ "$verdict" = "pulled" ]; then
  ok "the marker files messages under sources_pulled"
else
  bad "marker verdict" "expected pulled, got [$verdict]"
fi

echo "=== 2. NEGATIVE: put the bare python3 back and the same harness must go red ==="
sed 's/sys\.executable/"python3"/g' "$V_MUT/Meta/scripts/journal-preflight.py" > "$V_MUT/Meta/scripts/journal-preflight.py.mut" \
  && mv "$V_MUT/Meta/scripts/journal-preflight.py.mut" "$V_MUT/Meta/scripts/journal-preflight.py"
if cmp -s "$PREFLIGHT_SRC" "$V_MUT/Meta/scripts/journal-preflight.py"; then
  bad "negative control was built" "no sys.executable in the shipped preflight to revert, so the control cannot be made"
else
  ok "negative control was built (the copy differs from the shipped script)"
fi
mutant_src="$(cat "$V_MUT/Meta/scripts/journal-preflight.py")"
case "$mutant_src" in
  *'_run(["python3", fp, "--since"'*)
    ok "the reverted copy has the old call shape: _run([\"python3\", fp, \"--since\" ..." ;;
  *)
    bad "negative control shape" "the messages call no longer has the shape this control reverts; update the control together with the code" ;;
esac
mut_out="$(run_preflight "$V_MUT")"
case "$mut_out" in
  *"FETCH_STUB_RAN"*) bad "negative control: the stub must NOT run" "the reverted preflight still reached the fetcher, so the harness cannot see the defect" ;;
  *) ok "negative control: the reverted preflight never reaches the fetcher" ;;
esac
case "$mut_out" in
  *"ERROR: Use"*) ok "negative control: the digest shows the shim's advice, as on a real machine" ;;
  *) bad "negative control: shim advice" "expected the refusal text in the digest. First 600 bytes: $(printf '%s' "$mut_out" | head -c 600)" ;;
esac
mut_verdict="$(marker_verdict "$V_MUT")"
if [ "$mut_verdict" = "failed" ]; then
  ok "negative control: the marker files messages under sources_failed"
else
  bad "negative control: marker verdict" "expected failed, got [$mut_verdict]"
fi

echo
echo "=== summary: $PASS passed, $FAIL failed ==="
if [ $((PASS + FAIL)) -ne "$EXPECTED_CHECKS" ]; then
  echo "FAIL  check count :: ran $((PASS + FAIL)) checks, expected $EXPECTED_CHECKS (a check was skipped, not passed)"
  exit 1
fi
[ "$FAIL" -eq 0 ]
