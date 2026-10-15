#!/usr/bin/env python3
"""Block writing a LIVE credential into a note — PreToolUse(Write/Edit/MultiEdit).

Redaction exists at INGEST (the runtime scrubs secrets before they enter the
index) and at SESSION-END (jsonl scrub). But nothing stopped a live AWS key or
GitHub PAT from being WRITTEN into a note in the first place — which is exactly
how plaintext credentials ended up tracked in `⚙️ Meta/Sessions/` + `Handoffs/`.
This is the WRITE-TIME guard: it denies a Write/Edit that would put a
high-confidence live credential into a markdown/text note, and points you at the
keychain / a gitignored secrets file instead.

Only HIGH-CONFIDENCE provider credentials + connection-string passwords block
(AWS / GitHub / Anthropic / OpenAI / Stripe-secret / Slack / Heroku / HubSpot /
Google / Resend / Neon / db-URL passwords). The lower-precision heuristics (bare
JWT, 64-hex, Bearer header, publishable keys) do NOT block a write — they would
false-trip on legitimate notes; the ingest + session-scrub layers still cover
them.

Scope: note files only (`.md`, `.markdown`, `.mdx`, `.txt`). Code files are out
of scope (test fixtures / `.env.example` have legitimate credential shapes and
other layers cover them).

It only blocks a secret being INTRODUCED: for an Edit it scans the new text, so
removing/scrubbing a secret is never blocked.

Bypass: SECRET_VAULT_WRITE_BYPASS=1  (self-referential docs: this rule, the hook
itself, CLAUDE.md quoting the patterns, a note documenting AWS's example key).

WIRING (PreToolUse, matcher "Write|Edit|MultiEdit"):
  {"type": "command",
   "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/block-secret-in-note.py 2>/dev/null || echo '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"allow\"}}'"}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

try:
    from _lib.secret_patterns import PATTERNS
except Exception:
    PATTERNS = ()

# High-confidence provider creds + connection-string passwords that never have a
# legitimate reason to sit in a note. Names mirror _lib/secret_patterns.py.
BLOCK_NAMES = {
    "anthropic-api-key", "openai-api-key", "hubspot-private-app-token",
    "github-pat-fine-grained", "github-pat-classic", "heroku-api-key",
    "slack-token", "stripe-secret-key", "aws-access-key-id", "google-api-key",
    "resend-api-key", "neon-password", "postgres-url-password",
    "redis-url-password", "mongo-url-password",
}
NOTE_EXTS = {".md", ".markdown", ".mdx", ".txt"}


def _allow() -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow"}}))
    return 0


def _deny(reason: str) -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    return 0


def main() -> int:
    if os.environ.get("SECRET_VAULT_WRITE_BYPASS") == "1":
        return _allow()
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return _allow()

    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("path") or ""
    if Path(fp).suffix.lower() not in NOTE_EXTS:
        return _allow()

    # The text being INTRODUCED (not pre-existing content): Write.content, or
    # Edit/MultiEdit new strings. Scanning only the new text means scrubbing a
    # secret OUT of a note is never blocked.
    chunks: list[str] = []
    if "content" in ti:
        chunks.append(str(ti.get("content") or ""))
    if "new_string" in ti:
        chunks.append(str(ti.get("new_string") or ""))
    for e in ti.get("edits") or []:
        chunks.append(str((e or {}).get("new_string") or ""))
    text = "\n".join(chunks)
    if not text:
        return _allow()

    for p in PATTERNS:
        if p.name in BLOCK_NAMES and p.regex.search(text):
            return _deny(
                f"Blocked: this write would put a live credential ({p.name}) into "
                f"the note '{Path(fp).name}'. Plaintext secrets in notes get "
                f"committed, synced, and indexed. Store it in the macOS keychain "
                f"or a gitignored secrets file and reference it by name instead. "
                f"If this is a placeholder / example / doc, set "
                f"SECRET_VAULT_WRITE_BYPASS=1 for this write."
            )
    return _allow()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail OPEN: a write-time convenience guard must never block legitimate
        # note-writing on a bug. Ingest-redaction + session-scrub remain the
        # real safety net for anything that slips past.
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "allow"}}))
        sys.exit(0)
