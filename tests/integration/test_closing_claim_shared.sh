#!/usr/bin/env bash
# test_closing_claim_shared.sh — negative + positive controls for the shared
# close-claim detector (hooks/_lib/closing_claim.py), the single source of
# truth used by BOTH Stop-side verify hooks. MYC-791.
#
# Headline negative control = the EXACT case that tore down a worktree on
# 2026-06-19: an assistant report that QUOTES sign-offs as examples and
# DISCUSSES the close detector must NOT be read as a close claim. Positive
# controls prove genuine first-person closes still fire (no over-suppression,
# which would re-open the gallant-kalam incomplete-close gap).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 - "$REPO" <<'PY'
import sys
from pathlib import Path
repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "hooks"))
from _lib.closing_claim import is_closing_claim

cases = [
    # ---- NEGATIVE: mention / discussion, NOT a claim ----
    ("report quoting sign-offs + discussing the detector (2026-06-19 incident)",
     'These no longer auto-close: "good night", "buenas noches", "thanks". '
     'The close-signal detector false-fires on quoted text.', False),
    ("sign-offs only inside double-quotes, NO discussion marker (pure stripping)",
     'The two example phrases are "good night" and "buenas noches".', False),
    ("blockquoted draft containing a sign-off (MYC-791 original case)",
     "Gratitude draft for your approval:\n> Gracias por todo. Buenas noches\nReady?", False),
    ("code-fenced sign-off",
     "Example pattern target:\n```\nbuenas noches\n```\nThat is the regex.", False),
    ("inline-code sign-off", "The phrase `closing the session` is the trigger.", False),
    ("definitional statement", "'good night' is not a close signal for me.", False),
    ("meta discussion of the detector", "the detector keeps firing; the fix is a guard.", False),
    # ---- POSITIVE: genuine first-person close claims (must still fire) ----
    ("genuine close", "Closing the session now and writing the artifact.", True),
    ("genuine spanish sign-off, unquoted", "Listo. Buenas noches a todos.", True),
    ("genuine final-summary header", "## Session 2026-06-19 — final summary", True),
    ("genuine good night, unquoted", "All shipped. Good night!", True),
    ("genuine running the cascade", "Running the cascade now.", True),
]
fails = 0
for label, text, expected in cases:
    got = is_closing_claim(text)
    if got != expected:
        fails += 1
        print(f"FAIL [{label}] expected={expected} got={got}")
    else:
        print(f"PASS [{label}] -> {got}")
if fails:
    print(f"\n{fails} failure(s).")
    sys.exit(1)
print("\nAll closing-claim mention-vs-use assertions passed.")
PY
echo "PASS: shared closing-claim detector (mention-vs-use) holds"
