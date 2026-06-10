#!/usr/bin/env bash
#
# Integration test: check-cd-outside-worktree honors the inline
# `WORKTREE_CD_BYPASS=1 <cmd>` prefix it advertises in its block message, not
# only the session env. A PreToolUse(Bash) gate runs in the hook process whose
# env is the SESSION env; an inline prefix lives only in the command STRING, so
# reading os.environ alone makes the advertised bypass un-fireable (bug class
# HOOK-READS-SESSION-ENV-NOT-COMMAND-ENV). Every assertion has a negative control.
#
# Pure string-level: the hook does path-string matching off payload `cwd`, so no
# real dirs/git are needed — fast + hermetic.
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
HOOK="$REPO_ROOT/hooks/check-cd-outside-worktree.py"
PY="${PYTHON:-python3}"

main="/tmp/abs-fake-repo-$$"
wt="$main/.claude/worktrees/slug"

# run <command> [env_bypass]  -> echoes the hook exit code (0 allow / 2 block)
run() {
  local cmd="$1" env_bypass="${2:-}"
  local payload
  payload="{\"tool_name\":\"Bash\",\"cwd\":\"$wt\",\"tool_input\":{\"command\":\"$cmd\"}}"
  if [ "$env_bypass" = "env" ]; then
    printf '%s' "$payload" | WORKTREE_CD_BYPASS=1 "$PY" "$HOOK" >/dev/null 2>&1 && echo 0 || echo $?
  else
    printf '%s' "$payload" | env -u WORKTREE_CD_BYPASS "$PY" "$HOOK" >/dev/null 2>&1 && echo 0 || echo $?
  fi
}

assert() { # <label> <got> <want>
  if [ "$2" = "$3" ]; then echo "PASS: $1"; else echo "FAIL: $1 (got $2, want $3)"; exit 1; fi
}

# 1. NEGATIVE CONTROL: cd into the main checkout from a worktree session -> BLOCK
assert "cd into main blocks (negative control)" "$(run "cd $main")" 2

# 2. inline prefix -> ALLOW (the fix)
assert "inline WORKTREE_CD_BYPASS=1 prefix allows" "$(run "WORKTREE_CD_BYPASS=1 cd $main")" 0

# 3. session env -> ALLOW (pre-existing path still works)
assert "session-env WORKTREE_CD_BYPASS still allows" "$(run "cd $main" env)" 0

# 4. NEGATIVE CONTROL: a quoted/non-leading token is NOT a bypass; the real
#    `cd` into main still blocks.
assert "quoted bypass token does not bypass" "$(run "echo 'WORKTREE_CD_BYPASS=1' && cd $main")" 2

# 5. NEGATIVE CONTROL (the load-bearing one): a cd into main carrying a
#    DIFFERENT env prefix must STILL block. Before the strip-leading-env fix,
#    `^cd` missed any env-prefixed cd entirely (a HEAD-drift false-negative) and
#    the inline-bypass check was cosmetic. This proves the cd is now detected
#    through the prefix, and that only WORKTREE_CD_BYPASS — not any var — bypasses.
assert "non-bypass env-prefixed cd into main still blocks" "$(run "FOO=bar cd $main")" 2

echo "ALL PASS: test_cd_worktree_inline_bypass"
