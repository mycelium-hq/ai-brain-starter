#!/usr/bin/env bash
# Regression test for skills/meeting-todos/SKILL.md Step 0 — locate or
# create the to-do file BEFORE extracting action items.
#
# Bug: fresh-install vaults have no to-do file. The skill historically
# jumped to Step 5 with "Find the to-do file: look for a file named
# `✅ Get to-do.md` ..." and then errored with "file not found" when
# nothing matched. The meeting extraction work was already done — Claude
# just had no destination, and no guidance on what to do about it.
#
# This test asserts that Step 0 is present and documents the
# locate-or-create-with-confirmation flow. It is a doc-shape regression
# test (no shell behavior to exercise — SKILL.md is read by Claude),
# but documenting the required cues prevents future drift.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="$REPO_ROOT/skills/meeting-todos/SKILL.md"

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

[[ -f "$SKILL" ]] || fail "skill missing at $SKILL"

# 1. Step 0 header present.
grep -q "^## Step 0 — Locate (or create) the to-do file" "$SKILL" || \
    fail "Step 0 header missing — fresh-install vaults will still hit 'file not found'"

# 2. Common-paths-first guidance present (cheap before falling back to CLAUDE.md).
grep -qF "🏠 Home/✅ Get to-do.md" "$SKILL" || \
    fail "Step 0 should name the canonical to-do path '🏠 Home/✅ Get to-do.md'"

# 3. CLAUDE.md fallback path documented.
grep -qiF "vault \`CLAUDE.md\`" "$SKILL" || \
    fail "Step 0 should fall back to reading vault CLAUDE.md for a hint"

# 4. Ask-before-creating discipline.
grep -qiF "ASK the user before creating" "$SKILL" || \
    fail "Step 0 must ask before creating — silent file creation in user's vault is unwanted"

# 5. Canonical frontmatter structure named.
grep -qF "type: todo" "$SKILL" || \
    fail "Step 0 should document the canonical frontmatter (type: todo)"
grep -qF "## Inbox" "$SKILL" || \
    fail "Step 0 should document the canonical '## Inbox' section"

# 6. On-no branch: stop, don't silent-no-op.
grep -qiE "On no.*(stop|silent)" "$SKILL" || \
    fail "Step 0 should explicitly tell Claude to STOP on 'no' rather than continue and lose the extraction"

# 7. Step 1 still present and reachable after Step 0.
grep -q "^## Step 1 — Find the meeting note" "$SKILL" || \
    fail "Step 1 should remain unchanged after Step 0"

# 8. Step 5 references the resolved-in-Step-0 path (no re-search).
grep -qiE "use the to-do file path resolved.*Step 0|do NOT re-search" "$SKILL" || \
    fail "Step 5 should reuse the path from Step 0, not re-search the filesystem"

echo "PASS: meeting-todos SKILL.md Step 0 documents locate-or-create-with-confirmation flow; Step 5 reuses Step 0 result"
