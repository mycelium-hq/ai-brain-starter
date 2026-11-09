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
# installer is fetched with curl), both as Claude Code runs it (no TTY) and as a
# person runs it in Terminal (a pty: the interactive branch, the one that calls
# the installer). Apple Silicon controls prove the existing behavior is untouched
# and that the pty case really reaches that branch. No network; never writes
# outside its tmpdir.

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
    echo 'HOME="'"$TMP"'/home"; USERPROFILE="'"$TMP"'/home"; SHELL=/bin/bash; FAILED=(); LANG_CODE=en; CORPORATE_PROFILE=0'
    echo "DRY_RUN=$dry"
    echo 't() { [ "$LANG_CODE" = es ] && echo "$2" || echo "$1"; }'
    for fn in log ok warn err hdr dry is_mac is_linux have; do extract_fn "$fn"; done
    echo 'SKILL_DIR="'"$TMP"'/home/.claude/skills/ai-brain-starter"'
    extract_fn print_terminal_step
    awk '/^if is_mac && ! have brew && /,/^fi$/' "$BOOTSTRAP"
    echo 'echo "RESULT_REACHED_END=1"'
  } > "$out"
}

# A pty from python3 makes [[ -t 0 ]] true inside the harness on macOS and Linux
# alike. Resolve the real interpreter first (`-c` passes through PATH shims).
# Not pty.spawn: on Python 3.9 (Xcode's python3) its copy loop never returns
# once stdin is at EOF, so read the pty ourselves, with a timeout.
PY3="$(python3 -c 'import sys; print(sys.executable)' 2>/dev/null || true)"
[ -x "$PY3" ] || fail "python3 is required for the Terminal (pty) cases"
PTY_RUN='
import os, pty, signal, sys
pid, fd = pty.fork()
if pid == 0:
    os.execvp(sys.argv[1], sys.argv[1:])
def _timeout(*_):
    os.kill(pid, signal.SIGKILL)
    sys.stdout.write("PTY_TIMEOUT\n")
    sys.stdout.flush()
    os._exit(124)
signal.signal(signal.SIGALRM, _timeout)
signal.alarm(60)
out = b""
while True:
    try:
        chunk = os.read(fd, 65536)
    except OSError:
        break
    if not chunk:
        break
    out += chunk
_, status = os.waitpid(pid, 0)
sys.stdout.write(out.decode("utf-8", "replace"))
sys.exit(os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1)
'

run_case() { # run_case NAME ARCH DRY [TTY] -> sets OUT, CODE, CURL_CALLS
  local name="$1" arch="$2" dry="$3" tty="${4:-0}" dir="$TMP/$1"
  build_stubs "$dir" "$arch"
  build_harness "$dir/harness.sh" "$dry"
  set +e
  if [ "$tty" = 1 ]; then
    OUT="$(PATH="$dir:/usr/bin:/bin" "$PY3" -c "$PTY_RUN" bash "$dir/harness.sh" < /dev/null 2>&1)"
    CODE=$?
    OUT="$(printf '%s\n' "$OUT" | tr -d '\r')"
  else
    OUT="$(PATH="$dir:/usr/bin:/bin" bash "$dir/harness.sh" < /dev/null 2>&1)"
    CODE=$?
  fi
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

# Terminal: the person runs `bash bootstrap.sh` themselves (interactive branch)
run_case "intel-tty" x86_64 0 1
[ "$CODE" -eq 0 ] || fail "intel tty: harness exited $CODE. Output: $OUT"
echo "$OUT" | grep -q '^RESULT_REACHED_END=1$' || fail "intel tty: run did not continue past the Homebrew section. Output: $OUT"
echo "$OUT" | grep -qi "Intel" || fail "intel tty: no Intel warning printed. Output: $OUT"
echo "$OUT" | grep -qi "Installing Homebrew" && fail "intel tty: started the Homebrew install. Output: $OUT"
[ -z "$CURL_CALLS" ] || fail "intel tty: reached for the Homebrew installer: $CURL_CALLS"
echo "PASS: Intel Mac in Terminal never reaches the Homebrew installer"

# control: Apple Silicon behavior is unchanged (non-interactive prints the Terminal step)
run_case "arm-dry0" arm64 0
echo "$OUT" | grep -qi "TERMINAL STEP NEEDED" || fail "control: Apple Silicon no longer gets the Terminal step. Output: $OUT"
echo "$OUT" | grep -qi "Intel" && fail "control: Apple Silicon got the Intel warning. Output: $OUT"
echo "PASS: Apple Silicon control unchanged"

# control: the pty really reaches the interactive branch. Apple Silicon in
# Terminal still fetches Homebrew's installer (the curl stub records it), so the
# Intel Terminal case above tests that branch rather than passing by default.
run_case "arm-tty" arm64 0 1
echo "$CURL_CALLS" | grep -q "Homebrew/install" || fail "control: Apple Silicon in Terminal never reached the Homebrew installer, so the Intel Terminal case proves nothing. Output: $OUT"
echo "PASS: Apple Silicon Terminal control still reaches the Homebrew installer"
