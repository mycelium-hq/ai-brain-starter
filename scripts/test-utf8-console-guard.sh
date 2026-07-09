#!/usr/bin/env bash
#
# scripts/test-utf8-console-guard.sh - regression test for scripts/check-utf8-stdout.py,
# the fail-loud guard against the Windows cp1252 print crash class (ai-brain-starter#313).
#
# Bug class: a vault script that print()s the "gear Meta" emoji, an em dash, or an
# accented name works on a UTF-8 console (macOS/Linux) and silently ships. On a
# Windows cp1252 console - or a C-locale pipe - the SAME print() raises
# UnicodeEncodeError, the caller captures an empty string, and downstream logic
# misreads it (#313: sync-vault-scripts.ps1 read the empty output as "no Meta
# folder"). PR #313 fixed the two files that had already broken; this lint makes
# the NEXT one fail CI instead of a user's console.
#
# The assertions below prove the lint (a) FAILS on an unguarded non-ASCII-printing
# CLI - the negative control, because a guard earns trust only by failing on the
# thing it catches - (b) PASSES a guarded one, (c) honors the documented bypass,
# (d) does NOT over-flag a genuinely ASCII-only CLI, and (e) that the guard it
# enforces is load-bearing: the unguarded fixture actually crashes under cp1252
# while the guarded one prints clean. Finally it runs the lint over the real
# scripts/ tree and requires it clean, so a future unguarded script fails here.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKER="$HERE/check-utf8-stdout.py"

fail=0
check() {  # check <description> <expected> <actual>
  if [ "$2" = "$3" ]; then
    echo "  ok: $1"
  else
    echo "  FAIL: $1"
    echo "        expected: [$2]"
    echo "        actual:   [$3]"
    fail=1
  fi
}

# Non-ASCII bytes built at runtime so THIS shell file stays ASCII-clean; the
# fixture .py files below carry the real UTF-8 bytes that trigger the crash.
GEAR="$(printf '\xe2\x9a\x99\xef\xb8\x8f')"   # U+2699 U+FE0F  "gear Meta" emoji
EMDASH="$(printf '\xe2\x80\x94')"             # U+2014          em dash

base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT

rc() {  # rc <file...> -> echo the checker's exit code without tripping set -e
  if python3 "$CHECKER" "$@" >/dev/null 2>&1; then echo 0; else echo $?; fi
}

# --- Fixture A: unguarded CLI that prints non-ASCII (the crash class) --------
cat > "$base/unguarded.py" <<PY
#!/usr/bin/env python3
import sys


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")


if __name__ == "__main__":
    main()
PY
check "unguarded non-ASCII CLI is FLAGGED (exit 1)" "1" "$(rc "$base/unguarded.py")"

# --- Fixture B: same, guarded -> passes -------------------------------------
cat > "$base/guarded.py" <<PY
#!/usr/bin/env python3
import sys


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    main()
PY
check "guarded non-ASCII CLI PASSES (exit 0)" "0" "$(rc "$base/guarded.py")"

# --- Fixture C: unguarded but opted out via the documented bypass ------------
cat > "$base/bypass.py" <<PY
#!/usr/bin/env python3
# utf8-stdout-ok: console output below is provably ASCII; non-ASCII is doc only.
import sys


def main():
    print("${GEAR}")  # marker only


if __name__ == "__main__":
    main()
PY
check "bypass marker is honored (exit 0)" "0" "$(rc "$base/bypass.py")"

# --- Fixture D: genuinely ASCII-only CLI -> never flagged (no over-strict) ---
cat > "$base/ascii_only.py" <<'PY'
#!/usr/bin/env python3
import sys


def main():
    print("plain ascii output only, count", len(sys.argv))


if __name__ == "__main__":
    main()
PY
check "ASCII-only CLI is NOT flagged (exit 0)" "0" "$(rc "$base/ascii_only.py")"

# --- Fixture E: the guard is load-bearing under a real cp1252 console --------
if PYTHONIOENCODING=cp1252 PYTHONUTF8=0 python3 "$base/unguarded.py" >/dev/null 2>"$base/err"; then
  check "unguarded fixture CRASHES under cp1252" "crash" "no-crash"
else
  if grep -q UnicodeEncodeError "$base/err"; then
    check "unguarded fixture CRASHES under cp1252" "crash" "crash"
  else
    check "unguarded fixture CRASHES under cp1252" "crash" "other-error"
  fi
fi
if out="$(PYTHONIOENCODING=cp1252 PYTHONUTF8=0 python3 "$base/guarded.py" 2>/dev/null)"; then
  case "$out" in
    *Meta*) check "guarded fixture PRINTS under cp1252" "ok" "ok" ;;
    *)      check "guarded fixture PRINTS under cp1252" "ok" "bad-output[$out]" ;;
  esac
else
  check "guarded fixture PRINTS under cp1252" "ok" "crash"
fi

# --- Fixture F: the real scripts/ tree must be clean -------------------------
check "real scripts/ tree passes the lint (exit 0)" "0" "$(rc)"

if [ "$fail" != 0 ]; then
  echo "FAILED: utf8-console-guard regression test"
  exit 1
fi
echo "PASSED: utf8-console-guard regression test"
