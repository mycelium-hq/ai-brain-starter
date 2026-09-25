#!/usr/bin/env bash
# guard-session-artifacts-on-default-branch.sh
#
# Refuse committing session-close vault artifacts while the checkout is on a
# NON-default branch. Prevents the SESSIONCLOSE-COMMITS-TO-CURRENT-BRANCH-NOT-MAIN
# stranding class: if a checkout is parked off the default branch, every
# session-close artifact (Sessions/, Decisions/, the aggregates, ...) silently
# accumulates on a topic branch instead of landing on the default branch, and the
# local default branch quietly diverges — a failure that can go unnoticed for days
# under multiple concurrent sessions sharing one git dir.
#
# Fires at the git pre-commit CHOKEPOINT (pre-commit-template.sh chains it) and at
# pre-merge-commit (pre-merge-commit-template.sh chains it the same way), so it
# catches a session-close cascade, an auto-append, a manual commit, an agent, AND
# a conflict-free `git merge` that git auto-commits without ever running
# pre-commit. Off-branch code work is unaffected — it only blocks when a
# session-close artifact is staged.
#
# CARVE-OUT: a staged artifact is exempt when the STAGED tree already agrees with
# the default branch's remote-tracking ref (refs/remotes/origin/<default>), or —
# while merging a commit that is already on the default branch — with MERGE_HEAD,
# at that exact path: same blob AND same mode, OR the path is absent from BOTH
# (a staged deletion that matches a deletion the ref already made — deleting
# something already gone from the default branch cannot strand anything). A merge
# of a topic branch gets no MERGE_HEAD exemption. Content already on the default
# branch cannot be stranded by this commit, so a plain `git merge origin/main`
# into a feature branch (which stages main's own unchanged session artifacts) no
# longer needs the bypass. A NEW artifact, a mode-only change on an artifact whose
# blob matches the ref (chmod +x, a symlink swap), a merge whose resolution
# CHANGES an artifact, and a staged deletion the ref does NOT already have are all
# still refused. A missing or unreadable ref never grants the exemption — it just
# doesn't run (fail closed). At pre-merge-commit time MERGE_HEAD is not yet
# written (measured against git 2.50.1), so that route is inactive there and only
# the origin route can exempt — see pre-merge-commit-template.sh.
#
# COST: independent of how many staged paths match a session-artifact pattern.
# Exactly one `git diff-index` per ELIGIBLE exemption route (at most 2: origin,
# MERGE_HEAD), restricted by pathspec to just the matched candidates, plus the
# fixed handful of setup spawns — never a process per candidate path.
#
# INSTALL: called by the pre-commit hook (pre-commit-template.sh chains it, or a
# repo-local .githooks/pre-commit invokes it) and by the pre-merge-commit hook
# (pre-merge-commit-template.sh chains it the same way — see that file's header).
# Vendor this file byte-for-byte into consuming repos that keep their own
# .githooks/.
#
# CONFIG: extend the artifact path set per repo with a file at
#   <repo>/.githooks/session-artifact-paths.txt   (one substring per line; # comments ok)
#
# Exit 0 = allow. Exit 1 = refuse. Bypass: SESSION_ARTIFACT_BRANCH_BYPASS=1.
set -uo pipefail

[ -n "${SESSION_ARTIFACT_BRANCH_BYPASS:-}" ] && exit 0

_cur="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
# Detached HEAD (mid rebase/cherry-pick/bisect) is not the parked-branch case — allow.
[ "${_cur}" = "HEAD" ] && exit 0

# Default branch: prefer origin/HEAD, then init.defaultBranch, then "main".
_def="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
[ -z "${_def}" ] && _def="$(git config --get init.defaultBranch 2>/dev/null || true)"
[ -z "${_def}" ] && _def="main"

# On the default branch nothing strands — allow.
[ "${_cur}" = "${_def}" ] && exit 0

# Off the default branch: block ONLY if a session-close artifact is staged.
#
# NUL-separated, rename detection OFF, no explicit compare-from revision: git
# never quotes/escapes a path in -z output, so a name holding a double quote,
# a backslash, a tab or an embedded newline round-trips as its real bytes
# instead of a display string that names a DIFFERENT path (or nothing).
# --no-renames means a rename is one deletion plus one addition, each checked
# on its own path — never paired and skipped as a pair.
#
# No explicit `HEAD` argument: `git diff --cached` already defaults to
# comparing against HEAD, and — the case that matters here — against the
# EMPTY TREE when HEAD is unborn (a fresh `git checkout --orphan`, before its
# first commit). Passing `HEAD` explicitly forces resolution of a commit that
# does not exist yet on that branch, which FAILS and produces no output; that
# used to read as "nothing is staged", so the guard exited ALLOW before the
# artifact-matching loop below ever ran — no matter what was actually staged.
# Output goes to a real file, never `done < <(...)`, with its own exit status
# checked directly (same reasoning as the diff-index fix below: a process
# substitution only ever exposes the trailing `read`'s exit status). ANY
# failure of this listing — not just the unborn-HEAD case — used to produce
# empty output indistinguishable from a genuinely clean index. This is the
# one listing every later check depends on, so its own failure REFUSES
# rather than silently allowing.
# The scratch dir is allocated under $(git rev-parse --git-dir) FIRST, falling
# back to $TMPDIR (mktemp's own default) only if that fails. The git dir is on
# the same filesystem git already writes objects/refs/index to, so it is
# almost always writable whenever `git commit` can succeed at all — unlike
# $TMPDIR/tmp, which macOS periodically reaps, and which can be full or
# read-only independent of the repo. A mktemp failure here used to REFUSE
# unconditionally, even with zero session artifacts staged — contradicting
# this guard's own contract (header: "Off-branch code work is unaffected").
# Measured real trigger: TMPDIR pointing at a reaped /var/folders dir, or /tmp
# full/read-only — neither touches the git dir. Only if BOTH the git-dir and
# the $TMPDIR attempt fail does the guard still refuse outright (fail closed —
# a repo whose own .git dir cannot be written to has bigger problems than this
# hook, and this is the one case too degraded to tell artifact-staged from
# code-only apart).
_gitdir="$(git rev-parse --git-dir 2>/dev/null)"
_staged_dir=""
if [ -n "${_gitdir}" ]; then
  _staged_dir="$(mktemp -d "${_gitdir}/guard-staged.XXXXXX" 2>/dev/null)" || _staged_dir=""
fi
if [ -z "${_staged_dir}" ]; then
  _staged_dir="$(mktemp -d 2>/dev/null)" || _staged_dir=""
fi
if [ -z "${_staged_dir}" ]; then
  echo "pre-commit: REFUSED — could not create a scratch dir to list staged paths (mktemp failed under both \$(git rev-parse --git-dir) and \$TMPDIR)." >&2
  echo "  Bypass: SESSION_ARTIFACT_BRANCH_BYPASS=1 git commit ...   (or git commit --no-verify)." >&2
  exit 1
fi
_cleanup_staged_dir() { [ -n "${_staged_dir}" ] && rm -rf "${_staged_dir}"; }
trap _cleanup_staged_dir EXIT

_staged_out="${_staged_dir}/staged.nul"
git diff --cached --name-only -z --no-renames >"${_staged_out}" 2>/dev/null
if [ "$?" -ne 0 ]; then
  echo "pre-commit: REFUSED — could not list staged paths (git diff --cached failed)." >&2
  exit 1
fi
_staged_paths=()
while IFS= read -r -d '' _p; do
  _staged_paths+=("${_p}")
done < "${_staged_out}"
[ "${#_staged_paths[@]}" -eq 0 ] && exit 0

# Generic session-close outputs. Literal substring match so a folder icon prefix
# (e.g. an emoji-tagged "Meta" folder) still matches on "Meta/Sessions/".
_patterns='Meta/Sessions/
Meta/Decisions/
Meta/Last Session.md
Meta/Decision Log.md
Meta/Current Priorities.md'

# Optional per-repo extensions (one substring per line; # comments allowed).
_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
_extra="${_root}/.githooks/session-artifact-paths.txt"
[ -n "${_root}" ] && [ -f "${_extra}" ] && _patterns="${_patterns}
$(cat "${_extra}")"

# Parse the patterns ONCE.
_pats=()
while IFS= read -r _pat; do
  [ -z "${_pat}" ] && continue
  case "${_pat}" in \#*) continue ;; esac
  _pats+=("${_pat}")
done <<EOF
${_patterns}
EOF
[ "${#_pats[@]}" -eq 0 ] && exit 0

# Which staged paths match a session-artifact pattern at all — the ONLY paths
# that ever need an exemption lookup. An in-process substring test, so this
# stays cheap however many paths are staged (matches fd7509c's approach).
_artifact_paths=()
_artifact_pats=()
for _path in "${_staged_paths[@]}"; do
  _matched_pat=""
  for _pat in "${_pats[@]}"; do
    case "${_path}" in *"${_pat}"*) _matched_pat="${_pat}"; break ;; esac
  done
  [ -z "${_matched_pat}" ] && continue
  _artifact_paths+=("${_path}")
  _artifact_pats+=("${_matched_pat}")
done
[ "${#_artifact_paths[@]}" -eq 0 ] && exit 0
_n_artifacts="${#_artifact_paths[@]}"

# Resolve the two exemption refs ONCE. Missing/unreadable => that route simply
# never grants the exemption below (fail closed), it does not error out.
_origin_ref="refs/remotes/origin/${_def}"
_have_origin_ref=0
git rev-parse --quiet --verify "${_origin_ref}" >/dev/null 2>&1 && _have_origin_ref=1

# MERGE_HEAD only counts when the commit being merged is already on the default
# branch (reachable from local <default> or origin/<default>). Merging a topic
# branch that carries its own session artifacts would otherwise copy them onto
# this branch without a refusal, which is the stranding this guard exists for.
# At pre-merge-commit time MERGE_HEAD is not written yet (measured against git
# 2.50.1: `git rev-parse --verify MERGE_HEAD` fails there), so this stays 0 on
# that hook and only the origin route below can exempt anything — by design,
# not a special case: an unresolvable MERGE_HEAD is just another unreadable ref.
_merge_head_on_default=0
if git rev-parse --quiet --verify MERGE_HEAD >/dev/null 2>&1; then
  if git merge-base --is-ancestor MERGE_HEAD "refs/heads/${_def}" 2>/dev/null; then
    _merge_head_on_default=1
  elif [ "${_have_origin_ref}" = "1" ] && git merge-base --is-ancestor MERGE_HEAD "${_origin_ref}" 2>/dev/null; then
    _merge_head_on_default=1
  fi
fi

# One `git diff-index` per active route, restricted by pathspec to exactly the
# candidate artifact paths (never the whole repo, however large): the output
# is the subset of candidates whose STAGED blob or mode differs from that ref.
# diff-index compares full tree entries (blob AND mode), so a chmod +x or a
# symlink swap shows up here even when the bytes match. A candidate the ref
# has no entry for AND the index also lacks (a staged deletion the ref already
# made) never appears either way, so it reads as "no difference" — exempt.
# This is the fix for the review's HIGH cost finding: two spawns total here,
# never one per candidate, so a merge staging thousands of unchanged artifacts
# costs the same two spawns as one.
# --literal-pathspecs: a candidate path is always used AS A PATHSPEC ARGUMENT
# here, and without this flag git treats one that STARTS WITH ':' as pathspec
# MAGIC (":(glob)...", ":!...", etc), not a literal path. A path git cannot
# parse as magic (":Meta/Sessions/x.md" — no recognized keyword) is then
# silently dropped from the query, which reads as "absent from the diff" —
# wrongly EXEMPT, even brand new. Same bug class as the re-parsed `ref:path`
# quoting fix above, one layer over: it is not enough to stop re-parsing a
# path as a revision string if the path is still re-parsed as a pathspec.
#
# Output goes to a REAL FILE, never `done < <(...)`: a process substitution
# only ever exposes the trailing `read`'s own exit status, not the command
# feeding it, so a `git diff-index` that FAILS (E2BIG on a huge pathspec, an
# unreadable object, an index lock) produces empty output that is
# indistinguishable from "genuinely nothing differs" — every candidate on
# that route then read as exempt. `_origin_route_ok` / `_mh_route_ok` are 1
# ONLY when the ref exists AND the comparison itself actually succeeded; a
# failed comparison is gated out below exactly like a missing ref — it just
# doesn't run (fail closed), it never grants an exemption.
_diffidx_dir="$(mktemp -d 2>/dev/null)" || _diffidx_dir=""
# Replaces the `_cleanup_staged_dir` trap set above (bash keeps only the LAST
# EXIT trap registered, it does not stack them), so this one also removes
# `_staged_dir` — otherwise everything from here to the end of the script
# would leak that scratch dir on exit.
_cleanup_diffidx_dir() {
  [ -n "${_staged_dir}" ] && rm -rf "${_staged_dir}"
  [ -n "${_diffidx_dir}" ] && rm -rf "${_diffidx_dir}"
}
trap _cleanup_diffidx_dir EXIT

_origin_route_ok=0
_changed_origin=()
if [ "${_have_origin_ref}" = "1" ] && [ -n "${_diffidx_dir}" ]; then
  _origin_out="${_diffidx_dir}/origin.nul"
  git --literal-pathspecs diff-index --cached -z --no-renames --name-only \
      "${_origin_ref}" -- "${_artifact_paths[@]}" >"${_origin_out}" 2>/dev/null
  if [ "$?" -eq 0 ]; then
    _origin_route_ok=1
    while IFS= read -r -d '' _c; do
      _changed_origin+=("${_c}")
    done < "${_origin_out}"
  fi
fi
_mh_route_ok=0
_changed_mergehead=()
if [ "${_merge_head_on_default}" = "1" ] && [ -n "${_diffidx_dir}" ]; then
  _mh_out="${_diffidx_dir}/mergehead.nul"
  git --literal-pathspecs diff-index --cached -z --no-renames --name-only \
      MERGE_HEAD -- "${_artifact_paths[@]}" >"${_mh_out}" 2>/dev/null
  if [ "$?" -eq 0 ]; then
    _mh_route_ok=1
    while IFS= read -r -d '' _c; do
      _changed_mergehead+=("${_c}")
    done < "${_mh_out}"
  fi
fi

# Per-route shortcut: the diff-index call above was restricted to exactly the
# N candidate paths, so its output can only ever be a subset of them.
#   0 results    -> NONE of the N candidates differ -> every one is exempt via
#                    this route, with no per-path scan.
#   N results     -> ALL N candidates differ -> none is exempt via this route,
#                    again with no per-path scan (pigeonhole: N results drawn
#                    from a restriction to N candidates can only BE those N).
#   in between    -> fall back to a per-path membership check, bounded by N.
# Both extremes are the shapes the stress tests hit (a merge bringing in
# thousands of already-on-main artifacts unchanged; thousands of brand-new
# ones), and bash 3.2's "${arr[@]}" on an EMPTY array is a fatal unbound-
# variable error under `set -u` — the membership function below is only ever
# called once a route's changed-list is known non-empty, so that trap never
# fires.
_origin_all_exempt=0; _origin_none_exempt=0
if [ "${_origin_route_ok}" = "1" ]; then
  _n="${#_changed_origin[@]}"
  if [ "${_n}" -eq 0 ]; then _origin_all_exempt=1
  elif [ "${_n}" -ge "${_n_artifacts}" ]; then _origin_none_exempt=1
  fi
fi
_mh_all_exempt=0; _mh_none_exempt=0
if [ "${_mh_route_ok}" = "1" ]; then
  _n="${#_changed_mergehead[@]}"
  if [ "${_n}" -eq 0 ]; then _mh_all_exempt=1
  elif [ "${_n}" -ge "${_n_artifacts}" ]; then _mh_none_exempt=1
  fi
fi

# in_list NEEDLE LIST... -- bash-3.2-safe membership (no associative arrays).
# Only ever called with a non-empty LIST (see the shortcuts above).
_in_list() {
  local _needle="$1"; shift
  local _x
  for _x in "$@"; do
    [ "${_x}" = "${_needle}" ] && return 0
  done
  return 1
}

_hit_count=0
_hit=""
_i=0
for _path in "${_artifact_paths[@]}"; do
  _matched_pat="${_artifact_pats[$_i]}"
  _i=$((_i+1))

  _exempt=0
  if [ "${_origin_route_ok}" = "1" ]; then
    if [ "${_origin_all_exempt}" = "1" ]; then
      _exempt=1
    elif [ "${_origin_none_exempt}" = "1" ]; then
      :
    else
      _in_list "${_path}" "${_changed_origin[@]}" || _exempt=1
    fi
  fi
  if [ "${_exempt}" = "0" ] && [ "${_mh_route_ok}" = "1" ]; then
    if [ "${_mh_all_exempt}" = "1" ]; then
      _exempt=1
    elif [ "${_mh_none_exempt}" = "1" ]; then
      :
    else
      _in_list "${_path}" "${_changed_mergehead[@]}" || _exempt=1
    fi
  fi
  [ "${_exempt}" = "1" ] && continue

  _hit_count=$((_hit_count+1))
  [ "${_hit_count}" -le 20 ] && _hit="${_hit}
    ${_path}  (matched: ${_matched_pat})"
done

[ "${_hit_count}" -eq 0 ] && exit 0
[ "${_hit_count}" -gt 20 ] && _hit="${_hit}
    ... and $((_hit_count - 20)) more"

# Per-route status for the message below, so it never asserts a cause it
# never checked. A route with no usable ref/MERGE_HEAD at all is "ref
# missing" / "not applicable" -- there was genuinely nothing to compare
# against, so "not exempt" is trivially true. A route whose ref/MERGE_HEAD
# DID exist but whose `diff-index` call itself FAILED (E2BIG, an unreadable
# object, an index lock -- this file's header's own motivating case) is
# "comparison FAILED": on that route the staged content may well be
# byte-identical to the ref, the guard just never got to find out, so
# claiming "this is not that [identical]" there would be a false cause. This
# does not weaken the refusal itself -- every state below still exits 1.
_origin_status="ref missing"
if [ "${_have_origin_ref}" = "1" ]; then
  if [ "${_origin_route_ok}" = "1" ]; then _origin_status="ran, no match"
  else _origin_status="comparison FAILED"
  fi
fi
_mh_status="not applicable"
if [ "${_merge_head_on_default}" = "1" ]; then
  if [ "${_mh_route_ok}" = "1" ]; then _mh_status="ran, no match"
  else _mh_status="comparison FAILED"
  fi
fi

{
  echo "pre-commit: REFUSED — checkout is on '${_cur}', not the default branch '${_def}'."
  echo "  You are staging session-close artifact(s) that must land on '${_def}', or they STRAND on"
  echo "  this topic branch (never reaching '${_def}'; local '${_def}' then diverges)."
  if [ "${_origin_status}" = "comparison FAILED" ] || [ "${_mh_status}" = "comparison FAILED" ]; then
    echo "  (origin/${_def} route: ${_origin_status}; MERGE_HEAD route: ${_mh_status}. A FAILED comparison refuses"
    echo "  without knowing whether the content is identical to either — this is NOT a checked 'not identical', it"
    echo "  is fail-closed on an unknown. Re-run once whatever failed it — a huge pathspec, an unreadable object, an"
    echo "  index lock — is resolved.)"
  else
    echo "  (origin/${_def} route: ${_origin_status}; MERGE_HEAD route: ${_mh_status}. Content identical to either"
    echo "  would be exempt; this is not that.)"
  fi
  echo "  Refused path(s):${_hit}"
  echo "  Fix:    git checkout ${_def}    (then re-run the session close)."
  echo "  Bypass: SESSION_ARTIFACT_BRANCH_BYPASS=1 git commit ...   (or git commit --no-verify)."
} >&2
exit 1
