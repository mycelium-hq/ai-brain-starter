#!/usr/bin/env bash
# Regression test for hooks/check-claude-code-version.sh's cache-freshness
# read (scripts/PORTABILITY.md #1: the GNU-vs-BSD `stat` mtime trap).
#
# THE BUG: the old code read the cache's mtime with a BSD-first `||` chain --
#   last=$(stat -f %m "$CACHE_FILE" 2>/dev/null || stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0)
# GNU's `-f` means `--file-system`, not "custom format" -- so on real GNU
# coreutils `stat -f %m FILE` prints non-numeric filesystem-status text to
# stdout (see tests/integration/lib/gnu_stat_shim.sh for the measured
# transcript) instead of failing cleanly into the `-c %Y` fallback. That text
# landed in `last`, and `age=$(( now - last ))` then hit bash's arithmetic
# parser on a bare word ("File") -- an unbound-variable abort under this
# script's `set -uo pipefail`. Net effect measured against the real script: a
# SessionStart hook that silently prints nothing on every 2nd+ invocation
# within the 6h cache window on any Linux box, instead of the cached version
# banner.
#
# This test reproduces GNU stat's exact behavior on ANY host (macOS included)
# via a PATH shim (tests/integration/lib/gnu_stat_shim.sh), the same
# technique tests/integration/test_graph_context_hook_env.sh uses for its own
# env-override cases: run the real, unmodified target script under a
# deterministic fixture rather than mocking the logic under test.
#
# Asserts:
#   A fresh cache file (mtime = now) is read correctly under GNU stat's
#   idiosyncratic `-f %m` behavior: the script prints the cached banner
#   verbatim and does not crash. Fails against the pre-fix line (empty
#   stdout -- the script aborted before ever reaching `cat "$CACHE_FILE"`);
#   passes once the mtime read is GNU-first + numeric-validated.
#
# Self-contained. Exit 0 = pass, 1 = fail.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TARGET="$ROOT/hooks/check-claude-code-version.sh"

# HOME alone does not sandbox ~ on Windows -- see lib/sandbox_home.sh. This
# target only ever reads/writes $HOME/.claude/.claude-code-version-check.
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$HERE/lib/sandbox_home.sh"
# shellcheck source=tests/integration/lib/gnu_stat_shim.sh
. "$HERE/lib/gnu_stat_shim.sh"

[[ -f "$TARGET" ]] || { echo "FAIL: target not found: $TARGET"; exit 1; }

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
sandbox_home "$TMP/home"

SHIMDIR="$TMP/gnu-stat-shim"
install_gnu_stat_shim "$SHIMDIR"

CACHE_FILE="$HOME/.claude/.claude-code-version-check"
mkdir -p "$(dirname "$CACHE_FILE")"
BANNER="[claude-code-version] 9.9.9 is current (fixture)"
printf '%s\n' "$BANNER" > "$CACHE_FILE"
# mtime = now, well inside the 6h TTL -- this is the "fresh cache" branch,
# the one that dereferences the mtime read this test guards.

# Prepend the shim so `stat` resolves to the GNU-coreutils-9.4 double
# regardless of the host's real stat. The rest of PATH stays intact: the
# target's own PATH-shim-stripping header (trailofbits modern-python) and
# `gh`/`awk`/`sed` all still need to resolve normally on this "fresh cache"
# branch that this test exercises returns before ever touching gh.
# HOME (and, on Windows, USERPROFILE) are already exported by sandbox_home
# above -- re-stating HOME= here alone would redirect it without its
# Windows pair, so it is intentionally left out; PATH is the only override
# this specific call needs.
out="$(PATH="$SHIMDIR:$PATH" bash "$TARGET" 2>"$TMP/stderr")"

echo "$out" | grep -qF "$BANNER" ||
  fail "fresh cache under GNU stat: expected the cached banner on stdout, got: [$out] (stderr: $(cat "$TMP/stderr"))"

echo "OK: fresh cache is read correctly under GNU stat's -f %m behavior (cached banner printed, no crash)"
echo "PASS: test_check_claude_code_version_cache_age"
