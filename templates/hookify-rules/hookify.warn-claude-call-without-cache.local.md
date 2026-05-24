---
name: warn-claude-call-without-cache
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.(py|ts|tsx|mjs|js)$
  - field: new_text
    operator: regex_match
    pattern: (messages\.create\s*\(|messages\.stream\s*\(|@anthropic-ai/sdk|anthropic\.Anthropic\s*\(|new Anthropic\s*\()
---

**Anthropic Messages API call detected.** Per the prompt-caching rule (template at `templates/rules/prompt-caching.md`): every Claude-calling surface ships with `cache_control` on the system block from the start. Default ON, even when today's prefix is below the model minimum — the API silently no-ops if too small, so opt-in is free and future-proofs the surface.

**If you went through `_claude_router.py`** (or any wrapper that exposes a `cache_system` flag): caching is on by default. Nothing to do.

**If you're calling the SDK / API directly** (`client.messages.create(...)` or POST to `/v1/messages`): wrap the system prompt in a cache block.

Python:

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

TypeScript:

```ts
const response = await client.messages.create({
  model: MODEL,
  max_tokens: 2048,
  system: [
    { type: "text", text: SYSTEM_PROMPT, cache_control: { type: "ephemeral" } },
  ],
  messages: [{ role: "user", content: userContent }],
});
```

**Tools:** put `cache_control` on the LAST tool to cache the entire tools block.

**Verification:** read `response.usage.cache_read_input_tokens` and `cache_creation_input_tokens` on the first two calls. Second call within TTL should show `read > 0, write = 0`.

**Already-cached files don't need re-action** — this warn fires on any matching API call, including ones already caching. If you see the pattern + `cache_control` on the same block, ignore.

**Legitimate opt-out** (benchmark, model sweep, A/B prompt test): pass `cache_system=False` (router) or add a comment `# no-cache: <reason>` / `// no-cache: <reason>` next to the call so future audits know it was deliberate.

**Bypass for a one-off:** `PROMPT_CACHE_RULE_BYPASS=1` on the failing tool call. The rule itself stays on; never weaken the regex.

Pairs with `_claude_router.py` (`cache_system: bool = True` default) and the `prompt-caching.md` rule template. Together they push caching to ON by default for every new surface without requiring caller awareness.
