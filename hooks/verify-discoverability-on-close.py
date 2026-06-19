#!/usr/bin/env python3
"""Stop hook: blocks session close if any artifact committed in this session
lacks a same-session discoverability companion.

Per the same-session discoverability-enforcement rule
(codified 2026-05-13 after the gbrain-build wiring gap).

Bug class blocked: ARTIFACT-WITHOUT-DISCOVERABILITY.

Mechanism:
1. Detect closing-claim in the model's last assistant message (reuse the same
   patterns as verify-session-close-cascade.py).
2. If closing claim detected, run discoverability-verifier.py --strict on
   the last 24h of commits.
3. If verifier reports gaps AND no Handoff file acknowledges them, BLOCK
   the close with the gap list + remediation suggestions.

Bypass: DISCOVERABILITY_VERIFIER_BYPASS=1.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Shared close-claim detector - single source of truth (_lib/closing_claim.py).
# MENTION-vs-USE aware. Replaces this hook's previously-duplicated (and drifted)
# CLOSING_PATTERNS / NEGATION_PATTERNS / _is_closing_claim. MYC-791.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _lib.closing_claim import is_closing_claim  # noqa: E402
except Exception:  # fail-open: if the lib cannot load, never block a close
    def is_closing_claim(_text: str) -> bool:  # type: ignore
        return False

VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", str(Path.home() / "vault")))
VERIFIER = VAULT_ROOT / "⚙️ Meta" / "scripts" / "discoverability-verifier.py"

# Closing-claim detection now lives in the shared _lib/closing_claim.py
# imported above (de-drifted from verify-session-close-cascade.py, with
# MENTION-vs-USE guards). MYC-791.


def _get_last_assistant_text(transcript_path: str) -> str:
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", [])
        text_parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                text_parts.append(c.get("text", ""))
        if text_parts:
            return "\n".join(text_parts)
    return ""


def _run_verifier() -> tuple[bool, str]:
    """Returns (clean, output_text)."""
    if not VERIFIER.exists():
        return (True, "")
    try:
        result = subprocess.run(
            ["python3", str(VERIFIER), "--hours", "24", "--json"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:
        # Verifier failed to run — don't block on tooling failure
        return (True, f"discoverability-verifier could not run: {exc}")

    try:
        payload = json.loads(result.stdout)
    except Exception:
        # Malformed output — don't block
        return (True, "discoverability-verifier returned malformed JSON")

    gaps = payload.get("gaps", [])
    if not gaps:
        return (True, "")

    lines = [
        f"  • {len(gaps)} artifact(s) without discoverability wiring:",
    ]
    for gap in gaps[:8]:
        artifact = gap["artifact"]
        lines.append(
            f"      - {artifact['repo']} :: {artifact['path']}"
        )
        lines.append(f"          kind: {artifact['kind']}")
        lines.append(f"          fix: {gap['suggestion']}")
    if len(gaps) > 8:
        lines.append(f"      ... and {len(gaps) - 8} more")
    return (False, "\n".join(lines))


def main() -> int:
    if os.environ.get("DISCOVERABILITY_VERIFIER_BYPASS") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    transcript_path = payload.get("transcript_path", "")
    last_text = _get_last_assistant_text(transcript_path)
    if not is_closing_claim(last_text):
        return 0

    clean, gap_report = _run_verifier()
    if clean:
        return 0

    msg = (
        f"BLOCKED by verify-discoverability-on-close hook.\n\n"
        f"Per the same-session discoverability-enforcement rule\n"
        f"(codified 2026-05-13): every artifact ships discoverability wiring\n"
        f"in the same session as the artifact itself.\n\n"
        f"Bug class: ARTIFACT-WITHOUT-DISCOVERABILITY.\n\n"
        f"{gap_report}\n\n"
        f"Two ways to clear this block:\n"
        f"  (a) Wire the discoverability for each artifact NOW (preferred).\n"
        f"      For SKILL.md: ln -sfn <skill-dir> ~/.claude/skills/<name>\n"
        f"      For rules:    write .claude/hookify.<rule-name>.local.md\n"
        f"      For scripts:  add to sunday-review SKILL.md OR a hook OR cron\n"
        f"      For workflows: add 'on:' trigger block\n\n"
        f"  (b) File a handoff at ⚙️ Meta/Handoffs/<date>-<slug>.md mentioning\n"
        f"      the artifact name + the word 'discoverability' + a re-evaluate\n"
        f"      date. The verifier treats explicit handoff acknowledgment as\n"
        f"      a valid dismissal.\n\n"
        f"Bypass for one close (use sparingly): DISCOVERABILITY_VERIFIER_BYPASS=1\n"
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
