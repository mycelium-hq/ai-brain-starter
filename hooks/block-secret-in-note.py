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
(AWS / GitHub / Anthropic / OpenAI / NVIDIA / Stripe-secret / Slack / Heroku /
HubSpot / Google API key + OAuth client secret / Resend / Neon / npm /
Backblaze B2 / db-URL passwords). The lower-precision heuristics (bare JWT,
64-hex, Bearer header, publishable keys, generic user:pass@host URLs) do NOT
block a write — they would false-trip on legitimate notes; the ingest +
session-scrub layers still cover them. Every registry pattern is in exactly one
of BLOCK_NAMES or NOTE_DETECT_ONLY below, and a test enforces it.

Scope: note files only (`.md`, `.markdown`, `.mdx`, `.txt`). Code files are out
of scope (test fixtures / `.env.example` have legitimate credential shapes and
other layers cover them).

It scans only the text a call WRITES (Write.content, Edit/MultiEdit new_string),
never the text it replaces, so removing or scrubbing a secret is never blocked.
A secret already in a note that the new text carries along (a full-file Write,
or an Edit whose new_string keeps it) is blocked like a new one: that deny is
the moment to move it out.

Bypass: SECRET_VAULT_WRITE_BYPASS=1 in the environment Claude Code starts with
(a tool call cannot set it for itself), for self-referential docs: this rule,
the hook itself, CLAUDE.md quoting the patterns, a note documenting AWS's
example key.

WIRING (PreToolUse, matcher "Write|Edit|MultiEdit"):
  {"type": "command",
   "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/block-secret-in-note.py 2>/dev/null || echo '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"allow\"}}'"}
"""
from __future__ import annotations

# utf8-stdout-ok: every console write in this module is `print(json.dumps(...))`,
# and json.dumps defaults to ensure_ascii=True, so a non-ASCII note filename in a
# deny reason reaches stdout escaped to \uXXXX. hooks/test_block_secret_in_note.py
# runs a deny for such a filename under a cp1252 console to keep that true.
# Replaces this file's SEV-4-json-encoded row in scripts/utf8-stdout-baseline.txt,
# per that file's rule: rows are DELETED, never re-pinned to stay quiet.

import json
import os
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

try:
    from _lib.secret_patterns import PATTERNS, redact
except Exception:
    PATTERNS = ()

    def redact(text: str) -> tuple[str, list[str]]:  # never reached: no patterns
        return text, []

# High-confidence provider creds + connection-string passwords that never have a
# legitimate reason to sit in a note. Names mirror _lib/secret_patterns.py.
#
# google-oauth-client-secret blocks even though Google says a Desktop app's
# client secret "is obviously not treated as a secret". Web-application clients
# get the same GOCSPX- prefix (FastMCP's Google integration guide shows one),
# Google says not to keep their client_secret.json anywhere publicly
# accessible, and the shape cannot tell the two apart. A note is also never
# where the secret needs to live: an OAuth client reads it from its own config
# (client_secret.json, an env var, an MCP server's settings), while a note is
# synced, committed and indexed.
BLOCK_NAMES = {
    "anthropic-api-key", "nvidia-api-key", "openai-api-key",
    "hubspot-private-app-token", "github-pat-fine-grained", "github-pat-classic",
    "heroku-api-key", "slack-token", "stripe-secret-key", "aws-access-key-id",
    "google-api-key", "google-oauth-client-secret", "resend-api-key",
    "neon-password", "backblaze-b2-app-key", "npm-access-token",
    "postgres-url-password", "redis-url-password", "mongo-url-password",
}
# Registry patterns that deliberately do NOT block a note write, with the reason.
# Every pattern in _lib/secret_patterns.py sits in exactly one of BLOCK_NAMES or
# here, and hooks/test_block_secret_in_note.py fails on a pattern in neither.
# Without that check, nvidia-api-key, npm-access-token and backblaze-b2-app-key
# each joined the registry after this guard was written and never blocked.
NOTE_DETECT_ONLY = {
    "stripe-publishable-key": "publishable by design: it is meant to ship in client-side code",
    "generic-url-credential": "matches any scheme://user:pass@host, so a URL with a port and an @ in its path trips it",
    "jwt-bearer": "a JWT shape alone; notes quote example and expired tokens",
    "bearer-header": "a header shape with no provider prefix to confirm a credential",
    "hex-256bit-secret": "64 hex chars, the same shape as every SHA-256 digest a note quotes",
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
        # Raw bytes decoded as UTF-8, as detect-closing-signal's read_hook_input()
        # does. Claude Code sends UTF-8, but text-mode stdin decodes with the
        # locale codepage, cp1252 on a default Windows console, and the
        # variation selector in a folder name like `⚙️ Meta` ends in byte 0x8F,
        # which cp1252 cannot decode: the UnicodeDecodeError fell through to the
        # fail-open allow below, so the guard waved through every write there.
        buf = getattr(sys.stdin, "buffer", None)
        raw = buf.read().decode("utf-8", errors="replace") if buf is not None else sys.stdin.read()
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return _allow()

    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("path") or ""
    if Path(fp).suffix.lower() not in NOTE_EXTS:
        return _allow()

    # The text this call WRITES: Write.content, or Edit/MultiEdit new strings,
    # never the text it replaces, so scrubbing a secret OUT of a note is never
    # blocked. A secret the new text carries along is blocked like a new one.
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
            # The filename goes through redact() too: a deny that echoes a
            # secret from the path puts it straight back into the transcript.
            name = redact(Path(fp).name)[0]
            return _deny(
                f"Blocked: this write would put a live credential ({p.name}) into "
                f"the note '{name}'. Plaintext secrets in notes get committed, "
                f"synced, and indexed. Keep it in the system keychain or in a "
                f"gitignored secrets file that is not a note "
                f"({', '.join(sorted(NOTE_EXTS))}), and reference it by name. "
                f"For an example or a doc, write a short placeholder instead of "
                f"the real value. Starting Claude Code with "
                f"SECRET_VAULT_WRITE_BYPASS=1 turns this check off for that "
                f"whole session."
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
