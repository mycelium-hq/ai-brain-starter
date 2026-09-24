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
# NUL-separated, rename detection OFF, explicit HEAD as the compare-from tree:
# git never quotes/escapes a path in -z output, so a name holding a double
# quote, a backslash, a tab or an embedded newline round-trips as its real
# bytes instead of a display string that names a DIFFERENT path (or nothing).
# --no-renames means a rename is one deletion plus one addition, each checked
# on its own path — never paired and skipped as a pair.
_staged_paths=()
while IFS= read -r -d '' _p; do
  _staged_paths+=("${_p}")
done < <(git diff --cached --name-only -z --no-renames HEAD 2>/dev/null)
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
_changed_origin=()
if [ "${_have_origin_ref}" = "1" ]; then
  while IFS= read -r -d '' _c; do
    _changed_origin+=("${_c}")
  done < <(git --literal-pathspecs diff-index --cached -z --no-renames --name-only \
             "${_origin_ref}" -- "${_artifact_paths[@]}" 2>/dev/null)
fi
_changed_mergehead=()
if [ "${_merge_head_on_default}" = "1" ]; then
  while IFS= read -r -d '' _c; do
    _changed_mergehead+=("${_c}")
  done < <(git --literal-pathspecs diff-index --cached -z --no-renames --name-only \
             MERGE_HEAD -- "${_artifact_paths[@]}" 2>/dev/null)
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
if [ "${_have_origin_ref}" = "1" ]; then
  _n="${#_changed_origin[@]}"
  if [ "${_n}" -eq 0 ]; then _origin_all_exempt=1
  elif [ "${_n}" -ge "${_n_artifacts}" ]; then _origin_none_exempt=1
  fi
fi
_mh_all_exempt=0; _mh_none_exempt=0
if [ "${_merge_head_on_default}" = "1" ]; then
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
  if [ "${_have_origin_ref}" = "1" ]; then
    if [ "${_origin_all_exempt}" = "1" ]; then
      _exempt=1
    elif [ "${_origin_none_exempt}" = "1" ]; then
      :
    else
      _in_list "${_path}" "${_changed_origin[@]}" || _exempt=1
    fi
  fi
  if [ "${_exempt}" = "0" ] && [ "${_merge_head_on_default}" = "1" ]; then
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

{
  echo "pre-commit: REFUSED — checkout is on '${_cur}', not the default branch '${_def}'."
  echo "  You are staging session-close artifact(s) that must land on '${_def}', or they STRAND on"
  echo "  this topic branch (never reaching '${_def}'; local '${_def}' then diverges)."
  echo "  (Content identical to origin/${_def}, or to a merged commit already on '${_def}', is exempt; this is not that.)"
  echo "  Refused path(s):${_hit}"
  echo "  Fix:    git checkout ${_def}    (then re-run the session close)."
  echo "  Bypass: SESSION_ARTIFACT_BRANCH_BYPASS=1 git commit ...   (or git commit --no-verify)."
} >&2
exit 1
