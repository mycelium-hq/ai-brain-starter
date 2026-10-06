#!/usr/bin/env python3
"""Regression tests for the Google OAuth client secret pattern (`GOCSPX-`).

Why this file exists
--------------------
The google-workspace-mcp connector's guided setup has people create their own
OAuth client and hand its client secret to the connector's installer. The
registry had no pattern for that shape, so the transcript scrub, the scheduled
prior-session scan, the Bash-output alert and the note guard were all blind to
the one Google credential that setup has people copy by hand. Same class as the
nvidia-api-key entry: a credential the docs send you to is a credential the
guards must see.

The shape, and why the specimen is checked first
------------------------------------------------
`GOCSPX-` + exactly 28 characters of [A-Za-z0-9_-], 35 in all. That is what
the client-secret rule in Google's own scanner matches (osv-scalibr,
veles/secrets/gcpoauth2client: `\\bGOCSPX-[a-zA-Z0-9_-]{28}`), and a real client
secret measured for this change (length and character classes only) had a
28-character body.
A specimen of the wrong shape reports a false "no coverage" or a false
"covered", and both read like real results, so the first checks below assert
the specimen itself before anything is concluded from it.

As in test_secret_patterns_nvidia.py, each positive case varies the
ENCODING/CONTEXT the secret travels in, not the token. Failure messages mask
the specimen, so a red run never prints a secret-shaped string into a log.

Run: python3 hooks/test_secret_patterns_google_oauth.py
"""

from __future__ import annotations

import json
import string
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))

from _lib.secret_patterns import PATTERNS, redact, scan  # noqa: E402

PATTERN_NAME = "google-oauth-client-secret"
PREFIX = "GOCSPX-"
# Real-shaped, non-live. Split from PREFIX so this source file never holds a
# contiguous secret-shaped string for another scanner to trip on.
BODY = "Kq7Vn2-Rx9Lt4_Bm6Zc8Wa1Hd3Fj"
SECRET = PREFIX + BODY
CHARSET = set(string.ascii_letters + string.digits + "_-")

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS {label}")
    else:
        print(f"  FAIL {label} {detail}")
        failures.append(label)


def masked(text: str) -> str:
    return text.replace(SECRET, "<SPECIMEN>")


print("specimen shape (asserted before it is used as evidence):")
check("body is exactly 28 characters", len(BODY) == 28, f"-- got {len(BODY)}")
check("body uses only [A-Za-z0-9_-]", set(BODY) <= CHARSET)
for cls, members in (
    ("upper", string.ascii_uppercase),
    ("lower", string.ascii_lowercase),
    ("digit", string.digits),
    ("dash", "-"),
    ("underscore", "_"),
):
    check(f"body exercises the {cls} class", any(c in members for c in BODY))

print("\npattern is registered:")
check(
    f"{PATTERN_NAME} present in PATTERNS",
    any(p.name == PATTERN_NAME for p in PATTERNS),
    "-- no layer that imports the registry can see a GOCSPX- secret",
)

print("\npositive cases (encoding varies, token is constant):")
POSITIVE = {
    "bare token": SECRET,
    "client_secret.json as Google Cloud Console downloads it": json.dumps(
        {"installed": {
            "client_id": "123456789012-abc123def456.apps.googleusercontent.com",
            "client_secret": SECRET,
            "redirect_uris": ["http://localhost"],
        }}
    ),
    "installer invocation, single-quoted env var": (
        f"GWS_CLIENT_ID='123-abc.apps.googleusercontent.com' "
        f"GWS_CLIENT_SECRET='{SECRET}' bash install.sh"
    ),
    "PowerShell env assignment": f"$env:GWS_CLIENT_SECRET = '{SECRET}'",
    "claude mcp add -e form": (
        f"claude mcp add gws -s user -e GWS_CLIENT_SECRET={SECRET} -- python server.py"
    ),
    "token-refresh form body": (
        f"client_id=123-abc.apps.googleusercontent.com&client_secret={SECRET}"
        f"&grant_type=refresh_token"
    ),
    "markdown note line": f"- Client secret: {SECRET}\n",
    "inside a longer log line": f"2026-09-30 INFO oauth client loaded secret={SECRET} scopes=9",
}
for label, text in POSITIVE.items():
    hits = scan(text)
    check(
        f"caught in {label}",
        any(name == PATTERN_NAME for name, _ in hits),
        f"-- scan returned {hits}",
    )

print("\ncharset edges (a real body can start or end with - or _):")
EDGES = {
    "body starts with -": PREFIX + "-" + BODY[1:],
    "body starts with _": PREFIX + "_" + BODY[1:],
    "body ends with _": PREFIX + BODY[:-1] + "_",
    # A trailing \b would miss this one: '-' then '"' is no word boundary.
    "body ends with -, inside JSON quotes": '{"client_secret": "' + PREFIX + BODY[:-1] + '-"}',
    # The deliberate departure from Google's leading \b: glued to a word char.
    "glued after a URL-encoded =": "client_secret%3D" + SECRET + "&grant_type=x",
}
for label, text in EDGES.items():
    hits = [h for h in scan(text) if h[0] == PATTERN_NAME]
    check(f"caught when {label}", bool(hits), f"-- got {hits}")

print("\nnegative cases (must NOT fire -- these are not client secrets):")
NEGATIVE = {
    "short placeholder": "GWS_CLIENT_SECRET=GOCSPX-YOUR_SECRET_HERE",
    "bare prefix in prose": "The secret usually starts with GOCSPX- and is 35 characters long.",
    # Pins the 28 floor: one character short of the real shape.
    "27-character body": PREFIX + BODY[:-1],
    "near-miss prefix": "GOCSP-" + BODY,
    "lowercase prefix (Google issues it uppercase)": "gocspx-" + BODY,
    # The client ID is a public identifier, not the secret.
    "client ID alone": "123456789012-abc123def456.apps.googleusercontent.com",
}
for label, text in NEGATIVE.items():
    hits = [h for h in scan(text) if h[0] == PATTERN_NAME]
    check(f"no false positive on {label}", not hits, f"-- got {hits}")

print("\nredaction:")
redacted, _ = redact(f"GWS_CLIENT_SECRET='{SECRET}'")
check("secret does not survive redaction", SECRET not in redacted, f"-- got {masked(redacted)!r}")
check(
    "redaction is labelled",
    f"REDACTED-{PATTERN_NAME}" in redacted,
    f"-- got {masked(redacted)!r}",
)
twice, hits2 = redact(redacted)
check("redaction is idempotent", twice == redacted and hits2 == [], f"-- got {hits2}")

# A longer run must be redacted whole: `{28,}` takes the full token, so no
# tail of it survives next to the marker.
longer = PREFIX + BODY + "Zz9_"
red_long, _ = redact(f"secret={longer} next")
check(
    "a longer-than-28 run is redacted whole",
    PREFIX not in red_long and "Zz9_" not in red_long,
    f"-- got {red_long.replace(longer, '<LONGER-SPECIMEN>')!r}",
)

# A scrubbed client_secret.json must stay valid JSON, and only the secret goes:
# the client ID (a public identifier) is still there to tell clients apart.
doc = POSITIVE["client_secret.json as Google Cloud Console downloads it"]
red_doc, _ = redact(doc)
try:
    parsed = json.loads(red_doc)
    still_json = True
except ValueError:
    parsed, still_json = {}, False
check("a redacted client_secret.json still parses", still_json, f"-- got {masked(red_doc)!r}")
check(
    "redaction leaves the client ID in place",
    parsed.get("installed", {}).get("client_id", "").endswith(".apps.googleusercontent.com"),
    f"-- got {masked(red_doc)!r}",
)

print()
if failures:
    print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
    sys.exit(1)
print("All google-oauth-client-secret pattern checks passed.")
