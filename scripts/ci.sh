#!/usr/bin/env bash
#
# scripts/ci.sh - the canonical, locally-runnable unit/type gate for
# ai-brain-starter. ONE command, shared by two callers so they can never drift:
#
#   1. .github/workflows/lint.yml  - the `ci` job runs `bash scripts/ci.sh`.
#   2. ~/.local/bin/ci-test        - resolves this repo to mode=canon and runs
#                                    the same `bash scripts/ci.sh` pre-push.
#
# It runs EXACTLY the unit/type gate that lint.yml used to run as separate jobs:
#   (a) Python syntax     - py_compile every tracked *.py. Catches the PEP 604
#                           `X | None` annotation class that crashes Python 3.9
#                           at module load (many users invoke hooks via macOS's
#                           system /usr/bin/python3, which is 3.9).
#   (b) Shell integration - the named tests under tests/integration/, in
#                           order, stopping at the first failure.
#
# It does NOT run the pure-lint jobs (bash -n, pwsh ParseFile, BOM, em-dash,
# JSON, privacy, references, no-remote-pipe-install). Those stay as their own
# lint.yml jobs - they are lint, not the unit/type gate.
#
# Environment the integration tests need (lint.yml provides these in the `ci`
# job; this script adds a non-invasive fallback so a fresh `bash scripts/ci.sh`
# works for a contributor too):
#   - A git identity. The tests create temp repos and commit; they set their own
#     LOCAL identity, but a fresh box may have no ambient identity at all, so we
#     export GIT_* defaults only when nothing is configured.
#   - ruff on PATH is OPTIONAL: test_session_coordination_guards exercises the
#     F821 block path when ruff is present and fails OPEN (still green) when not.
#   - Python 3.9 for the py_compile check is IDEAL (it is the version whose crash
#     class this gate exists to catch). We prefer `python3.9` when present and
#     fall back to `python3` otherwise. lint.yml pins 3.9 via setup-python, so
#     CI is always authoritative for the 3.9 check; the local fallback to a newer
#     interpreter is a weaker superset check (it will not catch 3.9-only crashes).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Keep generated .pyc out of the working tree. This script runs IN the checkout
# (ci-test runs it inside the live worktree), so route every child interpreter's
# bytecode cache to a temp dir instead of littering __pycache__/ across the repo.
PYCACHE_TMP="$(mktemp -d)"
export PYTHONPYCACHEPREFIX="$PYCACHE_TMP"
cleanup() { rm -rf "$PYCACHE_TMP"; }
trap cleanup EXIT

# Non-invasive git identity fallback - only when nothing is configured. Uses env
# vars (not `git config --global`) so we never mutate the caller's global config.
if [ -z "$(git config user.email 2>/dev/null || true)" ]; then
  export GIT_AUTHOR_NAME="ci" GIT_AUTHOR_EMAIL="ci@example.com"
  export GIT_COMMITTER_NAME="ci" GIT_COMMITTER_EMAIL="ci@example.com"
fi

# ---- (a) Python syntax gate ------------------------------------------------
if command -v python3.9 >/dev/null 2>&1; then
  PY=python3.9
else
  PY=python3
fi
echo "==> (a) Python syntax: py_compile every tracked *.py  [$("$PY" --version 2>&1)]"
err="$(mktemp)"
fail=0
count=0
while IFS= read -r -d '' f; do
  count=$((count + 1))
  if ! "$PY" -m py_compile "$f" 2>"$err"; then
    echo "::error file=$f::python3 -m py_compile failed"
    sed 's|^|  |' "$err"
    fail=1
  fi
done < <(git ls-files -z -- '*.py')
rm -f "$err"
if [ "$fail" != 0 ]; then
  echo "FAILED: Python syntax gate (see errors above)"
  exit 1
fi
echo "    OK - $count file(s) compiled clean"

# ---- (b) Shell integration gate --------------------------------------------
# The named tests that constitute lint.yml's integration gate, in order.
# `set -e` aborts on the first non-zero test, which is the required
# stop-on-first-failure behavior. This list is the gate's source of truth:
# tests/integration/ also holds .sh/.py files that are NOT part of this gate, so
# it must be an explicit allow-list, never a glob over the directory.
INTEGRATION_TESTS=(
  test_worktree_session_close
  test_bootstrap_dry_run
  test_phase_doc_slash_commands_installed
  test_reconcile_ff_invariant
  test_detect_closing_signal_worktree
  test_stranded_session_artifacts_watchdog
  test_session_coordination_guards
  test_trust_prompt_preframing
  test_post_update_email_ask
  test_installer_retires_email_gate
  test_remediate_runaway_procs
  test_scan_prior_single_instance
)
echo "==> (b) Shell integration: ${#INTEGRATION_TESTS[@]} tests"
for t in "${INTEGRATION_TESTS[@]}"; do
  script="tests/integration/$t.sh"
  if [ ! -f "$script" ]; then
    echo "::error::missing integration test $script"
    exit 1
  fi
  echo "--- $t"
  bash "$script"
done

echo
echo "All gates passed: py_compile ($count file(s)) + ${#INTEGRATION_TESTS[@]} integration tests."
