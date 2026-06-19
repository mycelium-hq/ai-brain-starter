#!/usr/bin/env bash
# Test: surface-connector-liveness.py — the SessionStart visible-alert half of
# the connector liveness watchdog (MYC-367).
#
# The ticket's Done criterion requires a VISIBLE alert when a connector silently
# goes empty. scripts/check-connector-liveness.py is the tested detection core;
# this hook is what actually surfaces it at session start. This test proves the
# end-to-end surface: a broken connector produces a systemMessage that names it,
# a healthy vault is silent, and the bypass env silences it.
#
# The hook reads the vault from CWD (like the sibling SessionStart hooks) and
# honors CONNECTOR_LIVENESS_NOW for a hermetic "today". Uses the PRODUCTION
# default cadences (no --config), so the fixture matches those defaults.
#
# Self-contained: tmpdir vault, no network. Exit 0 = pass.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/surface-connector-liveness.py"
if [ ! -f "$HOOK" ]; then
  echo "FAIL: surface hook not found at $HOOK" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CONNECTOR_LIVENESS_NOW="2026-06-13"

ext() { # <vault> <Source> <scope> <date> <count>
  local d="$1/External Inputs/$2/$3"
  mkdir -p "$d"
  printf -- '---\ntype: external-input\nscope: %s\ndate: %s\ncount: %s\n---\nbody\n' \
    "$3" "$4" "$5" > "$d/$4.md"
}

# run_hook <vault> -> echoes the systemMessage ("" when silent)
run_hook() {
  ( cd "$1" && printf '{}' | python3 "$HOOK" 2>/dev/null ) \
    | python3 -c "import json,sys; raw=sys.stdin.read().strip(); print(json.loads(raw).get('systemMessage','') if raw else '')"
}

# --- Assertion 1: healthy-only vault -> silent -----------------------------
VH="$TMP/healthy"
for day in 07 08 09 10 11 12; do ext "$VH" WhatsApp founders "2026-06-$day" 5; done
OUT="$(run_hook "$VH")"
if [ -n "$OUT" ]; then
  echo "FAIL(1): hook spoke for a healthy vault; got: $OUT" >&2
  exit 1
fi
echo "PASS(1): hook silent when all connectors are fresh"

# --- Assertion 2: broken connector -> systemMessage names it ---------------
VB="$TMP/broken"
for day in 07 08 09 10 11 12; do ext "$VB" WhatsApp founders "2026-06-$day" 5; done   # healthy
for day in 01 02 03 04 05 06 07 08 09; do ext "$VB" Slack eng "2026-06-$day" 7; done  # silent since 06-09
OUT="$(run_hook "$VB")"
if [ -z "$OUT" ]; then
  echo "FAIL(2): hook silent when Slack #eng is broken" >&2
  exit 1
fi
case "$OUT" in
  *slack/eng*) echo "PASS(2): hook surfaces a systemMessage naming the broken connector" ;;
  *) echo "FAIL(2): systemMessage did not name slack/eng; got: $OUT" >&2; exit 1 ;;
esac

# --- Assertion 3: healthy connector NOT named in the alert -----------------
case "$OUT" in
  *founders*) echo "FAIL(3): healthy WhatsApp falsely named in the alert; got: $OUT" >&2; exit 1 ;;
  *) echo "PASS(3): healthy connector not named" ;;
esac

# --- Assertion 4: bypass env silences the hook -----------------------------
OUT="$(CONNECTOR_LIVENESS_SURFACE_BYPASS=1 run_hook "$VB")"
if [ -n "$OUT" ]; then
  echo "FAIL(4): bypass env did not silence the hook; got: $OUT" >&2
  exit 1
fi
echo "PASS(4): CONNECTOR_LIVENESS_SURFACE_BYPASS silences the hook"

echo
echo "All assertions passed. connector-liveness SessionStart surface holds."
