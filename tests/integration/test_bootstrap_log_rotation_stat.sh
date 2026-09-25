#!/usr/bin/env bash
# Regression test for bootstrap.sh's log-rotation size check
# (scripts/PORTABILITY.md #1: the GNU-vs-BSD `stat` mtime/size trap).
#
# THE BUG: bootstrap.sh reads its own forensic log's size with a BSD-first
# `||` chain, unconditionally, before argument parsing even runs (so this
# fires on EVERY invocation, --dry-run included, once ~/.claude/.bootstrap.log
# exists from a prior run):
#   log_size=$(stat -f %z "$BOOTSTRAP_LOG" 2>/dev/null || stat -c %s "$BOOTSTRAP_LOG" 2>/dev/null || echo 0)
#   if [[ "$log_size" -gt 5242880 ]]; then ...
# GNU's `-f` means `--file-system`, not "custom format" -- `stat -f %z FILE`
# on real GNU coreutils leaks non-numeric filesystem-status text to stdout on
# its way to failing (see tests/integration/lib/gnu_stat_shim.sh for the
# measured transcript), `log_size` ends up contaminated, and
# `[[ "$log_size" -gt N ]]` then hits bash's arithmetic evaluator on a bare
# word under this script's `set -u` -- an unbound-variable abort, every
# single run, once the log exists. This is the SAME bug class as
# hooks/check-claude-code-version.sh's cache-age crash, at a different
# `stat` format letter (%z, size, not %m, mtime) -- found while broadening
# that fix's recurrence guard to cover any BSD-first `stat -f <fmt>`, not
# just `%m`.
#
# Reuses test_bootstrap_dry_run.sh's fixture setup (email marker + a
# self-referencing SKILL_DIR symlink so bootstrap finds its own templates)
# so --dry-run reaches far enough to matter, then adds the one fixture this
# bug needs: a pre-existing .bootstrap.log.
#
# Self-contained. Exit 0 = pass, 1 = fail.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TARGET="$ROOT/bootstrap.sh"

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
sandbox_home "$TMP"

SHIMDIR="$TMP/gnu-stat-shim"
install_gnu_stat_shim "$SHIMDIR"

# Same fixture test_bootstrap_dry_run.sh uses: pre-stage the email marker so
# bootstrap doesn't try to mint a token, and a self-referencing SKILL_DIR so
# it finds its own templates/skills/scripts.
touch "$HOME/.claude/.ai-brain-starter-email-on-file"
mkdir -p "$HOME/.claude/skills/ai-brain-starter"
rmdir "$HOME/.claude/skills/ai-brain-starter"
ln -s "$ROOT" "$HOME/.claude/skills/ai-brain-starter"

# The one fixture THIS bug needs: a pre-existing .bootstrap.log, so the
# rotation-size check actually runs (it is skipped entirely on a fresh
# install with no log yet -- which is exactly why this crash was invisible
# on a first run and only bit on the second+ one).
mkdir -p "$HOME/.claude"
printf 'prior run forensic log content\n' > "$HOME/.claude/.bootstrap.log"

OUT_FILE="$TMP/bootstrap.out"
ERR_FILE="$TMP/bootstrap.err"
set +e
PATH="$SHIMDIR:$PATH" EMAIL="ci@example.com" NAME="CI Test" LANG_HINT="en" \
  bash "$TARGET" --dry-run > "$OUT_FILE" 2> "$ERR_FILE"
EXIT_CODE=$?
set -e

if grep -q "unbound variable" "$ERR_FILE"; then
  fail "bootstrap.sh aborted with an unbound-variable error reading its own log size under GNU stat (stderr: $(cat "$ERR_FILE"))"
fi
if [ "$EXIT_CODE" -ne 0 ]; then
  fail "bootstrap.sh --dry-run exited $EXIT_CODE under GNU stat (stderr tail: $(tail -5 "$ERR_FILE"))"
fi

echo "OK: bootstrap.sh reads its own log size correctly under GNU stat's -f %z behavior (no crash, exit 0)"
echo "PASS: test_bootstrap_log_rotation_stat"
