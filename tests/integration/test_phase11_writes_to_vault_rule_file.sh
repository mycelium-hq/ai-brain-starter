#!/usr/bin/env bash
# Regression test for phases/phase-11-external-tools.md — Phase 11 must
# write the tool-customized meeting-workflow rule to the VAULT's rule
# file (<vault>/⚙️ Meta/rules/meeting-workflow.md), not just to CLAUDE.md.
#
# Bug: Phase 4 copied a generic Granola-default `meeting-workflow.md`
# template into `<vault>/⚙️ Meta/rules/`. Phase 11 then interviewed the
# user about their actual meeting tool (Otter / Gemini / Fireflies /
# Zoom / Teams / Notion AI / manual / etc.) and generated a customized
# rule — but appended it to CLAUDE.md instead of overwriting the vault
# rule file. The `inject-meeting-workflow-on-trigger.py` hook reads
# from the vault rule file. Result: the hook kept injecting the
# generic Granola template even though Phase 11 had already generated
# a customized version.
#
# This test asserts:
#   1. Phase 11 names the vault rule file path explicitly.
#   2. Phase 11 names "overwriting" (or equivalent) so the model
#      doesn't append-without-replacing.
#   3. Phase 11 explains WHY (the inject hook reads from this file).
#   4. Phase 11 explicitly warns against duplicating the rule body
#      into CLAUDE.md (the prior bug-source).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PHASE="$REPO_ROOT/phases/phase-11-external-tools.md"

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

[[ -f "$PHASE" ]] || fail "phase-11 missing at $PHASE"

# 1. Vault rule file path named.
grep -qF "<vault>/⚙️ Meta/rules/meeting-workflow.md" "$PHASE" || \
    fail "Phase 11 must name the vault rule file path explicitly so the model writes to the right place"

# 2. Overwrite intent named.
grep -qiE "overwrit(e|ing)|replac(e|ing)" "$PHASE" || \
    fail "Phase 11 must say 'overwriting' or 'replacing' so Phase 4's generic copy gets replaced, not coexisting"

# 3. WHY explained — the inject hook reads from this file.
grep -qF "inject-meeting-workflow-on-trigger.py" "$PHASE" || \
    fail "Phase 11 must explain WHY the vault rule file matters (the inject hook reads from it)"

# 4. Anti-duplication warning.
grep -qiE "do NOT duplicate|not duplicate the rule body|two near-identical bodies|drift" "$PHASE" || \
    fail "Phase 11 must warn against duplicating the rule body into CLAUDE.md (the source of the original bug)"

echo "PASS: phase-11-external-tools.md instructs Phase 11 to write customized rule to vault file (not duplicate into CLAUDE.md)"
