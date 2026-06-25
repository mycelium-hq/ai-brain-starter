#!/usr/bin/env bash
# Regression test: every install-API call targets the CANONICAL host and
# shell callers follow redirects.
#
# Bug class (caught 2026-06-10, MYC-419; recurred mirror-image 2026-06-24,
# MYC-1659): alternate domains 308-redirect to the canonical host. curl does
# NOT follow redirects without -L, and Python 3.9/3.10's urllib does not
# follow 308 at all — so every install-API call against a non-canonical base
# dies silently (the reporters are deliberately fail-open). The funnel showed
# signups but consumed=0 / completed=0 for weeks while real installs ran: the
# mid-funnel zeros were measurement failure, not user drop-off.
#
# Canonical host = bare apex https://mycelium-ai.co (NO www). The 2026-06-22
# Vercel primary flip (MYC-1539) made the apex canonical; www.mycelium-ai.co
# AND the no-hyphen myceliumai.co now BOTH 308 to it. This test pins the apex
# so the next flip (either direction) fails loud instead of bleeding the funnel.
# Live probe for humans (not in CI — keeps the test offline-deterministic):
#   curl -s -o /dev/null -w '%{http_code}\n' -X OPTIONS https://mycelium-ai.co/api/install/quick-mint
#   expect 2xx (route live, no redirect); a 308 means the apex moved again.
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

CANON="https://mycelium-ai.co"
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

# 4. no non-canonical API calls in install-facing files. After the 2026-06-22
#    apex flip the non-canonical hosts are www.mycelium-ai.co (www 308s to apex)
#    and myceliumai.co (no hyphen, also 308s). The bare apex mycelium-ai.co is
#    canonical and must NOT match (the hyphen means "myceliumai.co" is not a
#    substring of it). -I skips binary files: a stray __pycache__/*.pyc (the URL
#    compiled into a bytecode string constant) is an untracked local artifact.
if matches=$(grep -rnEI '(www\.mycelium-ai\.co|myceliumai\.co)/api' \
    bootstrap.sh bootstrap.ps1 phases/ scripts/ hooks/ skills/ SECURITY.md 2>/dev/null); then
  fail "non-canonical install-API base found:"
  echo "$matches" | head -5 | sed 's|^|  |' >&2
fi

if [ "$FAILED" -gt 0 ]; then
  echo "test_install_api_canonical_base: $FAILED failure(s)" >&2
  exit 1
fi
echo "PASS: install-API calls all target $CANON and follow redirects"
