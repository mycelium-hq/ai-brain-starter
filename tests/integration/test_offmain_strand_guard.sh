#!/usr/bin/env bash
# Negative-control test for git-hooks/guard-session-artifacts-on-default-branch.sh
#
# Proves the guard FIRES on the failure it exists to catch (a session-close
# artifact staged while off the default branch) and does NOT over-block
# (plain code work off-branch, on-branch commits, and the bypass all pass).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
GUARD="${1:-$HERE/../../git-hooks/guard-session-artifacts-on-default-branch.sh}"
[ -f "$GUARD" ] || { echo "guard not found: $GUARD"; exit 2; }

# WHY THIS TEST SANDBOXES HOME
#
# Every case below runs `git init` and `git commit` in a throwaway repo. A
# throwaway repo is not a hermetic one: git still reads the developer's own
# global configuration, and two keys in it reach straight into this test.
#
#   core.hooksPath      Commonly set globally (it is on the maintainer's
#                       machine, pointing at ~/.claude/git-hooks). Every
#                       `git commit` below then EXECUTES the operator's real
#                       global pre-commit/post-commit hooks - arbitrary local
#                       code, run eight times per suite run, inside a test that
#                       is only supposed to exercise the guard passed as $1.
#   init.defaultBranch  Feeds the very fallback the guard under test resolves
#                       (guard line: `git config --get init.defaultBranch`).
#                       On a machine with `defaultBranch = master` the
#                       "default-branch + artifact -> ALLOW" case FAILS against
#                       a completely correct guard, because the guard computes
#                       _def=master while the case is on main. Verified by
#                       running this file under that config: 1 FAILED.
#
# So the assertions were a function of the machine, not of the guard. HOME alone
# does not sandbox ~ on Windows - see lib/sandbox_home.sh.
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$HERE/lib/sandbox_home.sh"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
sandbox_home "$SANDBOX"
# HOME closes ~/.gitconfig and (with XDG_CONFIG_HOME unset) ~/.config/git/config
# too. These close the two routes it does not: an exported XDG_CONFIG_HOME, and
# the system-level gitconfig. Same defect, remaining spellings.
export XDG_CONFIG_HOME="$SANDBOX/.config"
export GIT_CONFIG_NOSYSTEM=1

fails=0
pass(){ echo "PASS: $1"; }
fail(){ echo "FAIL: $1"; fails=$((fails+1)); }

# The guard ALLOWS an empty index, so a setup step that silently fails to stage
# the artifact turns an ALLOW case into a pass that tested nothing. Measured
# 2026-09-24: case (e) wrote into Meta/Sessions/ right after a checkout had
# removed that directory, staged nothing, and passed. Call this immediately
# before the guard in every bespoke case; it reports an EXIT= value that matches
# neither 0 nor 1, so the case fails instead.
require_staged(){
  if git diff --cached --quiet -- "$1"; then echo "EXIT=setup-staged-nothing:$1"; exit 0; fi
}

# Negative control for the sandbox itself. If it ever silently stops taking
# effect, every case below quietly goes back to executing the operator's real
# global git hooks and resolving their real init.defaultBranch - and the cases
# would still pass on a machine where those happen to be benign. This is the
# only thing that would say so.
hermetic_check(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    echo "core.hooksPath=$(git config --get core.hooksPath 2>/dev/null || true)"
    echo "init.defaultBranch=$(git config --get init.defaultBranch 2>/dev/null || true)"
  ) > "$d/out" 2>&1
  local leaked
  leaked="$(grep -E '^(core\.hooksPath|init\.defaultBranch)=.+' "$d/out" || true)"
  if [ -z "$leaked" ]; then
    pass "sandbox holds (no real global git config reaches the cases)"
  else
    fail "sandbox leaked real git config: $(printf '%s' "$leaked" | tr '\n' ' ')"
  fi
  rm -rf "$d"
}
hermetic_check

# name, branch, stage-path, bypass(0/1), expect_exit, extra-pattern(optional)
run_case(){
  local name="$1" branch="$2" path="$3" bypass="$4" expect="$5" extra="${6:-}"
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    mkdir -p .githooks
    cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    [ -n "$extra" ] && printf '%s\n' "$extra" > .githooks/session-artifact-paths.txt
    echo x > seed; git add seed; git commit -qm seed
    [ "$branch" != "main" ] && git checkout -q -b "$branch"
    mkdir -p "$(dirname "$path")"; echo content > "$path"; git add -- "$path"
    [ "$bypass" = "1" ] && export SESSION_ARTIFACT_BRANCH_BYPASS=1
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "$expect" ]; then pass "$name (exit $got)"; else fail "$name (got '$got' want '$expect')"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

run_case "default-branch + artifact -> ALLOW"          main      "Meta/Sessions/2026-07-07.md"   0 0
run_case "feature-branch + artifact -> BLOCK"          claude/x  "Meta/Sessions/2026-07-07.md"   0 1
run_case "feature-branch + code-only -> ALLOW"         claude/x  "src/foo.py"                     0 0
run_case "feature-branch + artifact + bypass -> ALLOW" claude/x  "Meta/Decisions/d.md"            1 0
run_case "feature-branch + aggregate -> BLOCK"         claude/x  "Meta/Last Session.md"           0 1
run_case "feature-branch + emoji-prefixed artifact -> BLOCK" claude/x "⚙️ Meta/Sessions/e.md"     0 1
run_case "feature-branch + per-repo extension -> BLOCK" claude/x "notes/Weekly Digest.md"         0 1 "Weekly Digest.md"
run_case "feature-branch + unlisted path -> ALLOW"     claude/x  "notes/random.md"                0 0

# --- Merge carve-out (the DEFECT this pairs with: a plain `git merge origin/main`
# into a feature branch stages main's OWN unchanged session artifacts, and the
# guard used to refuse that routine merge, forcing SESSION_ARTIFACT_BRANCH_BYPASS=1
# on content that could never strand). run_case above cannot express a merge
# (single branch + single staged path), so these are bespoke like hermetic_check.
# NOTE: (b) "a NEW artifact on a feature branch -> refused" is already proven by
# "feature-branch + artifact -> BLOCK" above -- a brand-new path has no origin/
# MERGE_HEAD blob to match, so it is untouched by the carve-out. Not duplicated
# here on purpose.

# (a) merging main's unchanged artifact into a feature branch -> ALLOW.
# One-line mutation that turns this red: delete (or stub to always-0) the
# "${_have_origin_ref}"/"${_have_merge_head}" exemption block in the guard, i.e.
# revert to the pre-carve-out matching logic -- this case then gets EXIT=1.
merge_case_allow_unchanged_artifact(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add seed.txt; git commit -qm seed
    mkdir -p "Meta/Sessions"; echo "seed-session" > "Meta/Sessions/a.md"
    git add "Meta/Sessions/a.md"; git commit -qm "artifact on main"
    git update-ref refs/remotes/origin/main main
    git checkout -q -b feature HEAD~1
    echo "feature work" > feature.txt; git add feature.txt; git commit -qm "feature work"
    mkdir -p .githooks; cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    git merge --no-commit --no-ff origin/main >/dev/null 2>&1
    require_staged "Meta/Sessions/a.md"
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "0" ]; then pass "(a) merge main's unchanged artifact into feature -> ALLOW (exit $got)"; else fail "(a) merge main's unchanged artifact into feature -> ALLOW (got '$got' want 0)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

# (b) sentinel note only -- see comment block above; no separate function.
# One-line mutation that turns "feature-branch + artifact -> BLOCK" red: widen
# the exemption to match on PATTERN/PATH alone instead of blob equality (e.g.
# `_exempt=1` as soon as `_matched_pat` is set, without checking `_sblob`
# against `_oblob`/`_mblob`) -- a brand-new artifact would then be wrongly
# exempted just because its path looks like a session artifact.

# (c) a merge whose RESOLUTION modifies an artifact -> BLOCK. Same merge as (a),
# but the staged content is edited after the merge stages it, so it no longer
# matches origin/<default> OR MERGE_HEAD.
merge_case_block_resolution_modifies(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add seed.txt; git commit -qm seed
    mkdir -p "Meta/Sessions"; echo "seed-session" > "Meta/Sessions/a.md"
    git add "Meta/Sessions/a.md"; git commit -qm "artifact on main"
    git update-ref refs/remotes/origin/main main
    git checkout -q -b feature HEAD~1
    echo "feature work" > feature.txt; git add feature.txt; git commit -qm "feature work"
    mkdir -p .githooks; cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    git merge --no-commit --no-ff origin/main >/dev/null 2>&1
    echo "resolved differently" > "Meta/Sessions/a.md"
    git add "Meta/Sessions/a.md"
    require_staged "Meta/Sessions/a.md"
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "1" ]; then pass "(c) merge resolution modifies artifact -> BLOCK (exit $got)"; else fail "(c) merge resolution modifies artifact -> BLOCK (got '$got' want 1)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

# (d) origin ref ABSENT (no remote configured at all, and no merge in progress)
# -> BLOCK, even though the staged content is byte-identical to LOCAL main.
# Proves the exemption never falls back to the local <default> branch and never
# treats "cannot resolve the ref" as "assume it matches" (the empty-string
# footgun: comparing two failed lookups' empty output would wrongly be equal).
no_origin_ref_case_block(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add seed.txt; git commit -qm seed
    mkdir -p "Meta/Sessions"; echo "shared content" > "Meta/Sessions/a.md"
    git add "Meta/Sessions/a.md"; git commit -qm "artifact on main"
    git checkout -q -b feature HEAD~1
    mkdir -p .githooks; cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    mkdir -p Meta/Sessions
    # The same bytes main's commit holds. Written as a literal, not read back
    # with `git show main:...`: check-frozen-before-state cannot tell this temp
    # repo from the real one and flags a moving-ref read.
    echo "shared content" > Meta/Sessions/a.md
    git add Meta/Sessions/a.md
    require_staged "Meta/Sessions/a.md"
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "1" ]; then pass "(d) origin ref absent, content matches local main only -> BLOCK (exit $got)"; else fail "(d) origin ref absent, content matches local main only -> BLOCK (got '$got' want 1)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

# (e) extra: the origin/<default> route alone, with no merge in progress at all
# (e.g. a cherry-pick or a manual re-add of main's content) -> ALLOW. Proves the
# two exemption routes are independent ORs, not "origin ref only counts mid-merge".
origin_ref_only_case_allow(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add seed.txt; git commit -qm seed
    mkdir -p "Meta/Sessions"; echo "already-on-main" > "Meta/Sessions/a.md"
    git add "Meta/Sessions/a.md"; git commit -qm "artifact on main"
    git update-ref refs/remotes/origin/main main
    git checkout -q -b feature HEAD~1
    mkdir -p .githooks; cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    # The checkout above removed Meta/Sessions/ (a.md was its only file), so the
    # directory has to be recreated before the write. Same bytes as main's copy,
    # written as a literal for the reason given in case (d).
    mkdir -p Meta/Sessions
    echo "already-on-main" > Meta/Sessions/a.md
    git add Meta/Sessions/a.md
    require_staged "Meta/Sessions/a.md"
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "0" ]; then pass "(e) origin-ref route alone, no active merge -> ALLOW (exit $got)"; else fail "(e) origin-ref route alone, no active merge -> ALLOW (got '$got' want 0)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

# (f) extra: a staged DELETION of an artifact -> BLOCK. There is no staged blob
# to compare (":${path}" fails to resolve), so it falls through as a hit rather
# than silently being treated as exempt.
staged_deletion_case_block(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    mkdir -p "Meta/Sessions"; echo "seed-session" > "Meta/Sessions/a.md"
    git add "Meta/Sessions/a.md"; git commit -qm seed
    git update-ref refs/remotes/origin/main main
    git checkout -q -b feature
    mkdir -p .githooks; cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    git rm -q --cached Meta/Sessions/a.md
    require_staged "Meta/Sessions/a.md"
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "1" ]; then pass "(f) staged deletion of an artifact -> BLOCK, fail-closed (exit $got)"; else fail "(f) staged deletion of an artifact -> BLOCK, fail-closed (got '$got' want 1)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

# (g) extra: emoji + space in the path ("⚙️ Meta"), through the merge-exempt
# route -- proves the byte-identity check is not just ASCII-safe.
merge_case_allow_emoji_path(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add seed.txt; git commit -qm seed
    mkdir -p "⚙️ Meta/Sessions"; echo "seed-session" > "⚙️ Meta/Sessions/e.md"
    git add "⚙️ Meta/Sessions/e.md"; git commit -qm "emoji artifact on main"
    git update-ref refs/remotes/origin/main main
    git checkout -q -b feature HEAD~1
    echo "feature work" > feature.txt; git add feature.txt; git commit -qm "feature work"
    mkdir -p .githooks; cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    git merge --no-commit --no-ff origin/main >/dev/null 2>&1
    require_staged "⚙️ Meta/Sessions/e.md"
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "0" ]; then pass "(g) merge unchanged emoji-prefixed artifact -> ALLOW (exit $got)"; else fail "(g) merge unchanged emoji-prefixed artifact -> ALLOW (got '$got' want 0)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

# (h) merging a TOPIC branch that carries its own artifact -> BLOCK. MERGE_HEAD is
# not on the default branch, so its copy proves nothing about stranding.
# Mutation that turns this red: honour MERGE_HEAD whenever it exists (drop the
# is-ancestor check that sets _merge_head_on_default).
merge_topic_branch_case_block(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add seed.txt; git commit -qm seed
    git update-ref refs/remotes/origin/main main
    git checkout -q -b topic
    mkdir -p "Meta/Sessions"; echo "stranded on topic" > "Meta/Sessions/t.md"
    git add "Meta/Sessions/t.md"; git commit -qm "artifact stranded on a topic branch"
    git checkout -q main; git checkout -q -b feature
    echo "feature work" > feature.txt; git add feature.txt; git commit -qm "feature work"
    mkdir -p .githooks; cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    git merge --no-commit --no-ff topic >/dev/null 2>&1
    require_staged "Meta/Sessions/t.md"
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "1" ]; then pass "(h) merge a topic branch carrying its own artifact -> BLOCK (exit $got)"; else fail "(h) merge a topic branch carrying its own artifact -> BLOCK (got '$got' want 1)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

# (i) merging LOCAL main while origin/main is behind it -> ALLOW through the
# MERGE_HEAD route alone (origin/main does not have the file yet). Proves the
# narrowing in (h) did not also shut the route it exists for.
merge_local_default_ahead_case_allow(){
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 99
    git init -q -b main
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add seed.txt; git commit -qm seed
    git update-ref refs/remotes/origin/main main
    mkdir -p "Meta/Sessions"; echo "closed on local main" > "Meta/Sessions/a.md"
    git add "Meta/Sessions/a.md"; git commit -qm "artifact on local main, not pushed"
    git checkout -q -b feature HEAD~1
    echo "feature work" > feature.txt; git add feature.txt; git commit -qm "feature work"
    mkdir -p .githooks; cp "$GUARD" .githooks/guard.sh; chmod +x .githooks/guard.sh
    git merge --no-commit --no-ff main >/dev/null 2>&1
    require_staged "Meta/Sessions/a.md"
    .githooks/guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got; got="$(sed -n 's/^EXIT=//p' "$d/out")"
  if [ "$got" = "0" ]; then pass "(i) merge local main ahead of origin/main -> ALLOW via MERGE_HEAD (exit $got)"; else fail "(i) merge local main ahead of origin/main -> ALLOW via MERGE_HEAD (got '$got' want 0)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

# (j) cost does not grow with the number of staged paths. 500 staged NON-artifact
# files must not start a process per path: git and grep are counted through PATH
# shims. Measured 2026-09-24: a per-path `printf | grep` took 30.8s on 3000 files.
# Mutation that turns this red: go back to spawning grep inside the path loop.
spawn_count_does_not_scale_with_staged_paths(){
  local d; d="$(mktemp -d)"
  local real_git real_grep; real_git="$(command -v git)"; real_grep="$(command -v grep)"
  mkdir -p "$d/shim"
  printf '#!/bin/sh\necho git >> "%s/spawns"\nexec "%s" "$@"\n' "$d" "$real_git" > "$d/shim/git"
  printf '#!/bin/sh\necho grep >> "%s/spawns"\nexec "%s" "$@"\n' "$d" "$real_grep" > "$d/shim/grep"
  chmod +x "$d/shim/git" "$d/shim/grep"
  (
    cd "$d" || exit 99
    git init -q -b main repo; cd repo || exit 99
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add seed.txt; git commit -qm seed
    git checkout -q -b feature
    mkdir -p src; i=0; while [ "$i" -lt 500 ]; do echo "$i" > "src/f$i.txt"; i=$((i+1)); done
    git add src
    cp "$GUARD" guard.sh; chmod +x guard.sh
    : > "$d/spawns"
    PATH="$d/shim:$PATH" ./guard.sh; echo "EXIT=$?"
  ) > "$d/out" 2>&1
  local got n; got="$(sed -n 's/^EXIT=//p' "$d/out")"; n="$(wc -l < "$d/spawns" | tr -d ' ')"
  if [ "$got" = "0" ] && [ "$n" -lt 20 ]; then pass "(j) 500 staged paths -> $n git/grep spawns, independent of path count"; else fail "(j) 500 staged paths -> got EXIT '$got' and $n git/grep spawns (want 0 and under 20)"; sed 's/^/    /' "$d/out"; fi
  rm -rf "$d"
}

merge_case_allow_unchanged_artifact
merge_case_block_resolution_modifies
no_origin_ref_case_block
origin_ref_only_case_allow
staged_deletion_case_block
merge_case_allow_emoji_path
merge_topic_branch_case_block
merge_local_default_ahead_case_allow
spawn_count_does_not_scale_with_staged_paths

echo "---"
if [ "$fails" -eq 0 ]; then echo "ALL PASS ($((0)) failures)"; exit 0; else echo "$fails FAILED"; exit 1; fi
