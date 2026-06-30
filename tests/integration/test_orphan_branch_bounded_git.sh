#!/usr/bin/env bash
# Regression test for hooks/surface-orphan-claude-branches.py (MYC-2348 / MYC-2361).
#
# Locks the bounded git fan-out fix. The hook surfaces, at SessionStart, the count
# of orphan claude/* branches. The pre-fix implementation ran one `git rev-list`
# per branch -- O(branches) subprocesses -- which on a large vault (~150 branches
# against a 60K-file index) cost ~2.7s at EVERY session open (SLOW-INSTALL-FROM-
# LAZY-PLUMBING). The fix uses TWO git calls total, independent of branch count.
#
# This is the deterministic class guard the static audit-sessionstart-boundedness
# gate CANNOT catch: that gate checks filesystem-walk boundedness (flock + cooldown
# + deadline); a per-branch SUBPROCESS fan-out is bounded-by-construction to it yet
# still O(branches) in cost. Here we count actual git invocations via a PATH shim
# and assert the count does not scale with branch count. Reintroduce the per-branch
# loop and the git-call count jumps from a small constant to O(branches): red.
#
# Also asserts CORRECTNESS: only branches with commits not reachable from base are
# counted; fully-merged claude/* branches are excluded.
#
# Stdlib python3 + bash + git only. No network. One owned temp root; the real vault
# and ~/.claude are never touched.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/surface-orphan-claude-branches.py"

PASS=0
FAIL=0
ROOT="$(mktemp -d)"
cleanup() { rm -rf "$ROOT"; }
trap cleanup EXIT

ok()  { PASS=$((PASS+1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL+1)); echo "FAIL  $1 :: $2"; }

REAL_GIT="$(command -v git)"
if [ -z "$REAL_GIT" ]; then echo "FAIL  git not found on PATH"; exit 1; fi

SN=0   # shim/run counter (run_hook runs in the parent shell, so this persists)

# build_vault <n_orphan> <n_merged> -- a vault-shaped repo (has .git + a *Meta dir,
# base branch 'main') with n_orphan claude/* branches each carrying one unmerged
# commit and n_merged claude/* branches fully reachable from main. Echoes the path.
# Arithmetic for-loops (not `seq`): BSD `seq 1 0` prints "1 0", GNU prints nothing.
build_vault() {
  local n_orphan="$1" n_merged="$2" repo i
  # mktemp -d for a unique dir: build_vault runs inside $(...) (a subshell), so a
  # parent-scoped counter would not persist and every vault would collide.
  repo="$(mktemp -d "$ROOT/vault.XXXXXX")"
  mkdir -p "$repo/Meta"
  git init -q -b main "$repo"
  git -C "$repo" config user.email t@t.t
  git -C "$repo" config user.name t
  git -C "$repo" commit -q --allow-empty -m base
  for (( i=1; i<=n_orphan; i++ )); do
    git -C "$repo" checkout -q -b "claude/orphan$i" main
    git -C "$repo" commit -q --allow-empty -m "orphan work $i"
  done
  for (( i=1; i<=n_merged; i++ )); do
    git -C "$repo" branch "claude/merged$i" main   # at main, no new commits -> merged
  done
  git -C "$repo" checkout -q main
  echo "$repo"
}

# run_hook <repo> -- run the hook with cwd=repo under a git-counting PATH shim.
# Sets OUT (stdout), RC, NGIT (number of git invocations).
run_hook() {
  local repo="$1" shimdir counter
  SN=$((SN+1)); shimdir="$ROOT/shim$SN"; counter="$ROOT/cnt$SN"
  mkdir -p "$shimdir"; : > "$counter"
  cat > "$shimdir/git" <<SHIM
#!/usr/bin/env bash
printf 'x' >> "$counter"
exec "$REAL_GIT" "\$@"
SHIM
  chmod +x "$shimdir/git"
  # cd binds before the pipe (| is higher precedence than &&), so printf and
  # python3 both run with cwd=repo; shimdir is first on python3's PATH so the
  # hook's child `git` calls route through the counter.
  OUT="$(cd "$repo" && printf '{}' | PATH="$shimdir:$PATH" python3 "$HOOK" 2>/dev/null)"
  RC=$?
  NGIT="$(wc -c < "$counter" | tr -d ' ')"
}

# --- Scenario A: correctness -- 5 orphan + 3 merged => reports 5 ----------------
run_hook "$(build_vault 5 3)"
case "$OUT" in
  *'"systemMessage"'*'[orphan-branches] 5 '*'branch(es)'*) ok "correctness: 5 orphan, 3 merged -> reports 5" ;;
  *) bad "correctness: reports 5 orphans" "out=${OUT:0:160}" ;;
esac

# --- Scenario B: merged-only => silent (no systemMessage, rc 0) -----------------
run_hook "$(build_vault 0 4)"
if [ "$RC" = 0 ] && [ -z "$OUT" ]; then
  ok "merged-only vault is silent"
else
  bad "merged-only vault is silent" "rc=$RC out=${OUT:0:120}"
fi

# --- Scenario C: BOUNDED fan-out -- git calls do NOT scale with branch count ----
# 8 vs 40 orphan branches must cost the SAME (small) git-call count. The pre-fix
# loop would be ~ (3 + N): 11 vs 43. Assert both <= 6 AND the 40-branch count does
# not exceed the 8-branch count -- the precise O(branches) signature.
run_hook "$(build_vault 8 0)";  N8="$NGIT"
run_hook "$(build_vault 40 0)"; N40="$NGIT"
if [ "$N8" -le 6 ] && [ "$N40" -le 6 ]; then
  ok "bounded git fan-out: 8-branch=$N8 calls, 40-branch=$N40 calls (both <= 6)"
else
  bad "bounded git fan-out" "8-branch=$N8 calls, 40-branch=$N40 calls (want both <= 6; O(branches) regression?)"
fi
if [ "$N40" -le "$N8" ]; then
  ok "git-call count does not grow with branch count (8->$N8, 40->$N40)"
else
  bad "git-call count grows with branch count" "8->$N8 but 40->$N40 (O(branches) fan-out reintroduced)"
fi

# --- Scenario D: NEGATIVE CONTROL -- prove the shim+counter actually detects the
# O(branches) fan-out it is meant to catch. Run the PRE-FIX shape (one rev-list
# per branch) by hand over the 40-branch vault under the shim; the git-call count
# MUST blow past the bounded ceiling. If it does not, the bounded assertion above
# is vacuous (a broken counter would pass everything).
NEG_VAULT="$(build_vault 40 0)"
SN=$((SN+1)); negshim="$ROOT/shim$SN"; negcnt="$ROOT/cnt$SN"
mkdir -p "$negshim"; : > "$negcnt"
cat > "$negshim/git" <<SHIM
#!/usr/bin/env bash
printf 'x' >> "$negcnt"
exec "$REAL_GIT" "\$@"
SHIM
chmod +x "$negshim/git"
(
  cd "$NEG_VAULT" || exit 1
  export PATH="$negshim:$PATH"
  for b in $(git for-each-ref --format='%(refname:short)' refs/heads/claude/); do
    git rev-list --count "main..$b" >/dev/null
  done
)
NEG="$(wc -c < "$negcnt" | tr -d ' ')"
if [ "$NEG" -gt 6 ]; then
  ok "negative control: pre-fix per-branch loop trips the ceiling ($NEG git calls > 6)"
else
  bad "negative control" "per-branch loop made only $NEG git calls (counter mechanism broken?)"
fi

echo "----"
echo "orphan-branch bounded-git: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
