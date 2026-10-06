#!/usr/bin/env bash
# Regression test for scripts/vault-safe-commit.sh's non-PID lock-age check
# (scripts/PORTABILITY.md #1: the GNU-vs-BSD `stat` mtime trap).
#
# THE SITE: when the vault's .git/index.lock exists, is non-empty, and its
# content is not a bare PID, the script falls back to an age check -- a lock
# older than 60s with no matching live write process is presumed abandoned
# and removed so a stuck commit doesn't wedge every future one. The age used
# to come from a raw
#   $(( $(date +%s) - $(stat -f%m LOCK 2>/dev/null || stat -c%Y LOCK 2>/dev/null || date +%s) ))
# one-liner. This test does not reproduce a crash on that exact line against
# measured GNU coreutils 9.4 -- the *unspaced* `-f%m` fails at option-parsing
# before touching any operand (clean, empty stdout), so the `||` fallback to
# `-c%Y` happens to work on this coreutils build (see the PR body / commit
# message for the measured transcript and why the fix still applies: an
# undocumented accident of one getopt implementation is not something a
# safety check should depend on, and the fixed line now shares the exact
# same GNU-first + numeric-validated helper as every other stat-mtime site
# in this repo, `_close_lock_mtime` in _session_close_guard.sh, instead of a
# fourth, differently-shaped inline chain).
#
# So this test asserts the CONTRACT directly, under the real GNU-stat
# behavior (via the PATH shim in lib/gnu_stat_shim.sh, same technique
# test_graph_context_hook_env.sh uses), against the real script:
#   1. A FRESH non-PID lock (mtime = now) is never removed: the script waits
#      and eventually refuses (dies) rather than clearing a live mutex.
#   2. A STALE non-PID lock (mtime far in the past, > 60s) IS removed, and
#      the commit that follows succeeds.
#
# Both cases are also run against the pre-fix line (git HEAD) for direct
# comparison; the PR body records what that comparison showed.
#
# Self-contained. Exit 0 = pass, 1 = fail.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TARGET="$ROOT/scripts/vault-safe-commit.sh"

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

# make_vault DIR -- a throwaway git repo with one committed file, so a
# genuine commit can proceed once the lock clears.
make_vault() {
  local d="$1"
  mkdir -p "$d"
  git -C "$d" init -q
  git -C "$d" config user.email "test@example.invalid"
  git -C "$d" config user.name "test"
  echo "seed" > "$d/seed.txt"
  git -C "$d" add seed.txt
  git -C "$d" commit -q -m seed
  echo "changed" > "$d/target.txt"
}

# --- case 1: fresh non-PID lock must NOT be removed ------------------------
V1="$TMP/vault-fresh"
make_vault "$V1"
mkdir -p "$V1/.git"
echo "not-a-pid" > "$V1/.git/index.lock"   # non-empty, non-numeric -> non-PID branch

set +e
out1="$(PATH="$SHIMDIR:$PATH" VAULT_ROOT="$V1" VAULT_GIT_LOCK_MAX_WAIT=2 \
  bash "$TARGET" "test commit" target.txt 2>&1)"
rc1=$?
set -e

[[ -e "$V1/.git/index.lock" ]] ||
  fail "case 1 (fresh lock): index.lock was REMOVED -- an age we could not have proven >60s old was treated as stale (output: $out1)"
[[ "$rc1" -ne 0 ]] ||
  fail "case 1 (fresh lock): expected a refusal (lock never clears within 2s), got exit 0 (output: $out1)"
echo "$out1" | grep -qi "lock held" ||
  fail "case 1 (fresh lock): expected the 'lock held ... Investigate before retry' refusal, got: $out1"
echo "OK: a fresh non-PID lock is correctly left in place (never removed) under GNU stat"

# --- case 2: stale non-PID lock (mtime far in the past) IS removed ---------
V2="$TMP/vault-stale"
make_vault "$V2"
mkdir -p "$V2/.git"
echo "not-a-pid" > "$V2/.git/index.lock"
touch -t 202001010000 "$V2/.git/index.lock"   # ~6 years old -- unambiguously > 60s

set +e
out2="$(PATH="$SHIMDIR:$PATH" VAULT_ROOT="$V2" VAULT_GIT_LOCK_MAX_WAIT=2 \
  bash "$TARGET" "test commit" target.txt 2>&1)"
rc2=$?
set -e

[[ ! -e "$V2/.git/index.lock" ]] ||
  fail "case 2 (stale lock): index.lock was NOT removed despite a provably ancient mtime (output: $out2)"
[[ "$rc2" -eq 0 ]] ||
  fail "case 2 (stale lock): expected the commit to succeed once the stale lock cleared, got exit $rc2 (output: $out2)"
git -C "$V2" log --oneline -1 | grep -q "test commit" ||
  fail "case 2 (stale lock): expected a real commit named 'test commit' after the lock cleared"
echo "OK: a stale (>60s) non-PID lock is correctly removed under GNU stat, and the commit proceeds"

echo "PASS: test_vault_safe_commit_lock_age"
