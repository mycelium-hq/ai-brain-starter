#!/usr/bin/env bash
# tests/integration/test_template_purity.sh
#
# Verifies the public-template-purity guard (MYC-1765 — Jackie's 2nd isolation
# plane). The guard is the STRUCTURAL complement to personal-pii-scrub.yml: that
# workflow catches personal NAME tokens + vault paths; this one catches POPULATED
# typed-category content (a real floor entry, a real deal/counterparty/amount, a
# real entity_id) that carries NO name and so slips the name-scrub entirely.
#
# Three surfaces, one shared detection module (hooks/_lib/template_purity.py):
#   1. scripts/check-template-purity.py  — CLI / CI / pre-push gate
#   2. hooks/block-populated-public-skill.py — PreToolUse(Write|Edit) write-time guard
#   3. the module self-test                — unit coverage for each detector
#
# Negative-control requirement (the guard earns trust only by failing on the
# exact harm it prevents): a POPULATED example is blocked + named; an EMPTY
# TEMPLATE passes. Structural detection only — no personal-name list lives here.
#
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

CLI="scripts/check-template-purity.py"
LIB="hooks/_lib/template_purity.py"
HOOK="hooks/block-populated-public-skill.py"
PASS=0
FAIL=0
_ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
_fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "==> test_template_purity"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# A POPULATED skill example — real typed-category data, NO personal name token
# (proves the structural layer catches what the name-scrub cannot). Fully
# synthetic ("Northwind" is a classic sample-DB name) so the fixture itself
# carries no real private data.
POPULATED="$TMP/populated-example.md"
cat > "$POPULATED" <<'EOF'
---
type: deal
counterparty: Northwind Logistics LLC
amount: $36,000
stage: signed
entity_id: tnt_a1b2c3d4
---

# Pilot close

floor: Courage
floor_level: High

Closed the pilot today. Valuation discussion landed at $1,200,000.
EOF

# An EMPTY TEMPLATE — same schema, every value a placeholder. Must pass.
EMPTY="$TMP/empty-template.md"
cat > "$EMPTY" <<'EOF'
---
type: deal
counterparty: <counterparty-name>
amount: $<amount>
stage: <stage>
entity_id: <tid>
---

# <title>

floor: <floor-name>
floor_level: <Low|Middle|High>

<your reflection here>
EOF

# ── Test 1: NEGATIVE — populated example blocks + names the file ──────────────
out="$(python3 "$CLI" "$POPULATED" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -ne 0 ] && echo "$out" | grep -q "populated-example.md"; then
  _ok "populated example → guard exits non-zero AND names the offending file"
else
  _fail "populated example → expected non-zero exit naming the file (rc=$rc)"
fi

# ── Test 2: POSITIVE — empty template passes ─────────────────────────────────
if python3 "$CLI" "$EMPTY" >/dev/null 2>&1; then
  _ok "empty template → guard exits 0"
else
  _fail "empty template → guard exited non-zero (false positive on a pure template)"
fi

# ── Test 3: module self-test (per-detector unit coverage) ────────────────────
if python3 "$LIB" --selftest >/dev/null 2>&1; then
  _ok "template_purity.py --selftest → exit 0"
else
  _fail "template_purity.py --selftest → non-zero (a structural detector regressed)"
fi

# ── Test 4: write-time hook DENIES introducing populated data ────────────────
deny_in="$(printf '{"tool_input":{"file_path":"%s/ai-brain-starter/skills/vertical-finance/EXAMPLE.md","content":%s}}' \
  "$TMP" "$(python3 -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' "$POPULATED")")"
hook_out="$(printf '%s' "$deny_in" | python3 "$HOOK" 2>/dev/null || true)"
if echo "$hook_out" | grep -q '"permissionDecision": *"deny"'; then
  _ok "write-time hook → DENY on populated content into a public skill path"
else
  _fail "write-time hook → expected deny (got: $hook_out)"
fi

# ── Test 5: write-time hook ALLOWS an empty template ─────────────────────────
allow_in="$(printf '{"tool_input":{"file_path":"%s/ai-brain-starter/skills/vertical-finance/EXAMPLE.md","content":%s}}' \
  "$TMP" "$(python3 -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' "$EMPTY")")"
hook_out2="$(printf '%s' "$allow_in" | python3 "$HOOK" 2>/dev/null || true)"
if echo "$hook_out2" | grep -q '"permissionDecision": *"allow"'; then
  _ok "write-time hook → ALLOW on a pure template"
else
  _fail "write-time hook → expected allow (got: $hook_out2)"
fi

# ── Test 6: the real public skills/ tree passes the guard (no self-DoS) ───────
# The committed public substrate must already be template-pure. If this fails,
# the named files are REAL pre-existing leaks to fix — not a guard bug.
if python3 "$CLI" --skills >/dev/null 2>&1; then
  _ok "public skills/ tree → guard exits 0 (substrate is template-pure)"
else
  _fail "public skills/ tree → guard flagged committed files (see: python3 $CLI --skills)"
fi

echo
echo "  template_purity: ${PASS} passed, ${FAIL} failed"
if [ "${FAIL}" -gt 0 ]; then
  exit 1
fi
