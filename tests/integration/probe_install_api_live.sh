#!/usr/bin/env bash
# LIVE probe: the install-API host the installer actually targets must serve a
# 2xx, NOT a redirect.
#
# Why this exists (and why the offline test is not enough): its sibling
# test_install_api_canonical_base.sh pins a hardcoded canonical STRING and checks
# the code matches it. That cannot catch a FUTURE Vercel primary flip where the
# canonical host ITSELF starts 308-redirecting — the offline test stays green
# because the string still equals itself, while the urllib POST callers (which do
# not reliably follow 308 on Python 3.9/3.10, and are fail-open) silently drop
# install emails/pings. That bug shipped twice: MYC-419, then MYC-1659 mirror-imaged.
#
# Runs on a SCHEDULE, never as a merge gate: a redirect fails the scheduled run
# and GitHub emails the failure (the MYC-770 alert channel). A transient network
# error does NOT fail — only a definitive 3xx does — so it never false-alarms.
#
# Exit 0 = OK (2xx) or transient network error. Exit 1 = host redirects (the
# canonical moved; repoint the client per MYC-1659 or fix the Vercel primary).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Single source of truth: read the SAME default the installer uses, so this probe
# can never drift from what bootstrap.sh actually targets. INSTALL_API_PROBE_BASE_OVERRIDE
# is a test seam for the negative control (point it at a known-308 host to prove
# the probe fails on the thing it catches).
if [ -n "${INSTALL_API_PROBE_BASE_OVERRIDE:-}" ]; then
  BASE="$INSTALL_API_PROBE_BASE_OVERRIDE"
else
  BASE="$(grep -oE 'MYCELIUM_INSTALL_API:-https?://[^}"]+' "$REPO_ROOT/bootstrap.sh" | head -1 | sed 's/^MYCELIUM_INSTALL_API:-//')"
fi

if [ -z "${BASE:-}" ]; then
  echo "FAIL: could not read INSTALL_API_BASE default from bootstrap.sh" >&2
  exit 1
fi
echo "Probing canonical install-API base: $BASE"

FAILED=0
probe() {
  local path="$1"
  local code
  code="$(curl -sS -m 12 --retry 2 --retry-delay 2 -o /dev/null -w '%{http_code}' -X OPTIONS "$BASE$path" 2>/dev/null || echo 000)"
  case "$code" in
    2*) echo "  OK   $code  $path" ;;
    3*) echo "  FAIL $code  $path  <-- REDIRECT: canonical host moved; urllib POST callers silently drop here" >&2; FAILED=1 ;;
    000) echo "  WARN  --   $path  (network error reaching host; not failing — transient)" ;;
    *)  echo "  WARN $code  $path  (unexpected; not a redirect; not failing)" ;;
  esac
}

# The endpoints the fail-open urllib callers POST to (the silent-death surface).
probe "/api/install/quick-mint"
probe "/api/install"
probe "/api/install/first-journal"

if [ "$FAILED" -ne 0 ]; then
  echo "install-api live probe: canonical host is REDIRECTING. Repoint the client (MYC-1659) or fix the Vercel primary flip (MYC-1539)." >&2
  exit 1
fi
echo "install-api live probe: PASS ($BASE serves 2xx, no redirect)"
