"""llm_synth.py: optional Anthropic-API helper for synth-* skills.

Used by skills/synth-pr-to-sop/synth.py and skills/synth-thread-to-sop/synth.py
when --use-llm is passed. Default operator-driven mode never imports this.

The function `refine_extraction` takes a raw text blob plus a classification
hint and returns a dict the calling synth.py merges into its frontmatter.
The heuristic pass owns idempotency keys (sha8, source IDs) — the LLM only
refines title, steps, summary, owners.

Caching strategy: the system prompt is identical across every invocation of
the same memory_class, so it is the right cache anchor. Cache TTL is 1h
because operators run synth in bursts when they catch up on a backlog.

The module returns (result, error) tuples; callers can decide whether a
missing dep or API failure should surface as a hard error or a graceful
fall-through to heuristic mode.
"""
from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1500

SYSTEM_PROMPT_TEMPLATE = """You extract structured memory from messy operator notes.

You will be given the body of a {kind} (a merged GitHub PR, a Slack thread,
or similar) and asked to return a single JSON object that conforms to the
schema below. No prose, no explanation, just the JSON.

Schema for type="{type_name}":
{schema_json}

Extraction rules:
- "title" must be a short noun phrase that names the artifact.
- "steps" must be an ordered list. Each step is a single imperative sentence.
- For decisions: capture WHAT was decided and WHY in `summary`. Note dissenters
  by name in `dissent` if present.
- For exceptions: name the rule the exception carves out from in `parent_rule`.
- For workflows: each step is one operational action. Owners go in `owner`.
- Never invent participants, dates, dollar amounts, or rule IDs that are not
  in the source. If a field is unknown, omit it; do not write null or "".
- Output JSON only.
"""

WORKFLOW_SCHEMA = {
    "title": "string (short)",
    "steps": [
        {"step_number": "int", "description": "string", "owner": "optional string"}
    ],
    "summary": "optional string",
}

DECISION_SCHEMA = {
    "title": "string (short)",
    "summary": "string",
    "rationale": "optional string",
    "owners": "optional list of names",
    "dissent": "optional string",
}

EXCEPTION_SCHEMA = {
    "title": "string (short)",
    "summary": "string",
    "parent_rule": "optional string",
    "scope": "optional string",
}

SCHEMA_BY_TYPE = {
    "workflow": WORKFLOW_SCHEMA,
    "decision": DECISION_SCHEMA,
    "exception": EXCEPTION_SCHEMA,
}


def is_available() -> tuple[bool, str]:
    """Return (ok, reason). False if anthropic dep missing or no API key."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "anthropic package not installed (pip install anthropic)"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY not set in environment"
    return True, "ok"


def _build_system_prompt(memory_type: str, kind: str) -> str:
    schema = SCHEMA_BY_TYPE.get(memory_type, WORKFLOW_SCHEMA)
    return SYSTEM_PROMPT_TEMPLATE.format(
        kind=kind,
        type_name=memory_type,
        schema_json=json.dumps(schema, indent=2),
    )


def _make_client(client_factory=None):
    """Indirection point so tests can monkeypatch."""
    if client_factory is not None:
        return client_factory()
    import anthropic
    return anthropic.Anthropic()


def refine_extraction(
    raw_text: str,
    memory_type: str,
    *,
    kind: str = "merged PR or Slack thread",
    model: str = DEFAULT_MODEL,
    client_factory=None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Call Anthropic to refine a heuristic extraction.

    Returns (parsed_json, None) on success or (None, error_message) on failure.
    Callers should NOT raise on error; they should fall back to heuristic-only.
    """
    ok, reason = is_available()
    if not ok and client_factory is None:
        return None, reason

    if memory_type not in SCHEMA_BY_TYPE:
        return None, f"unknown memory_type: {memory_type}"

    if not raw_text.strip():
        return None, "empty raw_text"

    system_prompt = _build_system_prompt(memory_type, kind)

    try:
        client = _make_client(client_factory=client_factory)
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ],
            messages=[
                {"role": "user", "content": raw_text[:20000]},
            ],
        )
    except Exception as exc:
        return None, f"anthropic API error: {exc.__class__.__name__}: {exc}"

    text_blocks = []
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            text_blocks.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            text_blocks.append(block.get("text", ""))
    raw = "\n".join(text_blocks).strip()
    if not raw:
        return None, "empty response from anthropic"

    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"could not parse JSON from response: {exc}"
    if not isinstance(parsed, dict):
        return None, "response was not a JSON object"
    return parsed, None


def cache_metrics(response) -> dict[str, int]:
    """Pull cache_read_input_tokens / cache_creation_input_tokens off the
    Anthropic SDK response object. Useful for verifying that the system block
    is in fact being cached after the first call.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }
