#!/usr/bin/env bash
# Regression test: every install-API call targets the CANONICAL host and
# shell callers follow redirects.
#
# Bug class (caught 2026-06-10, MYC-419): alternate domains 308-redirect to
# the canonical host. curl does NOT follow redirects without -L, and
# Python 3.9's urllib does not follow 308 at all — so every install-API
# call against a non-canonical base died silently (the reporters are
# deliberately fail-open). The funnel showed signups but consumed=0 /
# completed=0 for weeks while real installs ran: the mid-funnel zeros were
# measurement failure, not user drop-off.
#
# Asserts:
#   1. bootstrap.sh INSTALL_API_BASE default is the canonical host.
#   2. bootstrap.ps1 $installApiBase default is the canonical host.
#   3. Every bootstrap.sh curl against $INSTALL_API_BASE carries -L
#      (defense in depth for the NEXT domain change).
#   4. No install-facing file calls the API on a non-canonical base.
#
# Self-contained. Exit 0 = pass. Exit 1 = fail with details.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

CANON="https://www.mycelium-ai.co"
FAILED=0

fail() { echo "FAIL: $1" >&2; FAILED=$((FAILED + 1)); }

# 1. bootstrap.sh default base
grep -qF "INSTALL_API_BASE=\"\${MYCELIUM_INSTALL_API:-$CANON}\"" bootstrap.sh \
  || fail "bootstrap.sh INSTALL_API_BASE default is not $CANON"

# 2. bootstrap.ps1 default base
grep -qF "else { \"$CANON\" }" bootstrap.ps1 \
  || fail "bootstrap.ps1 installApiBase default is not $CANON"

# 3. every INSTALL_API_BASE curl in bootstrap.sh follows redirects
while IFS= read -r line; do
  if ! echo "$line" | grep -qE 'curl[^|]*-[a-zA-Z]*L'; then
    fail "bootstrap.sh curl without -L: $line"
  fi
done < <(grep -E 'curl .*\$INSTALL_API_BASE/api' bootstrap.sh)

# 4. no non-canonical API calls in install-facing files
#    (myceliumai.co — no hyphen — 308s; so does bare mycelium-ai.co without www)
#    -I skips binary files: a stray __pycache__/*.pyc (the URL compiled into a
#    bytecode string constant) is an untracked local artifact, not source to audit.
if matches=$(grep -rnEI '(myceliumai\.co|[^.w]mycelium-ai\.co)/api' \
    bootstrap.sh bootstrap.ps1 phases/ scripts/ hooks/ skills/ SECURITY.md 2>/dev/null); then
  fail "non-canonical install-API base found:"
  echo "$matches" | head -5 | sed 's|^|  |' >&2
fi

if [ "$FAILED" -gt 0 ]; then
  echo "test_install_api_canonical_base: $FAILED failure(s)" >&2
  exit 1
fi
echo "PASS: install-API calls all target $CANON and follow redirects"
