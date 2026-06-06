#!/usr/bin/env bash
# Negative-control + churn-burst test for relocate-machinery-sidecar.sh.
#
# The Done= predicate for the "vault may live in iCloud" mode is: after a full
# churn burst (worktree create + commits + `git gc`) on a vault, ZERO machinery
# CONTENT bytes live inside the (synced) vault tree — only static symlinks + the
# one-line `.git` pointer remain. We can't drive iCloud in CI, so we model
# "synced scope" as the vault tree itself and assert the heavy machinery content
# is OUT of it. `find -type f` does not follow symlinks, so relocated content
# (symlinked to the sidecar) is correctly counted as "out of tree".
#
# A guard earns trust only by failing on the thing it catches: the NEGATIVE
# CONTROL repeats the identical churn on a NON-relocated vault and asserts the
# machinery IS in-tree there — proving the metric discriminates.
#
# Run: bash scripts/test-machinery-sidecar.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HELPER="$HERE/relocate-machinery-sidecar.sh"
ROOT="$(mktemp -d)"
SIDE="$ROOT/sidecar"
trap 'rm -rf "$ROOT"' EXIT
fails=0
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; fails=$((fails+1)); }

gitq() { git -C "$1" "${@:2}" >/dev/null 2>&1; }

make_vault() {  # $1 = vault dir
  local v="$1"
  mkdir -p "$v"
  gitq "$v" init
  gitq "$v" config user.email "t@t.test"
  gitq "$v" config user.name  "Test"
  gitq "$v" config commit.gpgsign false
  mkdir -p "$v/.smart-env" "$v/.codegraph" "$v/.claude/worktrees" "$v/⚙️ Meta/Sessions"
  printf 'note\n'  > "$v/note.md"
  printf 'idx\n'   > "$v/.smart-env/index.bin"
  printf 'cg\n'    > "$v/.codegraph/graph.bin"
  printf 'sess\n'  > "$v/⚙️ Meta/Sessions/s1.md"
  gitq "$v" add note.md
  gitq "$v" commit -m init
}

# Count REGULAR machinery files physically inside the vault tree (symlinks not
# followed). Excludes the `.git` POINTER FILE (a tiny static pointer is allowed).
machinery_files_in_tree() {  # $1 = vault dir
  local v="$1" n
  n="$(find "$v" -type f \
        \( -path '*/.git/*' -o -path '*/.smart-env/*' -o -path '*/.codegraph/*' \
           -o -path '*/.claude/worktrees/*' -o -path '*/Sessions/*' \) \
        2>/dev/null | wc -l | tr -d ' ')"
  echo "${n:-0}"
}

churn() {  # $1 = vault dir — simulate a real session's git churn
  local v="$1"
  # a worktree (lands wherever .claude/worktrees resolves to)
  gitq "$v" worktree add "$v/.claude/worktrees/wt1" -b churnbranch HEAD || \
    gitq "$v" worktree add --detach "$v/.claude/worktrees/wt1" HEAD || true
  # several commits to generate loose objects
  local i
  for i in 1 2 3 4 5; do
    printf 'rev %s\n' "$i" > "$v/note.md"
    gitq "$v" add note.md
    gitq "$v" commit -m "rev$i"
  done
  gitq "$v" gc --aggressive --prune=now   # the wholesale-rewrite hazard
}

echo "=== machinery-sidecar: relocate + churn-burst + negative control ==="

# ---------------------------------------------------------------------------
# A. RELOCATED vault: machinery must be out of the synced tree, even after churn
# ---------------------------------------------------------------------------
VA="$ROOT/A"
make_vault "$VA"
before="$(machinery_files_in_tree "$VA")"
[ "$before" -gt 0 ] && pass "A pre-relocate: machinery present in tree ($before files)" \
                    || fail "A pre-relocate: expected machinery in tree, got $before"

bash "$HELPER" "$VA" --sidecar "$SIDE" --quiet
rc=$?
[ "$rc" = 0 ] && pass "A relocate exit 0" || fail "A relocate exit=$rc"

[ -f "$VA/.git" ] && [ ! -d "$VA/.git" ] && pass "A .git is a pointer file" \
                                         || fail "A .git is not a pointer file"
grep -q '^gitdir: ' "$VA/.git" 2>/dev/null && pass "A .git pointer well-formed" \
                                            || fail "A .git pointer malformed"
for d in ".smart-env" ".codegraph" ".claude/worktrees" "⚙️ Meta/Sessions"; do
  [ -L "$VA/$d" ] && pass "A $d is a symlink (out of tree)" || fail "A $d not a symlink"
done

after="$(machinery_files_in_tree "$VA")"
[ "$after" = 0 ] && pass "A post-relocate: ZERO machinery files in tree" \
                 || fail "A post-relocate: expected 0, got $after"

gitq "$VA" status && pass "A git still functional after relocation" \
                  || fail "A git broke after relocation"

churn "$VA"
churned="$(machinery_files_in_tree "$VA")"
[ "$churned" = 0 ] && pass "A post-CHURN (gc+worktree+5 commits): STILL zero machinery in tree" \
                   || fail "A post-churn: machinery leaked into tree ($churned files)"

# worktree content must physically live in the sidecar, not the vault
find "$SIDE/worktrees" -type f 2>/dev/null | grep -q . \
  && pass "A churned worktree content lives in sidecar" \
  || fail "A worktree content not found in sidecar"

# ---------------------------------------------------------------------------
# B. NEGATIVE CONTROL: identical churn on a NON-relocated vault → machinery IS
#    in-tree (proves the metric is not trivially always-zero)
# ---------------------------------------------------------------------------
VB="$ROOT/B"
make_vault "$VB"
churn "$VB"
ctrl="$(machinery_files_in_tree "$VB")"
[ "$ctrl" -gt 0 ] && pass "B negative control: machinery IS in tree without relocation ($ctrl files)" \
                   || fail "B negative control: expected machinery in tree, got $ctrl"

# ---------------------------------------------------------------------------
# C. IDEMPOTENCY: re-running relocate on a fresh (no-churn) vault is a clean no-op
#    (A is excluded here: its churn registered a worktree, which the no-live-
#     worktree guard correctly refuses — that path is covered by block E.)
# ---------------------------------------------------------------------------
VF="$ROOT/F"
make_vault "$VF"
bash "$HELPER" "$VF" --sidecar "$SIDE" --quiet
out="$(bash "$HELPER" "$VF" --sidecar "$SIDE" 2>&1)"; rc=$?   # non-quiet: surface "already" skip lines
[ "$rc" = 0 ] && pass "C re-run exit 0 (idempotent)" || fail "C re-run exit=$rc"
echo "$out" | grep -q 'already' && pass "C re-run reports already-relocated" \
                                 || fail "C re-run did not detect existing state"
still="$(machinery_files_in_tree "$VF")"
[ "$still" = 0 ] && pass "C re-run kept tree clean" || fail "C re-run dirtied tree ($still)"

# ---------------------------------------------------------------------------
# D. ROLLBACK: --rollback restores a normal local repo
# ---------------------------------------------------------------------------
VC="$ROOT/C"
make_vault "$VC"
bash "$HELPER" "$VC" --sidecar "$SIDE" --quiet
[ -f "$VC/.git" ] && pass "D pre-rollback .git is a pointer" || fail "D pre-rollback .git not a pointer"
bash "$HELPER" "$VC" --sidecar "$SIDE" --rollback --quiet
rc=$?
[ "$rc" = 0 ] && pass "D rollback exit 0" || fail "D rollback exit=$rc"
[ -d "$VC/.git" ] && pass "D .git is a normal dir again" || fail "D .git not restored to dir"
[ -d "$VC/.smart-env" ] && [ ! -L "$VC/.smart-env" ] && pass "D .smart-env restored as real dir" \
                                                       || fail "D .smart-env not restored"
gitq "$VC" status && pass "D git functional after rollback" || fail "D git broke after rollback"

# ---------------------------------------------------------------------------
# E. LIVE-WORKTREE GUARD: refuse (exit 1) when a linked worktree exists
# ---------------------------------------------------------------------------
VD="$ROOT/D"
make_vault "$VD"
gitq "$VD" worktree add "$VD/.claude/worktrees/live" -b livebranch HEAD
bash "$HELPER" "$VD" --sidecar "$SIDE" --quiet >/dev/null 2>&1
rc=$?
[ "$rc" = 1 ] && pass "E refuses with live linked worktree (exit 1)" \
              || fail "E expected refuse exit 1, got $rc"
# and --force overrides
bash "$HELPER" "$VD" --sidecar "$SIDE" --force --quiet >/dev/null 2>&1
rc=$?
[ "$rc" = 0 ] && pass "E --force overrides the guard (exit 0)" || fail "E --force exit=$rc"

# ---------------------------------------------------------------------------
# F. DRY-RUN: changes nothing
# ---------------------------------------------------------------------------
VE="$ROOT/E"
make_vault "$VE"
bash "$HELPER" "$VE" --sidecar "$SIDE" --dry-run --quiet >/dev/null 2>&1
[ -d "$VE/.git" ] && [ ! -L "$VE/.smart-env" ] && pass "F dry-run changed nothing" \
                                               || fail "F dry-run mutated the vault"

echo
echo "--- MANUAL (operator-gated, cannot automate in CI) ---"
echo "iPhone round-trip: with the vault in iCloud Drive + this relocation applied,"
echo "  edit a note on iPhone (Obsidian/Files) → confirm it appears on the Mac, and"
echo "  vice-versa, while Activity Monitor shows fileproviderd/bird idle during a"
echo "  Mac-side git gc. (Done= part b.)"
echo

if [ "$fails" -gt 0 ]; then echo "FAILED: $fails"; exit 1; fi
echo "ALL TESTS PASSED"
