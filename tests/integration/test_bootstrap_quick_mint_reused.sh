#!/usr/bin/env bash
# Test bootstrap.sh's handling of a quick-mint "reused" reply (MYC-5093).
#
# Bug: POST /api/install/quick-mint answers a resubmit for an email that
# already has a live install token with {ok:true, reused:true,
# resent:<bool>} and NO "token" field -- the endpoint is public and
# unauthenticated, so it deliberately never hands an existing token back
# out. The inline-mint block recognized only a 32-hex "token" field;
# anything else -- this reply included -- fell through to
# err("Inline mint failed. Falling back to form."), landing on bootstrap.sh's
# FAILED list. The end-of-run summary then told the user checks failed and a
# re-run is safe, and each re-run re-sent the welcome email until the
# per-IP cap.
#
# Covered here:
#   1. bootstrap.sh is syntactically valid (bash -n).
#   2. reused+resent=true -> warn() (never err()), TOKEN stays empty, and
#      the exact "I sent the link to your inbox again" copy prints.
#   3. reused+resent=false -> warn() (never err()), TOKEN stays empty, and
#      the exact "The link is in your inbox from last time" copy prints.
#   4. Existing first-time-token path is unchanged: a normal {ok:true,
#      token:"<32 hex>"} reply still ok()s and sets TOKEN.
#   5. Bonus: a network failure / unparseable reply (empty response) still
#      falls through to the original err() -- the new parsing did not touch
#      the failure path it wasn't meant to touch.
#   6. Bonus: Spanish copy -- LANG_CODE=es prints the ES lines for both
#      reused cases.
#   7. NEGATIVE CONTROL: the identical harness against the frozen ffddd85
#      (pre-fix) fixture must fail the way the bug actually failed -- err()
#      called once, TOKEN empty, no "reused" copy -- proving this test would
#      have caught the original bug, not just exercised dead code.
#
# The quick-mint sub-block has no function name to anchor on (it is an
# anonymous `if` nested in the signup gate), so it is extracted by awk range
# on its unique opening/closing text -- never reimplemented -- same
# technique test_bootstrap_brewless_reaches_userspace.sh uses for the
# Homebrew decision block, and the five console helpers (log/ok/warn/err/t)
# are extracted by name with the same extract_fn() every sibling bootstrap
# test uses.
#
# Self-contained; no network (curl is stubbed to serve canned JSON); never
# writes outside its own tmpdir.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/bootstrap.sh"
FIXTURE="$REPO_ROOT/tests/fixtures/bootstrap-prefix-ffddd85-quickmint.sh.txt"
[ -f "$BOOTSTRAP" ] || { echo "ERROR: $BOOTSTRAP not found" >&2; exit 1; }
[ -s "$FIXTURE" ]   || { echo "ERROR: $FIXTURE missing or empty -- without a 'before' source the negative control cannot run, and a control that cannot run must not report success" >&2; exit 1; }

fail() { echo "FAIL: $1" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ── 0. syntax ──
bash -n "$BOOTSTRAP" || fail "0: bootstrap.sh has a syntax error"

# ── extraction helpers (identical technique to
# test_bootstrap_userspace_fallback.sh's extract_fn): one-liner functions
# have no standalone '}' line, so a plain awk range would swallow every
# function up to the NEXT one that does. Try a single-line match first; fall
# back to the awk range for real multi-line functions. ──
extract_fn() {
  local name="$1" src="$2" oneliner
  oneliner="$(grep -E "^${name}\(\)[ ]*\{.*\}[ ]*\$" "$src" 2>/dev/null | head -1 || true)"
  if [ -n "$oneliner" ]; then printf '%s\n' "$oneliner"
  else awk "/^${name}\\(\\)[ ]*\\{/,/^}\$/" "$src"
  fi
}

# The EMAIL+NAME inline-mint block is anonymous, so anchor on its unique
# opening/closing text instead of a function name (same awk-range technique
# test_bootstrap_brewless_reaches_userspace.sh uses for the Homebrew
# decision block). Verified unique in bootstrap.sh: this opening line
# appears exactly once, and the closing bare "  fi" (2-space indent) is the
# first one after it -- every nested if/elif/else inside the block closes
# at 4-space or deeper.
extract_quickmint_block() {
  awk '/^  if \[\[ -z "\$\{TOKEN:-\}" && -n "\$\{EMAIL:-\}" && -n "\$\{NAME:-\}" \]\]; then$/,/^  fi$/' "$1"
}

for fn in log ok warn err t; do
  [ -n "$(extract_fn "$fn" "$BOOTSTRAP")" ] || fail "setup: $fn() not found in bootstrap.sh"
done
[ -n "$(extract_quickmint_block "$BOOTSTRAP")" ] || fail "setup: quick-mint block not found in bootstrap.sh (anchor text may have drifted)"

# ── curl stub: serves a canned JSON reply for quick-mint, ignores the
# request entirely (never touches the network). ──
build_curl_stub() { # build_curl_stub STUBDIR JSON_BODY
  local stubdir="$1" body="$2"
  cat > "$stubdir/curl" <<STUB
#!/usr/bin/env bash
printf '%s' '$body'
STUB
  chmod +x "$stubdir/curl"
}

# build_harness SRC OUT -- assembles a runnable script from the REAL (or
# frozen pre-fix) helpers + quick-mint block found in SRC.
build_harness() {
  local src="$1" out="$2"
  {
    echo 'set -uo pipefail'
    echo 'FAILED=()'
    for fn in log ok warn err t; do
      extract_fn "$fn" "$src"
    done
    extract_quickmint_block "$src"
    echo 'echo "RESULT_TOKEN=${TOKEN:-}"'
    echo 'echo "RESULT_FAILED_COUNT=${#FAILED[@]}"'
  } > "$out"
}

run_scenario() { # run_scenario STUBDIR LANG_CODE HARNESS -> combined stdout+stderr
  local stubdir="$1" lang="$2" harness="$3"
  PATH="$stubdir:$PATH" \
    EMAIL="user@example.com" NAME="Test User" LANG_HINT="$lang" LANG_CODE="$lang" \
    PY="python3" INSTALL_API_BASE="https://mycelium-ai.co" \
    bash "$harness" 2>&1
}

HARNESS="$TMP/harness.sh"
build_harness "$BOOTSTRAP" "$HARNESS"

# ── 1. reused + resent=true ──
S1="$TMP/s1"; mkdir -p "$S1"
build_curl_stub "$S1" '{"ok":true,"reused":true,"resent":true,"sideEffects":{"welcomeEmailSent":true}}'
OUT1="$(run_scenario "$S1" en "$HARNESS")"
echo "$OUT1" | grep -qF 'You already started an install with this email. I sent the link to your inbox again.' \
  || fail "1: reused+resent=true did not print the exact resent copy. Output:
$OUT1"
echo "$OUT1" | grep -q '^RESULT_FAILED_COUNT=0$' \
  || fail "1: err() was called on a reused+resent=true reply (should warn, never err). Output:
$OUT1"
echo "$OUT1" | grep -q '^RESULT_TOKEN=$' \
  || fail "1: TOKEN was set from a reused reply, which never carries a token. Output:
$OUT1"

# ── 2. reused + resent=false ──
S2="$TMP/s2"; mkdir -p "$S2"
build_curl_stub "$S2" '{"ok":true,"reused":true,"resent":false,"sideEffects":{"welcomeEmailSent":false}}'
OUT2="$(run_scenario "$S2" en "$HARNESS")"
echo "$OUT2" | grep -qF 'You already started an install with this email. The link is in your inbox from last time.' \
  || fail "2: reused+resent=false did not print the exact not-resent copy. Output:
$OUT2"
echo "$OUT2" | grep -q '^RESULT_FAILED_COUNT=0$' \
  || fail "2: err() was called on a reused+resent=false reply (should warn, never err). Output:
$OUT2"
echo "$OUT2" | grep -q '^RESULT_TOKEN=$' \
  || fail "2: TOKEN was set from a reused reply, which never carries a token. Output:
$OUT2"

# ── 3. existing first-time-token path unchanged ──
S3="$TMP/s3"; mkdir -p "$S3"
build_curl_stub "$S3" '{"ok":true,"token":"0123456789abcdef0123456789abcdef"}'
OUT3="$(run_scenario "$S3" en "$HARNESS")"
echo "$OUT3" | grep -qF 'Token minted inline. No browser needed.' \
  || fail "3: a first-time token reply no longer ok()s. Output:
$OUT3"
echo "$OUT3" | grep -q '^RESULT_FAILED_COUNT=0$' \
  || fail "3: err() was called on a normal first-time token reply. Output:
$OUT3"
echo "$OUT3" | grep -q '^RESULT_TOKEN=0123456789abcdef0123456789abcdef$' \
  || fail "3: TOKEN was not set from a normal first-time token reply. Output:
$OUT3"

# ── 4. bonus: network failure / unparseable reply is untouched ──
S4="$TMP/s4"; mkdir -p "$S4"
build_curl_stub "$S4" ''
OUT4="$(run_scenario "$S4" en "$HARNESS")"
echo "$OUT4" | grep -qF 'Inline mint failed. Falling back to form.' \
  || fail "4: an empty/failed curl reply no longer falls through to the original err(). Output:
$OUT4"
echo "$OUT4" | grep -q '^RESULT_FAILED_COUNT=1$' \
  || fail "4: an empty/failed curl reply did not land on the FAILED list exactly once. Output:
$OUT4"

# ── 5. bonus: Spanish copy ──
S5="$TMP/s5"; mkdir -p "$S5"
build_curl_stub "$S5" '{"ok":true,"reused":true,"resent":true}'
OUT5="$(run_scenario "$S5" es "$HARNESS")"
echo "$OUT5" | grep -qF 'Ya empezaste una instalación con este email. Te reenvié el link a tu bandeja de entrada.' \
  || fail "5: LANG_CODE=es did not print the Spanish resent copy. Output:
$OUT5"

S6="$TMP/s6"; mkdir -p "$S6"
build_curl_stub "$S6" '{"ok":true,"reused":true,"resent":false}'
OUT6="$(run_scenario "$S6" es "$HARNESS")"
echo "$OUT6" | grep -qF 'Ya empezaste una instalación con este email. El link está en tu bandeja de entrada de la última vez.' \
  || fail "6: LANG_CODE=es did not print the Spanish not-resent copy. Output:
$OUT6"

echo "PASS: bootstrap.sh recognizes reused/resent, warns (never errs), leaves TOKEN empty, and the token/failure/ES paths are unchanged (6 checks)"

# ── 7. NEGATIVE CONTROL: the identical harness against the frozen ffddd85
# (pre-fix) fixture must fail the way the bug actually failed. ──
#
# Provenance, not merely difference (same reasoning as
# test_bootstrap_userspace_fallback.sh's check 5): a byte-identical fixture
# would make this control compare the fix against itself and pass for the
# wrong reason.
if [ "$(cksum < "$FIXTURE")" = "$(cksum < "$BOOTSTRAP")" ]; then
  fail "7 (negative control): the pre-fix fixture is byte-identical to $BOOTSTRAP, so this control cannot fail. Restore a genuine pre-fix snapshot."
fi
# What makes this fixture pre-fix is precisely that QM_REUSED/QM_RESENT did
# not exist until this fix. If a future maintainer "refreshes" the fixture
# by re-extracting from a later bootstrap.sh, these tokens appear and this
# assertion catches it -- pointing at the fixture, not sending the next
# person to debug bootstrap.sh for a bug that isn't there.
if grep -q 'QM_REUSED\|QM_RESENT' "$FIXTURE"; then
  fail "7 (negative control): the pre-fix fixture already contains QM_REUSED/QM_RESENT, which did not exist until this fix. It was probably regenerated from post-fix source. It must stay a frozen snapshot of ffddd85, never a re-extraction from HEAD."
fi

PRE_HARNESS="$TMP/pre-harness.sh"
build_harness "$FIXTURE" "$PRE_HARNESS"
S7="$TMP/s7"; mkdir -p "$S7"
build_curl_stub "$S7" '{"ok":true,"reused":true,"resent":true,"sideEffects":{"welcomeEmailSent":true}}'
PRE_OUT="$(run_scenario "$S7" en "$PRE_HARNESS")"
echo "$PRE_OUT" | grep -qF 'Inline mint failed. Falling back to form.' \
  || fail "7 (negative control): the pre-fix source was expected to call err(\"Inline mint failed...\") on a reused reply -- this harness would NOT have caught the original bug. Output:
$PRE_OUT"
echo "$PRE_OUT" | grep -q '^RESULT_FAILED_COUNT=1$' \
  || fail "7 (negative control): the pre-fix source was expected to land the reused reply on the FAILED list exactly once. Output:
$PRE_OUT"
if echo "$PRE_OUT" | grep -qF 'already started an install'; then
  fail "7 (negative control): the pre-fix source printed the NEW reused copy -- it should have no idea what 'reused' means. Output:
$PRE_OUT"
fi

echo "PASS: negative control confirmed against the frozen pre-fix fixture (ffddd85) -- a reused reply called err() and landed on the FAILED list, exactly as the original bug did"
echo "PASS: test_bootstrap_quick_mint_reused (7 checks, negative control on the main scenario)"
