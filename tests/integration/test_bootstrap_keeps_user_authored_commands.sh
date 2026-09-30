#!/usr/bin/env bash
# Test that bootstrap.sh's slash-command step replaces a STALE copy of a shipped
# command but keeps a command the USER wrote.
#
# Bug class: a customization with no safe home. The step copied every
# commands/*.md over ~/.claude/commands/<name>.md whenever they differed (backup
# first), so a user who rewrote a command lost it on the next install. The one
# way to keep it was to put the same edit in the checkout's commands/ as well —
# and a dirty checkout makes ai-brain-auto-update.py refuse every update from
# then on. Observed in the field: 41 days with no successful update, every
# guard and security fix since then missing, and nothing looked broken.
#
# The line drawn: a differing installed copy whose blob this repo ever shipped
# under commands/ is stale -> replaced (backup kept). One it never shipped is
# the user's -> kept, reported under "Skipped (your customizations preserved)".
# Where provenance is unknowable (not a git checkout, shallow clone) the step
# behaves exactly as before.
#
# Runs the REAL block, extracted from bootstrap.sh by its markers, against
# temp fixtures. Self-contained. Exit 0 = pass, 1 = fail.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/bootstrap.sh"
# HOME alone does not sandbox ~ on Windows -- see lib/sandbox_home.sh.
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$REPO_ROOT/tests/integration/lib/sandbox_home.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILS=0
check() { # check <description> <command...>
  local msg="$1"; shift
  if "$@"; then echo "  ok    $msg"; else echo "  FAIL  $msg"; FAILS=$((FAILS + 1)); fi
}

echo "A. the block ships in bootstrap.sh and is extractable"
BLOCK="$TMP/block.sh"
awk '/^# ai-brain:slash-commands:start$/{on=1} on{print} /^# ai-brain:slash-commands:end$/{exit}' \
  "$BOOTSTRAP" > "$BLOCK"
check "start and end markers present" grep -q '^# ai-brain:slash-commands:end$' "$BLOCK"
check "block installs into ~/.claude/commands" grep -q 'HOME/.claude/commands' "$BLOCK"
if ! grep -q '^# ai-brain:slash-commands:end$' "$BLOCK"; then
  echo "ERROR: cannot extract the block; the rest of this test would be vacuous." >&2
  exit 1
fi

V1=$'# meeting-todos\nversion one\n'
V2=$'# meeting-todos\nversion two\n'
MINE=$'# meeting-todos\nmy own routing, never shipped\n'

# new_skill <dir> <git|plain>: a fake checkout whose commands/meeting-todos.md
# went V1 -> V2, so V1 is a blob "upstream" shipped and V2 is current.
new_skill() {
  local d="$1" kind="$2"
  mkdir -p "$d/commands"
  if [[ "$kind" == "git" ]]; then
    git -C "$d" init --quiet
    git -C "$d" config user.email t@example.com
    git -C "$d" config user.name T
    printf '* text=auto eol=lf\n' > "$d/.gitattributes"
    printf '%s' "$V1" > "$d/commands/meeting-todos.md"
    git -C "$d" add -A && git -C "$d" commit --quiet -m v1
    printf '%s' "$V2" > "$d/commands/meeting-todos.md"
    git -C "$d" add -A && git -C "$d" commit --quiet -m v2
  else
    printf '%s' "$V2" > "$d/commands/meeting-todos.md"
  fi
}

# run_block <skill dir> <home dir>: the block with bootstrap's helpers stubbed.
run_block() {
  (
    set -euo pipefail
    # Read by the sourced block, not by this file (shellcheck cannot see that).
    # shellcheck disable=SC2034
    SKILL_DIR="$1"
    sandbox_home "$2"   # HOME + USERPROFILE, so the block writes only under the fixture
    # shellcheck disable=SC2034
    UPDATED=(); SKIPPED=(); BACKUPS=()
    # shellcheck disable=SC2329
    hdr() { :; }
    # shellcheck disable=SC2329
    ok() { echo "OK: $*"; }
    # shellcheck disable=SC2329
    warn() { echo "WARN: $*"; }
    # shellcheck source=/dev/null
    source "$BLOCK"
    echo "SKIPPED=${#SKIPPED[@]} BACKUPS=${#BACKUPS[@]}"
  )
}

dst_of() { echo "$1/.claude/commands/meeting-todos.md"; }
baks() { find "$1/.claude/commands" -name 'meeting-todos.md.bak-*' | wc -l | tr -d ' '; }
same() { [[ "$(cat "$1")" == "$2" ]]; }
has() { grep -q -- "$2" <<<"$1"; }

echo "B. a stale copy of a shipped version is replaced, with a backup"
S="$TMP/b/skill"; H="$TMP/b/home"; new_skill "$S" git; mkdir -p "$H/.claude/commands"
printf '%s' "$V1" > "$(dst_of "$H")"
out="$(run_block "$S" "$H")"
check "installed copy is now the current version" same "$(dst_of "$H")" "${V2%$'\n'}"
check "one backup written" [ "$(baks "$H")" = 1 ]
check "nothing reported as kept" has "$out" "SKIPPED=0"

echo "C. a command the user wrote is kept, untouched, and reported"
S="$TMP/c/skill"; H="$TMP/c/home"; new_skill "$S" git; mkdir -p "$H/.claude/commands"
printf '%s' "$MINE" > "$(dst_of "$H")"
out="$(run_block "$S" "$H")"
check "user's command left exactly as written" same "$(dst_of "$H")" "${MINE%$'\n'}"
check "no backup made (nothing was replaced)" [ "$(baks "$H")" = 0 ]
check "reported under Skipped" has "$out" "SKIPPED=1"
check "warning names the command" has "$out" "kept your /meeting-todos"

echo "D. a CRLF copy of a shipped version still counts as shipped"
S="$TMP/d/skill"; H="$TMP/d/home"; new_skill "$S" git; mkdir -p "$H/.claude/commands"
printf '# meeting-todos\r\nversion one\r\n' > "$(dst_of "$H")"
run_block "$S" "$H" >/dev/null
check "CRLF stale copy replaced by the current version" same "$(dst_of "$H")" "${V2%$'\n'}"

echo "E. not a git checkout: unchanged behavior (replace, with backup)"
S="$TMP/e/skill"; H="$TMP/e/home"; new_skill "$S" plain; mkdir -p "$H/.claude/commands"
printf '%s' "$MINE" > "$(dst_of "$H")"
run_block "$S" "$H" >/dev/null
check "replaced by the shipped version" same "$(dst_of "$H")" "${V2%$'\n'}"
check "the user's text survives in the backup" [ "$(baks "$H")" = 1 ]

echo "E2. an archive install nested inside an unrelated repo: unchanged behavior"
O="$TMP/e2/outer"; mkdir -p "$O"; git -C "$O" init --quiet
git -C "$O" config user.email t@example.com; git -C "$O" config user.name T
new_skill "$O/skills/abs" plain
git -C "$O" add -A && git -C "$O" commit --quiet -m outer   # the outer repo now tracks skills/abs/commands/
H="$TMP/e2/home"; mkdir -p "$H/.claude/commands"
printf '%s' "$MINE" > "$(dst_of "$H")"
out="$(run_block "$O/skills/abs" "$H")"
check "outer repo's history not used: replaced with backup" has "$out" "SKIPPED=0 BACKUPS=1"

echo "F. shallow clone: provenance unknowable, unchanged behavior"
S="$TMP/f/src"; new_skill "$S" git
git clone --quiet --depth 1 "file://$S" "$TMP/f/skill"
H="$TMP/f/home"; mkdir -p "$H/.claude/commands"
printf '%s' "$MINE" > "$(dst_of "$H")"
run_block "$TMP/f/skill" "$H" >/dev/null
check "replaced by the shipped version" same "$(dst_of "$H")" "${V2%$'\n'}"
check "backup written" [ "$(baks "$H")" = 1 ]

echo "G. a checkout carrying the same edit (the old workaround) changes nothing"
S="$TMP/g/skill"; H="$TMP/g/home"; new_skill "$S" git; mkdir -p "$H/.claude/commands"
printf '%s' "$MINE" > "$S/commands/meeting-todos.md"
printf '%s' "$MINE" > "$(dst_of "$H")"
out="$(run_block "$S" "$H")"
check "identical copies: no backup, nothing kept" has "$out" "SKIPPED=0 BACKUPS=0"

echo "H. a fresh install still installs"
S="$TMP/h/skill"; H="$TMP/h/home"; new_skill "$S" git
run_block "$S" "$H" >/dev/null
check "command installed" same "$(dst_of "$H")" "${V2%$'\n'}"

echo
if [[ $FAILS -gt 0 ]]; then
  echo "FAILED: $FAILS assertion(s)"
  exit 1
fi
echo "PASS: bootstrap.sh keeps user-authored commands and replaces stale shipped ones"
