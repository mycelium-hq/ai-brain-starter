---
type: rule
applies_to: every code surface that calls the Anthropic Messages API
---

Default ON for every Claude-calling surface. The Anthropic API silently no-ops when the prefix is below the model minimum, so opt-in is free and future-proofs the surface against later prompt growth.

## When to cache

| Situation | Cache it? |
|---|---|
| Stable system prompt + repeated calls | YES (default) |
| Tool definitions shared across calls | YES — `cache_control` on the last tool |
| Large document analyzed many times | YES — cache the doc, not the question |
| Per-call prompt is unique (benchmarks, sweeps) | NO — pass `cache_system=False` |
| Tiny system today (< minimum), might grow later | YES anyway — API no-ops if too small, no cost |

## Minimum cacheable size

| Model | Minimum |
|---|---|
| Sonnet 4.5, Opus 4.1 | 1,024 tokens |
| Opus 4.7, Sonnet 4.6, Haiku 4.5 | 4,096 tokens |
| Haiku 3.5 (Vertex only) | 2,048 tokens |

Below minimum → cache silently no-ops. Caching anyway is free.

## Pricing (multipliers on base input price)

| Operation | Cost |
|---|---|
| 5m cache write | 1.25× |
| 1h cache write | 2× |
| Cache read | 0.1× |

Break-even on a reused prefix: 2 calls. Compounds from there.

## Cache hierarchy + invalidation

Levels: `tools → system → messages`. Change at any level invalidates that level AND all below.

| Change | Invalidates |
|---|---|
| Tool definitions | EVERYTHING |
| Web search / citations / speed toggle | system + messages |
| `tool_choice` change | messages |
| Images added/removed | messages |
| Thinking parameters | messages |

## Patterns

### Stable system prompt (the common case)

```python
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=2048,
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ],
    messages=[{"role": "user", "content": user_input}],
)
```

### Stable system + per-call appendix (e.g., locale directive)

Cache the stable block. Append uncached blocks AFTER the cache marker so per-call variation doesn't invalidate.

```python
system_blocks = [
    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": locale_directive(lang)},
]
```

### Large document + many questions

Cache the doc on the user message, not the question.

```python
messages=[{
    "role": "user",
    "content": [
        {"type": "text", "text": document_text, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": question},
    ],
}]
```

### Tools

`cache_control` on the LAST tool caches the entire tools block.

```python
tools = [
    {"name": "search", "description": "...", "input_schema": "..."},
    {"name": "fetch", "description": "...", "input_schema": "...",
     "cache_control": {"type": "ephemeral"}},
]
```

### 1-hour TTL for bursty cadence

```python
"cache_control": {"type": "ephemeral", "ttl": "1h"}
```

Use when calls cluster in bursts > 5 min apart (operator backlog catch-up, daily cron, multi-stage agent flows). 2× write cost, but worth it when default 5m would expire between calls.

### Pre-warming

Load cache before users arrive: `max_tokens=0`, dummy user message, normal system. Cache populates; the real request reads it.

## Verification (REQUIRED on first deploy)

Read `usage.cache_read_input_tokens` and `usage.cache_creation_input_tokens` off the response.

- First call within TTL: `write > 0, read = 0`
- Second call within TTL: `write = 0, read > 0`
- Second call writes too → prefix is varying per call. Audit it.

If you ship a Claude router, log cache metrics on every API call so cron logs can confirm caching fires on repeats.

For TypeScript / Anthropic Node SDK, `response.usage.cache_read_input_tokens` and `response.usage.cache_creation_input_tokens` are surfaced the same way.

## Router pattern: cache-on by default

The shipped `_claude_router.py` (in `scripts/`) exposes `cache_system: bool = True`. Set False ONLY when the caller varies the system prompt per call (benchmarks, evals, model sweeps, A/B tests on the prompt itself).

```python
text = call_claude_text(system=PROMPT, user=q, model="haiku")
text = call_claude_text(system=variant, user=q, cache_system=False)
```

First call is cached by default. Second call opts out, e.g. for a benchmark.

## N x M reviews: iterate doc-outer, column-inner

For tabular-review style work (N columns × M documents = N×M LLM calls) the cache architecture is:

- `system` block: cached, stable across the entire review (1 write, N×M−1 reads)
- `user[0]` text block: document_text, cached PER DOCUMENT (M writes, M×(N−1) reads)
- `user[1]` text block: per-column directive + JSON reply ask, varies per column (no cache)

This only works with `for document in documents: for column in columns:` iteration. The reverse order (column-outer) invalidates the document cache on every iteration because the document varies in the inner loop. Always iterate doc-outer. Break-even on per-document caching: N ≥ 2 columns (i.e. every real review).

If your runtime assembles the prompt server-side, return the parts separately so the client can apply `cache_control` to each layer. Example response shape:

```json
{
  "prompt": "<full assembled string, deprecated for new code>",
  "system": "<stable instruction template, cache anchor>",
  "column_directive": "<question + format suffix, varies per column>",
  "document_text": "<echoed back so clients don't have to track>"
}
```

Keep the legacy `prompt` field so old clients keep working until they migrate.

## New-code rule (enforced by hookify)

Any new file that imports `anthropic.Anthropic` / calls `messages.create` / imports `@anthropic-ai/sdk` ships with `cache_control` on the system block from the start.

The shipped hookify rule `warn-claude-call-without-cache` (in `templates/hookify-rules/`) warns on file edits matching the pattern. Override path: pass `cache_system=False` (router) or add a comment `# no-cache: <reason>` (direct call) so future audits know the omission was deliberate.

Bypass for unusual cases: `PROMPT_CACHE_RULE_BYPASS=1` on the failing tool call. Never weaken the regex.
