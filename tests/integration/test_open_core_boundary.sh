#!/usr/bin/env bash
# tests/integration/test_open_core_boundary.sh
#
# Verifies the open-core boundary guard (scripts/check-open-core-boundary.sh):
#   POSITIVE: current tree (clean, restored) → EXIT 0
#   NEGATIVE: synthetic premium path added   → EXIT 1
#   FAIL-CLOSED: allowlist file removed      → EXIT 1
#
# Part of MYC-1339 negative-control requirement. The guard earns trust only by
# failing on the exact harm it prevents.
#
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

GUARD="scripts/check-open-core-boundary.sh"
ALLOWLIST=".github/free-tier-allowlist.txt"
PASS=0
FAIL=0

_ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
_fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "==> test_open_core_boundary"

# ── Test 1: POSITIVE — clean tree must exit 0 ────────────────────────────────
if bash "${GUARD}" >/dev/null 2>&1; then
  _ok "clean tree → guard exits 0"
else
  _fail "clean tree → guard exited non-zero (unexpected FAIL on good tree)"
fi

# ── Test 2: NEGATIVE — unallowlisted skills/ entry must exit non-zero ─────────
PROBE_DIR="skills/__premium_probe__"
mkdir -p "${PROBE_DIR}"
echo "type: skill" > "${PROBE_DIR}/SKILL.md"
git add "${PROBE_DIR}/SKILL.md"

if bash "${GUARD}" >/dev/null 2>&1; then
  _fail "premium probe '${PROBE_DIR}' → guard exited 0 (should have FAILED)"
else
  _ok "premium probe '${PROBE_DIR}' → guard exits non-zero (correct FAIL)"
fi

git rm -f "${PROBE_DIR}/SKILL.md" >/dev/null 2>&1 || true
rm -rf "${PROBE_DIR}" 2>/dev/null || true

# ── Test 3: FAIL-CLOSED — missing allowlist must exit non-zero ───────────────
mv "${ALLOWLIST}" "${ALLOWLIST}.bak"
if bash "${GUARD}" >/dev/null 2>&1; then
  _fail "missing allowlist → guard exited 0 (should have FAILED closed)"
else
  _ok "missing allowlist → guard exits non-zero (fail-closed correct)"
fi
mv "${ALLOWLIST}.bak" "${ALLOWLIST}"

# ── Test 4: FAIL-CLOSED — empty allowlist must exit non-zero ─────────────────
EMPTY_TMP="$(mktemp)"
cp "${ALLOWLIST}" "${ALLOWLIST}.bak"
echo "# only comments" > "${ALLOWLIST}"
if bash "${GUARD}" >/dev/null 2>&1; then
  _fail "empty allowlist → guard exited 0 (should have FAILED closed)"
else
  _ok "empty allowlist → guard exits non-zero (fail-closed correct)"
fi
mv "${ALLOWLIST}.bak" "${ALLOWLIST}"
rm -f "${EMPTY_TMP}"

# ── Summary ──────────────────────────────────────────────────────────────────
echo
echo "  open_core_boundary: ${PASS} passed, ${FAIL} failed"
if [ "${FAIL}" -gt 0 ]; then
  exit 1
fi
