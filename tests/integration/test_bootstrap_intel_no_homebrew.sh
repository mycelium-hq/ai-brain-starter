#!/usr/bin/env bash
# An Intel Mac without Homebrew must not be sent to Homebrew (tickets#6174).
#
# Homebrew's installer now aborts on any Mac whose `uname -m` is not arm64, with
# no override. So on an Intel Mac with no brew, bootstrap.sh must print one
# warning, show no "TERMINAL STEP NEEDED" block, never run the Homebrew
# installer (dry-run included), and carry on to the user-space installs.
#
# Runs the REAL Homebrew decision block extracted from bootstrap.sh, with uname
# stubbed to Darwin/x86_64 and curl stubbed to record any call (the Homebrew
# installer is fetched with curl). An Apple Silicon control proves the existing
# behavior is untouched. No network; never writes outside its tmpdir.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/bootstrap.sh"
[ -f "$BOOTSTRAP" ] || { echo "ERROR: $BOOTSTRAP not found" >&2; exit 1; }
fail() { echo "FAIL: $1" >&2; exit 1; }

bash -n "$BOOTSTRAP" || fail "bootstrap.sh has a syntax error"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

extract_fn() {
  local name="$1" oneliner
  oneliner="$(grep -E "^${name}\(\)[ ]*\{.*\}[ ]*\$" "$BOOTSTRAP" 2>/dev/null | head -1 || true)"
  if [ -n "$oneliner" ]; then printf '%s\n' "$oneliner"
  else awk "/^${name}\\(\\)[ ]*\\{/,/^}\$/" "$BOOTSTRAP"
  fi
}

# stubs: uname (arch under test), curl (records a call instead of fetching)
build_stubs() {
  local dir="$1" arch="$2"
  mkdir -p "$dir"
  cat > "$dir/uname" <<STUB
#!/usr/bin/env bash
case "\$1" in
  -s) echo Darwin ;;
  -m) echo $arch ;;
  *) exec /usr/bin/uname "\$@" ;;
esac
STUB
  cat > "$dir/curl" <<STUB
#!/usr/bin/env bash
echo "\$*" >> "$dir/curl-calls"
exit 1
STUB
  chmod +x "$dir/uname" "$dir/curl"
}

# harness: real helpers + the real Homebrew decision block + a reached-end marker
build_harness() {
  local out="$1" dry="$2"
  {
    echo 'set -uo pipefail'
    echo 'HOME="'"$TMP"'/home"; SHELL=/bin/bash; FAILED=(); LANG_CODE=en; CORPORATE_PROFILE=0'
    echo "DRY_RUN=$dry"
    echo 't() { [ "$LANG_CODE" = es ] && echo "$2" || echo "$1"; }'
    for fn in log ok warn err hdr dry is_mac is_linux have; do extract_fn "$fn"; done
    echo 'SKILL_DIR="'"$TMP"'/home/.claude/skills/ai-brain-starter"'
    extract_fn print_terminal_step
    awk '/^if is_mac && ! have brew && /,/^fi$/' "$BOOTSTRAP"
    echo 'echo "RESULT_REACHED_END=1"'
  } > "$out"
}

run_case() { # run_case NAME ARCH DRY -> sets OUT, CURL_CALLS
  local name="$1" arch="$2" dry="$3" dir="$TMP/$1"
  build_stubs "$dir" "$arch"
  build_harness "$dir/harness.sh" "$dry"
  set +e
  OUT="$(PATH="$dir:/usr/bin:/bin" bash "$dir/harness.sh" < /dev/null 2>&1)"
  CODE=$?
  set -e
  CURL_CALLS="$(cat "$dir/curl-calls" 2>/dev/null || true)"
}

for dry in 0 1; do
  run_case "intel-dry$dry" x86_64 "$dry"
  [ "$CODE" -eq 0 ] || fail "intel dry=$dry: harness exited $CODE. Output: $OUT"
  echo "$OUT" | grep -q '^RESULT_REACHED_END=1$' || fail "intel dry=$dry: run did not continue past the Homebrew section. Output: $OUT"
  echo "$OUT" | grep -qi "Intel" || fail "intel dry=$dry: no Intel warning printed. Output: $OUT"
  echo "$OUT" | grep -qi "TERMINAL STEP NEEDED" && fail "intel dry=$dry: sent the person to a Terminal step. Output: $OUT"
  echo "$OUT" | grep -qi "install Homebrew" && fail "intel dry=$dry: planned a Homebrew install. Output: $OUT"
  [ -z "$CURL_CALLS" ] || fail "intel dry=$dry: reached for the Homebrew installer: $CURL_CALLS"
done
echo "PASS: Intel Mac without brew gets the warning, no Terminal step, no Homebrew installer (real and dry-run)"

# control: Apple Silicon behavior is unchanged (non-interactive prints the Terminal step)
run_case "arm-dry0" arm64 0
echo "$OUT" | grep -qi "TERMINAL STEP NEEDED" || fail "control: Apple Silicon no longer gets the Terminal step. Output: $OUT"
echo "$OUT" | grep -qi "Intel" && fail "control: Apple Silicon got the Intel warning. Output: $OUT"
echo "PASS: Apple Silicon control unchanged"
