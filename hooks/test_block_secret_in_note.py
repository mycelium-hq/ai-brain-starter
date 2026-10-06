#!/usr/bin/env python3
"""Negative controls for hooks/block-secret-in-note.py, the write-time guard
that refuses to put a live credential into a note.

Why this file exists
--------------------
The guard blocks only the registry patterns named in its BLOCK_NAMES set, and
nothing tied that set to the registry. Every provider pattern added to
_lib/secret_patterns.py after the guard was written (nvidia-api-key,
npm-access-token, backblaze-b2-app-key) was detected and redacted by every
other layer and still written into notes without a word. A guard that matches
nothing on a real input emits the same silence as one that has nothing to
match, so until this file the two were indistinguishable here.

What it checks
--------------
1. The guard, run as a subprocess under the hook contract: JSON on stdin, one
   JSON decision on stdout, exit 0, including raw UTF-8 input (non-ASCII left
   unescaped, as a JSON.stringify writer sends it) on a cp1252 interpreter. A
   positive control on a long-blocked shape (AWS) comes first, so a harness
   that cannot see a deny cannot pass.
2. The newly blocked shapes deny, through Write, Edit and MultiEdit, for every
   note extension and for either key a tool may name the file under.
3. What must stay allowed: the dotfiles nvidia.sh reads its key from, a
   client_secret.json, a removal edit, the bypass, placeholders, and the
   detect-only shapes the guard deliberately leaves alone.
4. A deny echoes no part of a secret, from the content or from the filename.
5. Every registry pattern is classified as blocking or detect-only, so the
   next pattern added to the registry fails here instead of silently skipping
   the guard.

Specimens are real-shaped and non-live, built from split literals so this file
never holds a contiguous secret-shaped string. Failure output never prints one.

Run: python3 hooks/test_block_secret_in_note.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

HOOKS = Path(__file__).resolve().parent
HOOK = HOOKS / "block-secret-in-note.py"
sys.path.insert(0, str(HOOKS))

from _lib.secret_patterns import PATTERNS, scan  # noqa: E402

AWS = "AKIA" + "Q7XK2LM9RT4BV6NC"
NVIDIA = "nvapi-" + "Xy7Zq2Lm9Rt4Bv6N" * 4
GOOGLE_OAUTH = "GOCSPX-" + "Kq7Vn2-Rx9Lt4_Bm6Zc8Wa1Hd3Fj"
NPM = "npm_" + "Ab3Cd5Ef7Gh9" * 3
B2 = "K005" + "Ab3Cd5Ef7" * 3
JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjMifQ" + "." + "SflKxwRJSMeKKF2QT4fw"
HEX = "e3b0c442" * 8
SPECIMENS = [AWS, NVIDIA, GOOGLE_OAUTH, NPM, B2, JWT, HEX]

failures: List[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS {label}")
    else:
        print(f"  FAIL {label} {detail}")
        failures.append(label)


def masked(text: str) -> str:
    for s in SPECIMENS:
        text = text.replace(s, "<SPECIMEN>")
    return text


def run_hook(
    tool_input: Dict[str, object],
    bypass: bool = False,
    extra_env: Optional[Dict[str, str]] = None,
    raw_utf8: bool = False,
) -> Dict[str, object]:
    env = {k: v for k, v in os.environ.items() if k != "SECRET_VAULT_WRITE_BYPASS"}
    if bypass:
        env["SECRET_VAULT_WRITE_BYPASS"] = "1"
    env.update(extra_env or {})
    # raw_utf8 sends non-ASCII as raw UTF-8 bytes, the way Claude Code's
    # JSON.stringify does, instead of json.dumps' \uXXXX escapes.
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Write", "tool_input": tool_input}, ensure_ascii=not raw_utf8),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
    )
    decision: Optional[str] = None
    reason = ""
    try:
        out = json.loads(proc.stdout.strip())["hookSpecificOutput"]
        decision = out.get("permissionDecision")
        reason = out.get("permissionDecisionReason", "")
    except (ValueError, KeyError, TypeError):
        pass
    return {
        "rc": proc.returncode,
        "decision": decision,
        "reason": reason,
        "raw": proc.stdout + proc.stderr,
    }


def leaks(output: str) -> List[str]:
    """Specimens with ANY 10-character window present in the output. A whole-
    string check misses a deny that echoes only part of a secret."""
    found = []
    for s in SPECIMENS:
        if any(s[i:i + 10] in output for i in range(len(s) - 9)):
            found.append(s[:4] + "...")
    return found


def expect(
    label: str,
    tool_input: Dict[str, object],
    want: str,
    names: Optional[str] = None,
    bypass: bool = False,
    extra_env: Optional[Dict[str, str]] = None,
    raw_utf8: bool = False,
) -> None:
    r = run_hook(tool_input, bypass=bypass, extra_env=extra_env, raw_utf8=raw_utf8)
    detail = f"-- rc={r['rc']} decision={r['decision']} reason={masked(str(r['reason']))!r}"
    ok = r["rc"] == 0 and r["decision"] == want
    if ok and names:
        ok = names in str(r["reason"])
    check(label, ok, detail)
    if r["decision"] == "deny":
        leaked = leaks(str(r["raw"]))
        check(f"{label}: the deny echoes no part of a secret", not leaked, f"-- leaked: {leaked}")


def matches(text: str, pattern: str) -> bool:
    return any(name == pattern for name, _ in scan(text))


NOTE = "/tmp/vault/Setup notes.md"

print("specimens match the registry pattern they stand for (precondition):")
for spec, pattern in (
    (AWS, "aws-access-key-id"),
    (NVIDIA, "nvidia-api-key"),
    (GOOGLE_OAUTH, "google-oauth-client-secret"),
    (NPM, "npm-access-token"),
    (B2, "backblaze-b2-app-key"),
    (JWT, "jwt-bearer"),
    (HEX, "hex-256bit-secret"),
):
    check(f"specimen matches {pattern}", matches(f"value: {spec}\n", pattern))

print("\npositive control (a shape the guard has always blocked):")
expect("AWS access key in a note is denied", {"file_path": NOTE, "content": f"aws key {AWS}\n"}, "deny",
       names="aws-access-key-id")

print("\nnewly blocked shapes:")
expect("NVIDIA key in a note (Write) is denied",
       {"file_path": NOTE, "content": f"NVIDIA_API_KEY={NVIDIA}\n"}, "deny", names="nvidia-api-key")
expect("Google OAuth client secret in a note (Write) is denied",
       {"file_path": NOTE, "content": f"Client ID: 123-abc.apps.googleusercontent.com\nClient secret: {GOOGLE_OAUTH}\n"},
       "deny", names="google-oauth-client-secret")
expect("pasted client_secret.json inside a note's code fence is denied",
       {"file_path": NOTE, "content": "```json\n" + json.dumps({"installed": {"client_secret": GOOGLE_OAUTH}}) + "\n```\n"},
       "deny", names="google-oauth-client-secret")
expect("npm token in a note is denied",
       {"file_path": NOTE, "content": f"NPM_TOKEN={NPM}\n"}, "deny", names="npm-access-token")
expect("Backblaze B2 application key in a note is denied",
       {"file_path": NOTE, "content": f"B2_APPLICATION_KEY={B2}\n"}, "deny", names="backblaze-b2-app-key")
expect("NVIDIA key added by an Edit to a .txt note is denied",
       {"file_path": "/tmp/vault/keys.txt", "old_string": "key: TODO", "new_string": f"key: {NVIDIA}"},
       "deny", names="nvidia-api-key")
expect("Google OAuth client secret added by a MultiEdit to a .mdx note is denied",
       {"file_path": "/tmp/vault/setup.mdx", "edits": [
           {"old_string": "a", "new_string": "b"},
           {"old_string": "secret: TODO", "new_string": f"secret: {GOOGLE_OAUTH}"},
       ]},
       "deny", names="google-oauth-client-secret")

expect("an uppercase .MD extension is still a note",
       {"file_path": "/tmp/vault/KEYS.MD", "content": f"key {NVIDIA}\n"}, "deny", names="nvidia-api-key")
expect("a .markdown note is denied",
       {"file_path": "/tmp/vault/setup.markdown", "content": f"secret {GOOGLE_OAUTH}\n"},
       "deny", names="google-oauth-client-secret")
expect("a tool input that names the file under `path` is denied",
       {"path": NOTE, "content": f"key {NVIDIA}\n"}, "deny", names="nvidia-api-key")
expect("SECRET_VAULT_WRITE_BYPASS=0 does not turn the guard off",
       {"file_path": NOTE, "content": f"key {NVIDIA}\n"}, "deny", names="nvidia-api-key",
       extra_env={"SECRET_VAULT_WRITE_BYPASS": "0"})
# The deny names the note, so a secret in the filename must not ride out in it.
expect("a secret in the note's filename is not echoed back",
       {"file_path": f"/tmp/vault/{GOOGLE_OAUTH}.md", "content": f"secret {GOOGLE_OAUTH}\n"},
       "deny", names="google-oauth-client-secret")

print("\nconsole encoding (the hook's `utf8-stdout-ok` marker claims this):")
# Claude Code sends hook input as raw UTF-8. On a cp1252 interpreter, text-mode
# stdin cannot decode the 0x8F that ends the variation selector in `⚙️`,
# and the guard used to fail open on every note under such a folder. The deny
# reason also carries the filename, which has to leave stdout escaped.
expect("raw UTF-8 input for an emoji folder and filename is denied on a cp1252 interpreter",
       {"file_path": "/tmp/vault/⚙️ Meta/Sessions/Configuración \U0001F4C4.md",
        "content": f"key {NVIDIA}\n"},
       "deny", names="nvidia-api-key", extra_env={"PYTHONIOENCODING": "cp1252"}, raw_utf8=True)

print("\nmust stay allowed:")
# nvidia.sh reads NVIDIA_API_KEY from these dotfiles. They are not notes, so the
# guard must never stand between a user and the place the script looks.
expect("NVIDIA key into ~/.zsh_secrets (where nvidia.sh reads it)",
       {"file_path": "/tmp/home/.zsh_secrets", "content": f'export NVIDIA_API_KEY="{NVIDIA}"\n'}, "allow")
expect("NVIDIA key into ~/.env",
       {"file_path": "/tmp/home/.env", "content": f"NVIDIA_API_KEY={NVIDIA}\n"}, "allow")
expect("Google OAuth client secret into client_secret.json",
       {"file_path": "/tmp/home/client_secret.json", "content": json.dumps({"installed": {"client_secret": GOOGLE_OAUTH}})},
       "allow")
expect("an Edit that REMOVES a key from a note",
       {"file_path": NOTE, "old_string": f"key: {NVIDIA}", "new_string": "key: in the keychain"}, "allow")
expect("the documented bypass",
       {"file_path": NOTE, "content": f"example: {GOOGLE_OAUTH}\n"}, "allow", bypass=True)
expect("placeholders that only name the shape",
       {"file_path": NOTE, "content": "NVIDIA_API_KEY=nvapi-YOUR_KEY_HERE\nGWS_CLIENT_SECRET=GOCSPX-YOUR_SECRET_HERE\n"},
       "allow")
expect("prose about the secret format",
       {"file_path": NOTE, "content": "Google's client secret starts with GOCSPX- and NVIDIA keys start with nvapi-.\n"},
       "allow")
expect("a JWT-shaped string (detect-only shape)",
       {"file_path": NOTE, "content": f"example token from the docs: {JWT}\n"}, "allow")
expect("a 64-hex checksum (detect-only shape)",
       {"file_path": NOTE, "content": f"checksum {HEX}\n"}, "allow")
expect("a clean note", {"file_path": NOTE, "content": "Connected my email today.\n"}, "allow")

print("\nevery registry pattern is classified (blocking or detect-only):")
spec = importlib.util.spec_from_file_location("block_secret_in_note", HOOK)
assert spec is not None and spec.loader is not None, f"cannot load {HOOK}"
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

registry = {p.name for p in PATTERNS}
block = set(getattr(mod, "BLOCK_NAMES", set()))
detect_only = dict(getattr(mod, "NOTE_DETECT_ONLY", {}))
check(
    "the guard loaded the full registry (no silent empty fallback)",
    len(getattr(mod, "PATTERNS", ())) == len(PATTERNS) > 0,
    f"-- guard sees {len(getattr(mod, 'PATTERNS', ()))}, registry has {len(PATTERNS)}",
)
check(
    "every BLOCK_NAMES entry names a registry pattern",
    block <= registry,
    f"-- unknown (blocks nothing): {sorted(block - registry)}",
)
check(
    "every NOTE_DETECT_ONLY entry names a registry pattern",
    set(detect_only) <= registry,
    f"-- unknown: {sorted(set(detect_only) - registry)}",
)
check(
    "no pattern is both blocking and detect-only",
    not (block & set(detect_only)),
    f"-- both: {sorted(block & set(detect_only))}",
)
check(
    "every registry pattern has a decision",
    registry <= block | set(detect_only),
    f"-- unclassified: {sorted(registry - block - set(detect_only))}",
)
check(
    "every detect-only entry states why it does not block",
    bool(detect_only) and all(isinstance(r, str) and r.strip() for r in detect_only.values()),
)

print()
if failures:
    print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
    sys.exit(1)
print("All block-secret-in-note checks passed.")
