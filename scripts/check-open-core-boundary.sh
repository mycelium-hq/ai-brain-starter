#!/usr/bin/env bash
#
# check-open-core-boundary.sh - fail-loud guard for ADR-0001 (open-core boundary).
#
# The public ai-brain-starter substrate teaches the PATTERN. It must never ship
# paid-runtime content: per-vertical workflow packs, multi-tenant connector specs,
# or legal-grade audit-analytics templates. Those belong to the private runtime.
#
# This guard FAILS if any such content reappears - by name OR by the structural
# shape it always takes (a connectors/ or decision-audit/ subtree under a skill).
# Structure over names: a future "vertical-realestate" carrying a connectors/ dir
# is caught even though its name is on no list.
#
# Verified safe at introduction (2026-06-18): no in-scope skill uses a connectors/
# or decision-audit/ subtree, so the structural patterns below cannot false-positive
# on substrate content.
#
# Source of truth: docs/adr/0001-open-core-boundary.md
# Runs in: .github/workflows/open-core-boundary.yml (CI) and locally pre-push.
#
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

violations="$(git ls-files \
  | grep -E \
      -e '^skills/vertical-[^/]+/' \
      -e '^skills/influencer-pack/' \
      -e '^skills/[^/]+/connectors/' \
      -e '^skills/[^/]+/decision-audit/' \
  || true)"

if [ -n "${violations}" ]; then
  {
    echo "OPEN-CORE BOUNDARY VIOLATION (ADR-0001)."
    echo
    echo "The public substrate must not ship per-vertical packs, multi-tenant"
    echo "connectors, or audit-analytics content. These tracked paths cross the"
    echo "boundary and belong in the private paid runtime instead:"
    echo
    while IFS= read -r path; do echo "  - ${path}"; done <<< "${violations}"
    echo
    echo "If this is intentional, it requires an explicit ADR-0001 re-eval, not a"
    echo "silent merge. See docs/adr/0001-open-core-boundary.md."
  } >&2
  exit 1
fi

echo "open-core boundary OK: no paid-runtime content in the public substrate."
