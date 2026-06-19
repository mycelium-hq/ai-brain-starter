#!/usr/bin/env bash
# Test: check-connector-liveness.py — the connector liveness watchdog (MYC-367).
#
# Bug class: SILENT-EMPTY-CONNECTOR (the "0-vs-0" gap). A connector (Granola,
# WhatsApp, iMessage, Slack, Gmail) silently returns 0 items after a vendor
# changes a surface. The launchd exit-status watchdog catches NON-zero exits but
# not "returns 0 when it should return >0." Origin: granola_export returned 0
# transcripts for ~3 weeks after Granola changed its local storage; exit code
# stayed 0 and nobody noticed.
#
# This is the NEGATIVE-CONTROL test the ticket's Done criterion requires: point
# connectors at stale/empty sources and confirm the alert fires within one
# expected-cadence window — AND confirm a connector that is merely IDLE (silent,
# but within its own demonstrated rhythm) does NOT raise a false alarm. That
# second half is the whole point: distinguish "0 because nothing happened" from
# "0 because the source broke."
#
# Signal source: connectors already persist their runs. WhatsApp/iMessage/Slack/
# Gmail write External Inputs/<Source>/<scope>/<YYYY-MM-DD>.md with a *count*
# frontmatter key; Granola writes Meeting Notes/<YYYY-MM-DD> - <title> -
# Transcript.md. The watchdog reads that history — no live credential-gated
# probe (which would soft-pass forever).
#
# Determinism: the script takes --now <YYYY-MM-DD> (the time seam) and --config
# (per-source cadence floors) so this test is hermetic and not coupled to the
# wall clock or the production default cadences.
#
# Assertions:
#   1. Empty vault (no connectors) -> SKIP_NO_CONNECTORS, exit 0.
#   2. Only-healthy vault -> OK_ALL_FRESH, exit 0.
#   3. A regular connector gone silent past one window -> CONNECTOR_GAP, exit 1.
#   4. A within-window connector is NOT flagged (no false positive).
#   5. A sparse-but-on-rhythm connector is NOT flagged (idle != broke).
#   6. Granola gone silent past its window IS flagged (the origin incident).
#   7. A connector still RUNNING but returning count:0 after a regular history
#      IS flagged (the literal 0-vs-0 gap).
#
# Self-contained: tmpdir fake vault, no network, no MCP. Exit 0 = pass.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/check-connector-liveness.py"
if [ ! -f "$SCRIPT" ]; then
  echo "FAIL: watchdog script not found at $SCRIPT" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

NOW="2026-06-13"
CONFIG="$TMP/cadence.json"
cat > "$CONFIG" <<'JSON'
{ "cadence_days": {
    "slack": 2, "whatsapp": 3, "imessage": 3, "gmail": 2, "granola": 3
} }
JSON

# write an External Inputs day-file with a given item count
ext() { # <vault> <Source> <scope> <date> <count>
  local d="$1/External Inputs/$2/$3"
  mkdir -p "$d"
  cat > "$d/$4.md" <<EOF
---
type: external-input
scope: $3
date: $4
count: $5
ingested_at: ${4}T09:00:00-05:00
---
body
EOF
}

# write a Granola transcript file for a date
granola() { # <vault> <date> <title>
  local d="$1/📝 Meeting Notes"
  mkdir -p "$d"
  echo "transcript" > "$d/$2 - $3 - Transcript.md"
}

run() { # <vault> -> porcelain stdout; also captures exit code in RC
  set +e
  OUT="$(python3 "$SCRIPT" --porcelain --now "$NOW" --config "$CONFIG" "$1" 2>/dev/null)"
  RC=$?
  set -e
}

# --- Assertion 1: empty vault -> SKIP --------------------------------------
V1="$TMP/v1"; mkdir -p "$V1"
run "$V1"
if [ "$RC" != 0 ] || [ "${OUT%%$'\n'*}" != "SKIP_NO_CONNECTORS" ]; then
  echo "FAIL(1): empty vault should SKIP_NO_CONNECTORS exit 0; got rc=$RC out=[$OUT]" >&2
  exit 1
fi
echo "PASS(1): empty vault -> SKIP_NO_CONNECTORS"

# --- Assertion 2: only-healthy vault -> OK ---------------------------------
V2="$TMP/v2"; mkdir -p "$V2"
# WhatsApp founders: data every day up to the day before NOW -> silence 1 day
for day in 07 08 09 10 11 12; do ext "$V2" WhatsApp founders "2026-06-$day" 5; done
run "$V2"
if [ "$RC" != 0 ] || [ "${OUT%%$'\n'*}" != "OK_ALL_FRESH" ]; then
  echo "FAIL(2): healthy vault should be OK_ALL_FRESH exit 0; got rc=$RC out=[$OUT]" >&2
  exit 1
fi
echo "PASS(2): only-healthy vault -> OK_ALL_FRESH"

# --- Build the full mixed fixture for assertions 3-7 -----------------------
V="$TMP/v"; mkdir -p "$V"

# (3) Slack #eng: regular daily, last data 06-09, now 06-13 -> silent 4 > 2 (BROKE)
for day in 01 02 03 04 05 06 07 08 09; do ext "$V" Slack eng "2026-06-$day" 7; done

# (4) iMessage family: regular daily through 06-12 -> silent 1 (HEALTHY, within window)
for day in 06 07 08 09 10 11 12; do ext "$V" iMessage family "2026-06-$day" 3; done

# (5) Gmail newsletters: sparse but on a ~15-day rhythm; last data 05-31 ->
#     silent 13 days, but its own max gap is 15 -> NOT overdue (IDLE, not broke)
ext "$V" Gmail newsletters "2026-05-01" 2
ext "$V" Gmail newsletters "2026-05-16" 2
ext "$V" Gmail newsletters "2026-05-31" 2

# (6) Granola: regular every ~2 days, last 06-08, now 06-13 -> silent 5 > 3 (BROKE)
granola "$V" "2026-06-02" "Standup"
granola "$V" "2026-06-04" "Design sync"
granola "$V" "2026-06-06" "Roadmap"
granola "$V" "2026-06-08" "1-on-1"

# (7) Slack #marketing: regular data 06-01..06-05, then STILL RUNNING but
#     returning count:0 every day 06-06..06-12 -> last *data* 06-05, silent 8
#     > 2 (the literal 0-vs-0: connector alive, source went empty) (BROKE)
for day in 01 02 03 04 05; do ext "$V" Slack marketing "2026-06-$day" 4; done
for day in 06 07 08 09 10 11 12; do ext "$V" Slack marketing "2026-06-$day" 0; done

run "$V"

# Assertion 3: the broken connectors must flag with non-zero exit
if [ "$RC" = 0 ]; then
  echo "FAIL(3): expected non-zero exit when connectors are broken; out=[$OUT]" >&2
  exit 1
fi
case "$OUT" in
  *CONNECTOR_GAP:slack:eng:*) echo "PASS(3): broken Slack #eng flagged" ;;
  *) echo "FAIL(3): Slack #eng (silent 4d, daily rhythm) not flagged; out=[$OUT]" >&2; exit 1 ;;
esac

# Assertion 4: the within-window connector must NOT be flagged
case "$OUT" in
  *imessage:family*) echo "FAIL(4): healthy within-window iMessage falsely flagged; out=[$OUT]" >&2; exit 1 ;;
  *) echo "PASS(4): healthy iMessage not flagged" ;;
esac

# Assertion 5: the sparse-but-on-rhythm connector must NOT be flagged
case "$OUT" in
  *gmail:newsletters*) echo "FAIL(5): idle sparse Gmail falsely flagged (idle != broke); out=[$OUT]" >&2; exit 1 ;;
  *) echo "PASS(5): sparse-on-rhythm Gmail not flagged (idle distinguished from broke)" ;;
esac

# Assertion 6: Granola (the origin incident) must be flagged
case "$OUT" in
  *CONNECTOR_GAP:granola:*) echo "PASS(6): silent Granola flagged (origin incident covered)" ;;
  *) echo "FAIL(6): Granola (silent 5d, ~2d rhythm) not flagged; out=[$OUT]" >&2; exit 1 ;;
esac

# Assertion 7: the 0-vs-0 case (running but returning 0) must be flagged
case "$OUT" in
  *CONNECTOR_GAP:slack:marketing:*) echo "PASS(7): 0-vs-0 Slack #marketing flagged (returns 0 when it should return >0)" ;;
  *) echo "FAIL(7): Slack #marketing (running but count:0 after regular data) not flagged; out=[$OUT]" >&2; exit 1 ;;
esac

echo
echo "All assertions passed. connector-liveness watchdog invariant holds."
