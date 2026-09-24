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
# Fires at the git pre-commit CHOKEPOINT so it catches EVERY committer (a
# session-close cascade, an auto-append, a manual commit, an agent), not just one
# call site. Off-branch code work is unaffected — it only blocks when a
# session-close artifact is staged.
#
# CARVE-OUT: a staged artifact is exempt when its staged content is byte-identical,
# path for path, to what is already on the default branch's remote-tracking ref
# (refs/remotes/origin/<default>), or — while a merge is in progress — to what is
# on MERGE_HEAD. Content already on the default branch cannot be stranded by this
# commit, so a plain `git merge origin/main` into a feature branch (which stages
# main's own unchanged session artifacts) no longer needs the bypass. A NEW
# artifact, a merge whose resolution CHANGES an artifact, and a staged deletion
# (no staged blob to compare) are all still refused. A missing or unreadable ref
# never grants the exemption — it just doesn't run (fail closed).
#
# INSTALL: called by the pre-commit hook (pre-commit-template.sh chains it, or a
# repo-local .githooks/pre-commit invokes it). Vendor this file byte-for-byte into
# consuming repos that keep their own .githooks/.
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
_staged="$(git -c core.quotepath=false diff --cached --name-only 2>/dev/null || true)"
[ -z "${_staged}" ] && exit 0

# Generic session-close outputs. Substring match (grep -F) so a folder icon prefix
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

# Resolve the two exemption refs ONCE. Missing/unreadable => that route simply
# never grants the exemption below (fail closed), it does not error out.
_origin_ref="refs/remotes/origin/${_def}"
_have_origin_ref=0
git rev-parse --quiet --verify "${_origin_ref}" >/dev/null 2>&1 && _have_origin_ref=1

_have_merge_head=0
git rev-parse --quiet --verify MERGE_HEAD >/dev/null 2>&1 && _have_merge_head=1

_hit=""
while IFS= read -r _path; do
  [ -z "${_path}" ] && continue

  _matched_pat=""
  while IFS= read -r _pat; do
    [ -z "${_pat}" ] && continue
    case "${_pat}" in \#*) continue ;; esac
    if printf '%s\n' "${_path}" | grep -F -q -- "${_pat}"; then
      _matched_pat="${_pat}"
      break
    fi
  done <<EOF
${_patterns}
EOF
  [ -z "${_matched_pat}" ] && continue

  # Matched a session-artifact pattern. Exempt ONLY if the STAGED content at this
  # exact path already exists, byte-for-byte, on origin/<default> or MERGE_HEAD.
  # Never exempt on path/pattern alone, and never exempt a staged deletion (there
  # is no staged blob to compare, so it falls through as a hit).
  _exempt=0
  _sblob="$(git rev-parse --quiet --verify ":${_path}" 2>/dev/null || true)"
  if [ -n "${_sblob}" ]; then
    if [ "${_have_origin_ref}" = "1" ]; then
      _oblob="$(git rev-parse --quiet --verify "${_origin_ref}:${_path}" 2>/dev/null || true)"
      [ -n "${_oblob}" ] && [ "${_oblob}" = "${_sblob}" ] && _exempt=1
    fi
    if [ "${_exempt}" = "0" ] && [ "${_have_merge_head}" = "1" ]; then
      _mblob="$(git rev-parse --quiet --verify "MERGE_HEAD:${_path}" 2>/dev/null || true)"
      [ -n "${_mblob}" ] && [ "${_mblob}" = "${_sblob}" ] && _exempt=1
    fi
  fi
  [ "${_exempt}" = "1" ] && continue

  _hit="${_hit}
    ${_path}  (matched: ${_matched_pat})"
done <<EOF
${_staged}
EOF

[ -z "${_hit}" ] && exit 0

{
  echo "pre-commit: REFUSED — checkout is on '${_cur}', not the default branch '${_def}'."
  echo "  You are staging session-close artifact(s) that must land on '${_def}', or they STRAND on"
  echo "  this topic branch (never reaching '${_def}'; local '${_def}' then diverges)."
  echo "  (Content already identical to origin/${_def} or MERGE_HEAD is exempt — this is not that.)"
  echo "  Refused path(s):${_hit}"
  echo "  Fix:    git checkout ${_def}    (then re-run the session close)."
  echo "  Bypass: SESSION_ARTIFACT_BRANCH_BYPASS=1 git commit ...   (or git commit --no-verify)."
} >&2
exit 1
