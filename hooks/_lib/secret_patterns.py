"""Shared secret-pattern registry.

One module, used by every secret-detection / redaction layer:
- `hooks/redact-bash-secrets.py` (PostToolUse Bash, alerts on detect)
- `hooks/scrub-session-jsonl-secrets.py` (SessionEnd, rewrites JSONLs)
- `hooks/scan-prior-sessions-for-secrets.py` (SessionStart, warns + auto-scrubs closed sessions)
- Any standalone tool that imports `redact()` or `scan()`

Adding a new pattern here automatically covers all layers. That's the
architectural property: the secret-defense surface is one regex file, not
N hooks that each evolved separately.

False-positive discipline: every pattern in this registry that has known
benign matches (Docker image digests, NPM integrity hashes, base64 blobs,
.env.example placeholders) ships with negative lookbehind/lookahead OR
context requirements that skip the benign case. The self-test at the
bottom of this file gates regressions.

Codified initially after a `heroku releases:info` command dumped a batch
of production secrets into a session transcript. The pattern registry +
auto-scrub layer were the structural fix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretPattern:
    """A named secret pattern.

    `name` is the human-readable label that appears in the redaction marker
    and the incident report. `regex` is the compiled pattern. `redaction`
    is the replacement string (use `[REDACTED-{name}]` by convention).

    `description` documents the source so future maintainers know why this
    pattern lives in the registry.
    """

    name: str
    regex: re.Pattern[str]
    redaction: str
    description: str


# Provider-issued credentials (long-lived; high blast radius)
_PROVIDER = [
    SecretPattern(
        name="anthropic-api-key",
        regex=re.compile(r"sk-ant-api\d{2}-[\w\-]{40,}", re.ASCII),
        redaction="[REDACTED-anthropic-api-key]",
        description="Anthropic API key, format sk-ant-api{NN}-{token}.",
    ),
    SecretPattern(
        # Tightened after early audits: original `{20,}` matched
        # documentation placeholders like `sk-...`, `sk-xxxxx`, `sk-YOUR_KEY`.
        # Real OpenAI keys are >=48 chars after the sk- prefix (legacy) or 56
        # chars after sk-proj- (newer). Requires alphanumerics dominate (no
        # `.`, `_-` are rare). Avoids matching sk-ant- (Anthropic).
        name="openai-api-key",
        regex=re.compile(
            r"sk-(?!ant-)(?:proj-[A-Za-z0-9_\-]{56,}|[A-Za-z0-9]{48,})\b",
            re.ASCII,
        ),
        redaction="[REDACTED-openai-api-key]",
        description="OpenAI API key (sk-... >=48 chars, or sk-proj-... >=56 chars).",
    ),
    SecretPattern(
        name="hubspot-private-app-token",
        regex=re.compile(r"pat-na[12]-[\w\-]{20,}", re.ASCII),
        redaction="[REDACTED-hubspot-pat]",
        description="HubSpot private app access token, format pat-na{1,2}-{token}.",
    ),
    SecretPattern(
        name="github-pat-fine-grained",
        regex=re.compile(r"github_pat_[A-Za-z0-9_]{60,}", re.ASCII),
        redaction="[REDACTED-github-pat]",
        description="GitHub fine-grained personal access token.",
    ),
    SecretPattern(
        name="github-pat-classic",
        regex=re.compile(r"gh[ps]_[A-Za-z0-9]{36,}", re.ASCII),
        redaction="[REDACTED-github-pat-classic]",
        description="GitHub classic PAT (ghp_ / ghs_) or OAuth (gho_).",
    ),
    SecretPattern(
        name="heroku-api-key",
        regex=re.compile(r"HRKU-[A-Za-z0-9]{32,}", re.ASCII),
        redaction="[REDACTED-heroku-api-key]",
        description="Heroku API key, format HRKU-{32+ chars}.",
    ),
    SecretPattern(
        name="slack-token",
        regex=re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}", re.ASCII),
        redaction="[REDACTED-slack-token]",
        description="Slack tokens (xoxa, xoxb, xoxp, xoxr, xoxs).",
    ),
    SecretPattern(
        name="stripe-secret-key",
        regex=re.compile(r"sk_(?:test|live)_[A-Za-z0-9]{24,}", re.ASCII),
        redaction="[REDACTED-stripe-secret-key]",
        description="Stripe secret key (sk_test_ or sk_live_).",
    ),
    SecretPattern(
        name="stripe-publishable-key",
        regex=re.compile(r"pk_(?:test|live)_[A-Za-z0-9]{24,}", re.ASCII),
        redaction="[REDACTED-stripe-publishable-key]",
        description="Stripe publishable key (low risk but flagged for visibility).",
    ),
    SecretPattern(
        name="aws-access-key-id",
        regex=re.compile(r"AKIA[0-9A-Z]{16}", re.ASCII),
        redaction="[REDACTED-aws-access-key-id]",
        description="AWS access key ID (the ID itself is sensitive in context).",
    ),
    SecretPattern(
        # Tightened after PDF/base64-binary content in big session JSONLs
        # tripped false-positives: `AIza` appearing mid-base64 with 35
        # alphanumerics immediately following. Real keys are delimited by
        # quote / equals / whitespace / line-start. Char-class lookbehind+
        # lookahead blocks mid-base64 matches but still matches real keys at
        # clean boundaries.
        name="google-api-key",
        regex=re.compile(
            r"(?<![A-Za-z0-9_\-])AIza[A-Za-z0-9_\-]{35}(?![A-Za-z0-9_\-])",
            re.ASCII,
        ),
        redaction="[REDACTED-google-api-key]",
        description="Google API key. Requires non-alphanumeric boundary on both sides to skip base64-binary substring false positives.",
    ),
    SecretPattern(
        name="resend-api-key",
        # Skip `.env.example` placeholders like `re_xxxxxxxxxxxxxxxxxxxx` (all
        # literal x's) or `re_YOUR_KEY_HERE`-style sentinels — those are docs,
        # not credentials. Real Resend keys are random alphanumerics.
        regex=re.compile(
            r"\bre_(?!x{20,}\b)(?!YOUR[_-])(?!your[_-])[A-Za-z0-9]{20,}",
            re.ASCII,
        ),
        redaction="[REDACTED-resend-api-key]",
        description="Resend API key. Skips `re_xxxx...` and `re_YOUR_KEY` placeholders.",
    ),
    SecretPattern(
        # Added after a Comet-style rotation leaked an npg_-prefixed password
        # standalone (not inside a postgres:// URL), bypassing the
        # postgres-url-password pattern below.
        name="neon-password",
        regex=re.compile(r"\bnpg_[A-Za-z0-9]{12,}\b", re.ASCII),
        redaction="[REDACTED-neon-password]",
        description="Neon-issued database password (npg_ prefix, >=12 chars).",
    ),
]


# Embedded credentials in connection strings (the value AFTER user: AND BEFORE @)
# We redact just the password portion to keep the URL structure (host, db name,
# query params) legible.
_CONNECTION_STRING = [
    SecretPattern(
        # Redaction includes a space so the marker doesn't match the
        # password group `[^@\s]+` on a second pass — keeps redact() idempotent.
        name="postgres-url-password",
        regex=re.compile(
            r"(postgres(?:ql)?://[^:/\s]+:)([^@\s]+)(@)",
            re.ASCII | re.IGNORECASE,
        ),
        redaction=r"\1REDACTED pg password\3",
        description="Password inside a postgres:// or postgresql:// connection URL.",
    ),
    SecretPattern(
        name="redis-url-password",
        regex=re.compile(
            r"(rediss?://[^:/\s]*:)([^@\s]+)(@)",
            re.ASCII | re.IGNORECASE,
        ),
        redaction=r"\1REDACTED redis password\3",
        description="Password inside a redis:// or rediss:// connection URL.",
    ),
    SecretPattern(
        name="mongo-url-password",
        regex=re.compile(
            r"(mongodb(?:\+srv)?://[^:/\s]+:)([^@\s]+)(@)",
            re.ASCII | re.IGNORECASE,
        ),
        redaction=r"\1REDACTED mongo password\3",
        description="Password inside a mongodb:// or mongodb+srv:// connection URL.",
    ),
]


# Generic-shape patterns (heuristic; lower precision, higher recall)
_GENERIC = [
    SecretPattern(
        name="jwt-bearer",
        regex=re.compile(
            r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
            re.ASCII,
        ),
        redaction="[REDACTED-jwt]",
        description="JWT-shaped token (header.payload.signature, base64url).",
    ),
    SecretPattern(
        name="bearer-header",
        regex=re.compile(
            r"(Authorization:\s*Bearer\s+)([\w\-\.~+/=]{20,})",
            re.ASCII | re.IGNORECASE,
        ),
        redaction=r"\1[REDACTED-bearer]",
        description="Authorization: Bearer <token> header value.",
    ),
    SecretPattern(
        name="hex-256bit-secret",
        regex=re.compile(
            # Skip content-integrity hashes: sha256: / sha512: / sha384: /
            # sha1: / md5: prefixes (GitHub Releases asset digests, Docker
            # image manifests, NPM hex-integrity, etag/digest HTTP headers).
            # Added after release-asset JSON tripped this pattern on every
            # `gh release view` and `gh api .../releases` response — those
            # sha256 digests are public by design, not secrets. Each
            # lookbehind is fixed-width so compiles cleanly.
            #
            # Dot-prefix variants (sha256. / sha512. / sha384. / sha1. /
            # md5.) added for pnpm's `packageManager` field format
            # `pnpm@VERSION+sha256.HASH` (also yarn integrity
            # `<algo>-<base64>` and some lockfile formats).
            r"(?<!sha256:)(?<!sha512:)(?<!sha384:)(?<!sha1:)(?<!md5:)"
            r"(?<!sha256\.)(?<!sha512\.)(?<!sha384\.)(?<!sha1\.)(?<!md5\.)"
            r"(?<![A-Fa-f0-9])([A-Fa-f0-9]{64})(?![A-Fa-f0-9])",
            re.ASCII,
        ),
        redaction="[REDACTED-hex-256bit]",
        description="64-char hex string (256-bit secret; HMAC, openssl rand -hex 32). Skips common content-digest prefixes (sha{1,256,384,512}:, md5:) and integrity-hash dot prefixes (sha{1,256,384,512}., md5.) used by pnpm/yarn.",
    ),
]


# Aggregate registry (order matters — connection strings first so URL password
# match wins over a JWT-like substring of the URL; provider patterns last so
# they don't shadow more specific patterns).
PATTERNS: tuple[SecretPattern, ...] = tuple(
    _CONNECTION_STRING + _PROVIDER + _GENERIC
)


def redact(text: str) -> tuple[str, list[str]]:
    """Apply every registered pattern. Return (redacted_text, hit_names).

    `hit_names` is the list of pattern names that matched at least once.
    Caller uses it for incident-reporting + the "what got rotated" stamp.

    Idempotent: redacted text passed back through `redact()` returns
    (text, []) — the redaction markers themselves don't match any pattern.
    """
    hits: list[str] = []
    out = text
    for p in PATTERNS:
        new, n = p.regex.subn(p.redaction, out)
        if n > 0:
            hits.append(p.name)
            out = new
    return out, hits


def scan(text: str) -> list[tuple[str, int]]:
    """Read-only scan. Return [(pattern_name, match_count), ...].

    Use this for detection-without-mutation paths (PostToolUse alert,
    SessionStart warning). Output is empty when the text is clean.
    """
    results: list[tuple[str, int]] = []
    for p in PATTERNS:
        matches = p.regex.findall(text)
        if matches:
            results.append((p.name, len(matches)))
    return results


# Self-test (run `python3 -m hooks._lib.secret_patterns`)
if __name__ == "__main__":
    SAMPLES = {
        "anthropic-api-key": "sk-ant-api03-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "hubspot-pat": "pat-na1-AAAAAAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        "postgres-url": "postgres://user:hunter2_supersecret@db.example.com:5432/dbname",
        "redis-url": "rediss://:p123abc456def@redis.example.com:6379",
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        "github-pat": "github_pat_AAAAAAAAAAAAAAAAAAAAAA_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN",
        "hex-256": "a" * 64,
        "clean": "no secrets here just regular text and code",
    }
    for label, sample in SAMPLES.items():
        redacted, hits = redact(sample)
        print(f"{label}: hits={hits}")
        if "REDACTED" in redacted:
            print(f"  -> {redacted}")
    print("\nIdempotency check:")
    once, _ = redact("sk-ant-api03-" + "x" * 50)
    twice, hits2 = redact(once)
    assert once == twice, "non-idempotent"
    assert hits2 == [], f"second pass should produce no hits, got {hits2}"
    print("  OK: redaction is idempotent.")

    # False-positive exclusions — gate regressions.
    print("\nFalse-positive exclusion checks:")
    FP_SAMPLES = {
        # sha256:<hex> content digest (GitHub release asset, Docker manifest)
        "github-asset-digest": '"digest":"sha256:' + "a" * 64 + '"',
        # sha512:<hex> NPM hex-integrity, Docker manifest
        "sha512-hex": "sha512:" + "b" * 64,
        # pnpm packageManager integrity hash (dot separator, not colon)
        "pnpm-package-manager": '"packageManager": "pnpm@10.11.1+sha256.' + "c" * 64 + '"',
        # Real 256-bit hex secret — MUST still match
        "real-hex-secret": "API_KEY=" + "d" * 64,
        # Resend literal placeholder (`re_x` * 30 in .env.example)
        "resend-placeholder-xs": "RESEND_API_KEY=re_" + "x" * 30,
        # Resend YOUR_KEY-style placeholder
        "resend-placeholder-your": "RESEND_API_KEY=re_YOUR_API_KEY_HERE_123",
        # Real Resend key — MUST still match
        "real-resend-key": "RESEND_API_KEY=re_AbCdEfGh12345678IjKlMn",
        # AIza substring inside base64-binary content (mid-blob, no boundary)
        "aiza-in-base64": "...ZNAEUVnbQjEVvEg3bvlQDn1oABZWqpKAIza" + "X" * 35 + "trm1xb...",
        # Real Google API key — MUST still match (quoted assignment)
        "real-google-api-key": 'GOOGLE_MAPS_KEY="AIza' + "Y" * 35 + '"',
        # Real Google API key at line start — MUST still match
        "real-google-api-key-bare": "AIza" + "Z" * 35,
    }
    expected_hits = {
        "github-asset-digest": [],   # sha256: prefix → skipped
        "sha512-hex": [],            # sha512: prefix → skipped
        "pnpm-package-manager": [],  # sha256. prefix → skipped
        "real-hex-secret": ["hex-256bit-secret"],
        "resend-placeholder-xs": [],
        "resend-placeholder-your": [],
        "real-resend-key": ["resend-api-key"],
        "aiza-in-base64": [],         # surrounded by alphanumerics → skipped
        "real-google-api-key": ["google-api-key"],
        "real-google-api-key-bare": ["google-api-key"],
    }
    failures = 0
    for label, sample in FP_SAMPLES.items():
        _, hits = redact(sample)
        want = expected_hits[label]
        ok = hits == want
        print(f"  [{'OK' if ok else 'FAIL'}] {label}: got={hits} want={want}")
        if not ok:
            failures += 1
    if failures:
        raise SystemExit(f"\n{failures} FP-exclusion check(s) failed.")
    print("  OK: all FP exclusions behave as expected.")
