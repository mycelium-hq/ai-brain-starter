#!/usr/bin/env bash
# Negative-control test for check-worktree-on-vault.py (the worktree-on-vault melt guard).
# A guard earns trust only by FIRING on the exact thing it catches AND staying
# SILENT on every near-miss. This asserts a HIT for a real git worktree checked
# out inside an Obsidian vault, and OK for every negative control: a plain vault,
# a non-git vault, a code-repo worktree (no .obsidian/), and an empty worktrees dir.
# Run: bash scripts/test-worktree-on-vault-guard.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-worktree-on-vault.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0

# git in the temp repos needs an identity; set it LOCALLY per-repo (never global)
# and via env as a belt-and-suspenders for a box with no ambient identity.
export GIT_AUTHOR_NAME="ci" GIT_AUTHOR_EMAIL="ci@example.com"
export GIT_COMMITTER_NAME="ci" GIT_COMMITTER_EMAIL="ci@example.com"

mkrepo() { # DIR  -> a git repo with one commit
  git init -q "$1"
  git -C "$1" config user.email ci@example.com
  git -C "$1" config user.name ci
  printf 'x\n' > "$1/note.md"
  git -C "$1" add -A
  git -C "$1" commit -qm init
}

addworktree() { # REPO  SLUG  -> a real linked worktree at REPO/.claude/worktrees/SLUG
  mkdir -p "$1/.claude/worktrees"
  git -C "$1" worktree add -q --detach "$1/.claude/worktrees/$2" HEAD 2>/dev/null
}

assert_token() { # label  expected-prefix  vault
  local label="$1" want="$2" v="$3" got
  got="$(python3 "$CHECK" --porcelain "$v" 2>/dev/null)"
  case "$got" in
    "$want"*) echo "PASS  $label  ($got)";;
    *)        echo "FAIL  $label  want=$want got=$got"; fails=$((fails+1));;
  esac
}

assert_rc() { # label  want-rc  vault
  local label="$1" want="$2" v="$3"
  python3 "$CHECK" --porcelain "$v" >/dev/null 2>&1
  local rc=$?
  [ "$rc" = "$want" ] && echo "PASS  $label (rc=$rc)" || { echo "FAIL  $label want-rc=$want got-rc=$rc"; fails=$((fails+1)); }
}

# POSITIVE: a real git worktree checked out inside an Obsidian vault must HIT (exit 1).
POS="$TMP/vault-with-worktree"
mkrepo "$POS"
mkdir -p "$POS/.obsidian"
addworktree "$POS" "session-abc123"
assert_token "real worktree inside vault" "WORKTREE_ON_VAULT" "$POS"
assert_rc    "HIT exits 1"                1                   "$POS"

# POSITIVE via cwd channel: /diagnose run FROM inside the worktree, vault passed
# as the arg, still HITs (exercises current_worktree()). Use a vault whose on-disk
# scan would also find it, but prove the cwd path independently by cd-ing in.
( cd "$POS/.claude/worktrees/session-abc123" && python3 "$CHECK" --porcelain "$POS" >/dev/null 2>&1 ) \
  && { echo "FAIL  cwd-channel want-rc=1 got-rc=0"; fails=$((fails+1)); } \
  || echo "PASS  cwd-channel fires from inside the worktree (rc=1)"

# NEGATIVE 1: plain vault (git + .obsidian/, no worktrees) -> OK (proves it is not
# always-HIT; a guard that always fires is as useless as one that never does).
PLAIN="$TMP/plain-vault"
mkrepo "$PLAIN"
mkdir -p "$PLAIN/.obsidian"
assert_token "plain vault (no worktrees)" "OK_NO_WORKTREES" "$PLAIN"
assert_rc    "OK exits 0"                 0                 "$PLAIN"

# NEGATIVE 2: not a git repo (.obsidian/ + a stray .claude/worktrees/ dir, no .git)
# -> OK_NOT_GIT. The Desktop worktree feature needs git; no git == no melt path.
NOGIT="$TMP/nogit-vault"
mkdir -p "$NOGIT/.obsidian" "$NOGIT/.claude/worktrees/stray"
assert_token "non-git vault" "OK_NOT_GIT" "$NOGIT"
assert_rc    "non-git exits 0" 0          "$NOGIT"

# NEGATIVE 3: a CODE repo worktree (git + real worktree, NO .obsidian/) -> OK_NOT_VAULT.
# Code-repo worktrees are cheap + correct; .obsidian/ is the discriminator.
CODE="$TMP/code-repo"
mkrepo "$CODE"
addworktree "$CODE" "feature-x"
assert_token "code-repo worktree (no .obsidian/)" "OK_NOT_VAULT" "$CODE"
assert_rc    "code-repo exits 0"                  0              "$CODE"

# NEGATIVE 4: an EMPTY .claude/worktrees/ dir (git + .obsidian/, dir but no checkout)
# -> OK_NO_WORKTREES. The dir alone is not the melt; a live checkout is.
EMPTY="$TMP/empty-worktrees"
mkrepo "$EMPTY"
mkdir -p "$EMPTY/.obsidian" "$EMPTY/.claude/worktrees"
assert_token "empty worktrees dir" "OK_NO_WORKTREES" "$EMPTY"

# NEGATIVE 5: a non-existent path -> OK (fail-open, never crash the report).
assert_token "missing path" "OK_NO_WORKTREES" "$TMP/does-not-exist"

echo
if [ "$fails" -gt 0 ]; then echo "FAILED: $fails"; exit 1; fi
echo "ALL TESTS PASSED"
