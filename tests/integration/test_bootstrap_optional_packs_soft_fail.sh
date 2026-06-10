#!/usr/bin/env bash
# Test that failures of OPTIONAL third-party vendor packs (claude-seo, lean-ctx,
# etc.) warn instead of landing in the red "checks failed" list.
#
# Bug (MYC-739, 2026-06-09 workshop): claude-seo (an upstream marketplace-naming
# bug) and lean-ctx (a 404'd source repo) were routed through err() into the
# red FAILED list, so a non-technical installer saw "checks failed" for things
# they could do nothing about and didn't matter. The whole vendor block is
# skippable wholesale (SKIP_VENDOR_SKILLS=1), so none of its failures are
# blocking. Fix: a SOFT_FAIL=1 scope around the vendor block routes the *_safe
# helpers' failures through soft_err() -> warn().
#
# Asserts (all deterministic; no Mac/brew/network needed):
#   1. soft_err with SOFT_FAIL=1 does NOT append to FAILED (warns instead).
#   2. soft_err with SOFT_FAIL=0 DOES append to FAILED (negative control: the
#      red list still works for genuinely actionable failures).
#   3. The four install helpers route failure through soft_err, not err.
#   4. SOFT_FAIL=1 is set inside the vendor block and reset to 0 before its
#      close, and claude-seo + lean-ctx both fall inside that scope.
#
# Self-contained; never writes outside its tmpdir.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/bootstrap.sh"
[ -f "$BOOTSTRAP" ] || { echo "ERROR: $BOOTSTRAP not found" >&2; exit 1; }

fail() { echo "FAIL: $1" >&2; exit 1; }
bash -n "$BOOTSTRAP" || fail "bootstrap.sh has a syntax error"

# ── 1 + 2. behavioral: exercise the real soft_err() with stubbed deps ──
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
HARNESS="$TMP/soft.sh"
{
  echo 'FAILED=()'
  echo 'warn(){ :; }'
  echo 'err(){ FAILED+=("$*"); }'
  echo 't(){ echo "$1"; }'
  awk '/^soft_err\(\) \{/,/^\}/' "$BOOTSTRAP"
  echo 'SOFT_FAIL=1; soft_err "optional thing broke"'
  echo 'soft1=${#FAILED[@]}'
  echo 'SOFT_FAIL=0; soft_err "real thing broke"'
  echo 'soft0=${#FAILED[@]}'
  echo 'echo "SOFT1=$soft1 SOFT0=$soft0"'
} > "$HARNESS"
RES="$(bash "$HARNESS")"
echo "$RES" | grep -q "SOFT1=0" || { echo "$RES"; fail "1: SOFT_FAIL=1 still landed in FAILED (expected warn)"; }
echo "$RES" | grep -q "SOFT0=1" || { echo "$RES"; fail "2: SOFT_FAIL=0 did NOT land in FAILED (red list broken)"; }

# ── 3. the four *_safe helpers route through soft_err, not raw err ──
for helper_marker in \
  "marketplace add failed:" \
  "plugin install failed:" \
  "pipx install \$pkg failed" \
  "clone failed (exit"; do
  line="$(grep -n "$helper_marker" "$BOOTSTRAP" | head -1 || true)"
  [ -n "$line" ] || fail "3: helper failure site not found: $helper_marker"
  echo "$line" | grep -q "soft_err" || fail "3: '$helper_marker' still calls raw err (should be soft_err): $line"
done

# ── 4. claude-seo + lean-ctx fall inside a closed SOFT_FAIL=1..=0 scope ──
on_line="$(grep -n '^  SOFT_FAIL=1' "$BOOTSTRAP" | head -1 | cut -d: -f1)"
off_line="$(grep -n '^  SOFT_FAIL=0' "$BOOTSTRAP" | head -1 | cut -d: -f1)"
seo_line="$(grep -n 'AgriciDaniel/claude-seo' "$BOOTSTRAP" | head -1 | cut -d: -f1)"
lean_line="$(grep -n 'lean-ctx clone' "$BOOTSTRAP" | head -1 | cut -d: -f1)"
for v in on_line off_line seo_line lean_line; do
  [ -n "${!v}" ] || fail "4: anchor '$v' not found"
done
[ "$on_line" -lt "$off_line" ] || fail "4: SOFT_FAIL block is not closed (=1 at $on_line not before =0 at $off_line)"
[ "$on_line" -lt "$seo_line" ] && [ "$seo_line" -lt "$off_line" ] \
  || fail "4: claude-seo install ($seo_line) is not inside the SOFT_FAIL scope ($on_line..$off_line)"
[ "$on_line" -lt "$lean_line" ] && [ "$lean_line" -lt "$off_line" ] \
  || fail "4: lean-ctx clone ($lean_line) is not inside the SOFT_FAIL scope ($on_line..$off_line)"

echo "PASS: optional vendor-pack failures soft-fail (warn), red list reserved for actionable failures (test_bootstrap_optional_packs_soft_fail)"
