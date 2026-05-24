"""Shared Claude-routing helper for vault scripts.

Routes Claude calls in priority order:

  1. Local `claude -p` CLI (Max plan via OAuth/keychain). DEFAULT.
  2. Anthropic SDK with ANTHROPIC_API_KEY (legacy, separate billing).
  3. Caller-supplied fallback (e.g., MiniMax). Optional.

Why this exists: vault scripts that hit `https://api.anthropic.com/v1/messages`
directly burn through API-key billing while a Max plan covers the same
model via the local `claude` CLI. Documented in
`⚙️ Meta/Critical Failure Inventory.md` "Schedule + cron surface" entry
(2026-05-10) and the substrate audit at
`🏠 Home/Substrate Audit/2026-05-10.md`.

Escape hatch: set `CLAUDE_ROUTER_PREFER_API_KEY=1` to skip the CLI step
and go directly to API-key billing. Set `CLAUDE_ROUTER_DISABLE_CLI=1`
to force the API-key path even when the CLI is present.

Usage:

    from _claude_router import call_claude_text

    text = call_claude_text(
        system="You are a JSON generator. Reply only with valid JSON.",
        user="Extract {names, dates} from: ...",
        model="haiku",          # alias OR full model ID
        max_tokens=2048,
    )

    # For structured JSON output:
    from _claude_router import call_claude_json
    obj = call_claude_json(
        system="...",
        user="...",
        model="haiku",
    )

If both the CLI and API key are unavailable, raises `RouterUnavailable`.
Caller can catch and fall through to its own fallback (MiniMax, etc).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


__all__ = [
    "call_claude_text",
    "call_claude_json",
    "RouterUnavailable",
]


CLI_TIMEOUT_SECONDS = 600
API_TIMEOUT_SECONDS = 180


class RouterUnavailable(RuntimeError):
    """Raised when neither the CLI nor an API key is available."""


def _log(msg: str) -> None:
    """Stderr log so it doesn't pollute the JSON output capture."""
    print(f"[claude-router] {msg}", file=sys.stderr)


def _resolve_cli() -> str | None:
    """Find the local `claude` CLI binary, or None if missing."""
    if os.environ.get("CLAUDE_ROUTER_DISABLE_CLI") == "1":
        return None

    explicit = os.environ.get("CLAUDE_CLI_PATH")
    if explicit and Path(explicit).exists():
        return explicit

    candidate = shutil.which("claude")
    if candidate:
        return candidate

    home = Path.home()
    for fallback in [
        home / "local/node-v20.19.0-darwin-arm64/bin/claude",
        home / ".local/bin/claude",
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
    ]:
        if fallback.exists():
            return str(fallback)

    return None


def _resolve_api_key() -> str | None:
    """Look for ANTHROPIC_API_KEY in env. Caller is responsible for sourcing
    ~/.zsh_secrets if needed (this helper does not read user secrets files)."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def _call_via_cli(
    cli: str, system: str, user: str, model: str
) -> str:
    """Run `claude -p` and return stdout text.

    Acceptance logic:
      - exit 0 with any stdout (including "PONG.") → accept
      - exit non-zero with non-empty stdout → accept (likely a SessionEnd
        hook failed AFTER Claude wrote its response; throwing the response
        away just because the hook failed is a regression we explicitly
        log + accept past)
      - exit non-zero with empty stdout → real failure, raise

    `claude -p` runs SessionStart and SessionEnd hooks even in print mode;
    a failing hook (sync-my-skills.sh push, etc.) used to bubble up as exit 1
    even when Claude succeeded. The earlier MIN_RESPONSE_CHARS heuristic was
    wrong because legitimate replies can be very short ("PONG.", "Yes", "42").
    """
    cmd = [
        cli,
        "-p",
        user,
        "--append-system-prompt",
        system,
        "--model",
        model,
        "--no-session-persistence",
        "--disable-slash-commands",
        "--dangerously-skip-permissions",
    ]
    _log(f"calling via CLI ({cli}, model={model})")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SECONDS,
            check=False,  # tolerate non-zero exits with valid stdout
        )
    except subprocess.TimeoutExpired as e:
        raise RouterUnavailable(
            f"claude CLI timed out after {CLI_TIMEOUT_SECONDS}s"
        ) from e

    stdout = result.stdout.strip()
    # Refusal markers — CLI returned a string but it's an auth/refusal banner,
    # not an actual model response. Treat as CLI unavailable so the router
    # falls back to API. Patched 2026-05-19 after hallucination-sample-audit
    # accepted "Not logged in · Please run /login" as a 33-char success.
    refusal_markers = (
        "not logged in",
        "please run /login",
        "authentication required",
        "authentication failed",
        "session expired",
    )
    if stdout and any(m in stdout.lower() for m in refusal_markers):
        raise RouterUnavailable(
            f"claude CLI returned refusal banner: {stdout[:200]!r}. "
            "Subprocess cannot reach Max OAuth — set ANTHROPIC_API_KEY for "
            "API fallback, or run from a shell with claude CLI logged in."
        )

    if result.returncode == 0:
        return stdout

    if stdout:
        _log(
            f"CLI exit {result.returncode} but stdout has "
            f"{len(stdout)} chars — accepting (likely SessionEnd "
            f"hook failure post-response)"
        )
        return stdout

    raise RouterUnavailable(
        f"claude CLI exit {result.returncode} with empty stdout. "
        f"stderr: {result.stderr[:300]}"
    )


def _call_via_api(
    api_key: str,
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    cache_system: bool = True,
) -> str:
    """POST to api.anthropic.com Messages API. Returns the first text block.

    When `cache_system=True` (default), wraps the system prompt in a single
    `cache_control=ephemeral` block so the Anthropic prompt cache is reused
    across calls with the same prefix. The API silently no-ops when the
    prefix is below the model's cache minimum (1K tokens for Sonnet 4.5 /
    Opus 4.1, 4K for Opus 4.7 / Sonnet 4.6 / Haiku 4.5), so opt-in is
    safe at any size.

    Logs `cache_read_input_tokens` / `cache_creation_input_tokens` from the
    response so logs can confirm caching fires on repeated calls.
    """
    system_payload: object
    if cache_system:
        system_payload = [{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }]
    else:
        system_payload = system
    payload = json.dumps(
        {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_payload,
            "messages": [{"role": "user", "content": user}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    _log(f"calling via API key (model={model}, cache_system={cache_system})")
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RouterUnavailable(
            f"Anthropic API error {e.code}: {e.read().decode()[:300]}"
        ) from e
    except urllib.error.URLError as e:
        raise RouterUnavailable(f"Anthropic network error: {e}") from e
    # Cache metrics. Non-zero read means a hit (0.1x cost for those tokens).
    usage = body.get("usage", {}) or {}
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_write = usage.get("cache_creation_input_tokens", 0) or 0
    if cache_read or cache_write:
        _log(f"cache: read={cache_read} tok, write={cache_write} tok")
    blocks = body.get("content", [])
    if not blocks:
        return ""
    return blocks[0].get("text", "")


def call_claude_text(
    system: str,
    user: str,
    model: str = "haiku",
    max_tokens: int = 4096,
    cache_system: bool = True,
) -> str:
    """Call Claude and return the response text.

    Routing order: CLI (Max plan) → API key. Raises `RouterUnavailable`
    if neither is available.

    Model aliases: "haiku", "sonnet", "opus", or any full model ID
    (e.g., "claude-haiku-4-5-20251001"). The CLI accepts both forms.

    `cache_system` controls Anthropic prompt caching on the API path. Default
    True. The CLI path caches automatically — Claude Code handles it
    transparently and the flag is ignored there. Set False only when the
    caller varies the system prompt per call (benchmarks, evals, sweeps).
    """
    prefer_api = os.environ.get("CLAUDE_ROUTER_PREFER_API_KEY") == "1"

    cli = None if prefer_api else _resolve_cli()
    if cli is not None:
        try:
            return _call_via_cli(cli, system, user, model)
        except RouterUnavailable as e:
            _log(f"CLI failed, falling back to API: {e}")

    api_key = _resolve_api_key()
    if api_key is not None:
        return _call_via_api(api_key, system, user, model, max_tokens, cache_system)

    raise RouterUnavailable(
        "no claude CLI and no ANTHROPIC_API_KEY — install `claude` "
        "(`npm i -g @anthropic-ai/claude-code`) or export ANTHROPIC_API_KEY."
    )


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def call_claude_json(
    system: str,
    user: str,
    model: str = "haiku",
    max_tokens: int = 4096,
    cache_system: bool = True,
) -> dict | list:
    """Call Claude and parse the response as JSON.

    Strips markdown code fences if the model adds them. Raises
    `RouterUnavailable` if no transport is available, or `ValueError`
    if the response is not valid JSON.

    See `call_claude_text` for `cache_system` semantics (default True).
    """
    text = call_claude_text(system, user, model, max_tokens, cache_system)
    stripped = text.strip()
    fence_match = _FENCE_RE.match(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Claude returned non-JSON ({len(text)} chars): "
            f"{text[:300]!r}"
        ) from e
