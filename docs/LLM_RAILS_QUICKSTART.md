## LLM Rails Quickstart

A teaching pack for AI coding agents shipping production LLM features. Distills six patterns from [NVIDIA-NeMo/Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) (Apache-2.0) into a five-rail taxonomy + concrete code snippets you can adopt today without taking on a framework dependency.

**Who this is for:** you (or your AI coding agent) are about to ship code that calls Anthropic / OpenAI / NVIDIA / local LLMs from production. Maybe a chatbot, maybe a workflow, maybe a webhook handler. You need the safety surface explicit, the observability surface explicit, and you need it shippable in one or two commits.

**Who this is NOT for:** if you want a full framework with a DSL and a unified runtime, install NeMo Guardrails directly — `pip install nemoguardrails`. This doc is for the case where you want the principles without the framework weight.

---

## The five-rail taxonomy

Every LLM-calling surface ships rails at five stages:

| Stage | When | Common use cases |
|---|---|---|
| **Input rails** | Before LLM is called | Content safety, jailbreak detection, topic control, PII masking |
| **Retrieval rails** | After RAG retrieval, before context assembly | Document filter, chunk validation, source allowlist |
| **Dialog rails** | Across turns in a multi-turn conversation | Flow control, guided conversations, canonical-form routing |
| **Execution rails** | Around tool/function calls | Action input/output validation, allowlist on tool args |
| **Output rails** | After LLM response, before user sees it | Response filter, fact-check, sensitive data removal |

**Input + Output rails are the most common** and cover ~80% of safety surface. Retrieval rails only apply with a RAG pipeline. Dialog rails only apply to multi-turn conversational agents. Execution rails only apply when the agent invokes tools/functions.

**Audit your surface against the matrix.** If any applicable rail is empty, that's a defect. Name the gap, file an issue, ship the rail.

---

## Pattern 1: Three-mode action taxonomy

When a scanner fires, the action MUST be one of three first-class modes, chosen per-surface in config:

- **REJECT** — block downstream processing. Surface for human review. DEFAULT for auto-draft / auto-reply.
- **OMIT** — strip the detected portion in place. Pass the cleaned remainder. Use when injection is bounded and legitimate content around it is high-value.
- **SANITIZE** — rewrite the detected portion to neutralized form. Highest cost (small-model rewrite pass). Use only when REJECT + OMIT both kill business value.

Adopted from NeMo Guardrails `nemoguardrails/library/injection_detection/yara_config.py`:

```python
from enum import Enum

class ActionOptions(Enum):
    REJECT = "reject"
    OMIT = "omit"
    SANITIZE = "sanitize"
```

Wiring rule: scanner returns `{is_violation: bool, text: str, detections: list[str]}`. The action mode lives in surface config, not in the scanner. Same scanner → different actions per surface.

---

## Pattern 2: Inversion-safety via output_mapping

Every scanner / verifier MUST declare HOW its raw output maps to the binary "should we block?" decision, AT the scanner definition site, not at the call site. The classic bug is a scanner returning "YES = injection" wired to a downstream check that reads "YES = safe to proceed" — same word, opposite semantics, silent failure.

Adopted from NeMo's `@action` decorator pattern. Verbatim from `nemoguardrails/library/self_check/output_check/actions.py`:

```python
@action(is_system_action=True, output_mapping=lambda value: not value)
async def self_check_output(...):
    ...
    return is_safe  # raw output: True = safe
    # output_mapping inverts: rail blocks when mapping returns True
    # so `not is_safe` = block when unsafe → correct
```

For non-decorator setups (most production code), annotate via docstring:

```python
def scan_for_injection(body: str) -> bool:
    """Return True if injection detected.

    output_mapping: identity — True from this function = block.
    Polarity: prompt instructs the model to return YES on injection;
    parse_yes_no inverts text→bool with YES→True. Therefore the raw
    model output and the block decision share polarity.
    """
```

Code review checks this line exists and matches the prompt's polarity. Inversion bugs are silent — the discipline is the only guard.

---

## Pattern 3: Self-consistency hallucination check

For high-stakes generations (legal, medical, financial advice, factual claims), run the same prompt N times at temperature=1.0 and vote. NeMo's canonical implementation from `nemoguardrails/library/hallucination/actions.py`:

```python
HALLUCINATION_NUM_EXTRA_RESPONSES = 2

# Use beam search with n=N when provider supports it (OpenAI, NVIDIA NIM).
# Cheaper than N serial calls — one TTFT, N completions.
configured_chain = chain.with_config(
    configurable={"temperature": 1.0, "n": num_responses}
)
extra_llm_response = await configured_chain.agenerate(...)
```

Implementation rules:

1. **Use single LLM call with `n=N` when provider supports it.** Cheaper than N serial calls.
2. **Temperature = 1.0 for the resample set**, NOT 0.0. Higher entropy forces divergence if uncertain; temperature 0 makes the resample identical and defeats the check.
3. **Compare resamples against the original at temperature 0**, not against each other. Original is "claim under test"; resamples are "evidence."
4. **Same post-processing as the generation pass.** If the generator does multi-line cleanup, the resamples must too — otherwise format diffs masquerade as content diffs and trigger false positives.
5. **`n=2` is the MINIMUM that produces a useful vote signal** (NeMo's default). When budget is tight, `N=3` is the floor; `N=5` is the production target.

When the provider does NOT support `n=N` (Anthropic SDK doesn't expose it), the fallback is N serial calls at temperature 1.0. Cost scales linearly; for high-frequency surfaces this is the bottleneck that motivates Pattern 4.

---

## Pattern 4: YARA signature-scan prefilter

LLM scanners cost real money and add real latency. For known-pattern injection (XSS, SQLi, template injection, code injection), compiled signature scanning is ~0ms with $0 marginal cost. Use YARA as a prefilter BEFORE the LLM scanner.

Install:

```bash
brew install yara  # macOS; apt install yara on Debian/Ubuntu
pip install yara-python
```

NeMo's default rule categories (vendor verbatim, Apache-2.0): `code.yara`, `sqli.yara`, `template.yara`, `xss.yara` at `nemoguardrails/library/injection_detection/yara_rules/`.

```python
import yara
from functools import lru_cache

@lru_cache
def _load_yara_rules():
    return yara.compile(filepaths={
        "code": "yara_rules/code.yara",
        "sqli": "yara_rules/sqli.yara",
        "template": "yara_rules/template.yara",
        "xss": "yara_rules/xss.yara",
    })

def scan_for_injection(text: str, call_llm_scanner) -> dict:
    """Returns {is_injection, text, detections}.

    output_mapping: identity — is_injection=True means block.
    """
    rules = _load_yara_rules()
    matches = rules.match(data=text)
    if matches:
        return {
            "is_injection": True,
            "text": text,
            "detections": [m.rule for m in matches],
        }
    # YARA didn't match — fall through to expensive LLM scanner
    return call_llm_scanner(text)
```

Measure hit-rate before declaring success. Target: >50% of triggered scans short-circuit at YARA layer. If hit-rate is low, the prefilter is dead weight and you revert.

**Gotcha:** yara-python is a C++ binding with platform-dependent install. Production deploys (Docker, Vercel, Fly.io) need yara installed in the build image, not just at dev time.

---

## Pattern 5: OpenTelemetry GenAI semconv

Every production LLM-calling surface emits OpenTelemetry traces using the GenAI semantic conventions. Standard attribute keys = compatible with every OT-native ingestor (Jaeger, Honeycomb, Grafana Tempo, Datadog, Phoenix Arize) without per-service mapping.

Standard attributes:

| Attribute | Required? | Example |
|---|---|---|
| `gen_ai.system` | yes | `"anthropic"`, `"openai"`, `"nvidia"` |
| `gen_ai.request.model` | yes | `"claude-sonnet-4-6"`, `"gpt-4o"` |
| `gen_ai.usage.input_tokens` | yes | `1542` |
| `gen_ai.usage.output_tokens` | yes | `218` |
| `gen_ai.response.id` | yes if provider returns one | `"msg_abc123"` |
| `gen_ai.response.finish_reasons` | yes | `["stop"]`, `["max_tokens"]` |
| `gen_ai.usage.cache_read_input_tokens` | yes when prompt caching enabled | `1200` |
| `gen_ai.usage.cache_creation_input_tokens` | yes when caching | `342` |

**Banned attribute keys** (would collide with semconv or carry content): `prompt`, `response`, `messages`, `system_prompt`, `user_message`, `bot_message`. Content goes in span EVENTS (off by default), never in attributes.

Python reference impl:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource

# Configure ONCE at process entrypoint
resource = Resource.create({"service.name": "my-llm-service"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

def call_with_trace(prompt: str, system: str) -> str:
    with tracer.start_as_current_span("chat claude-sonnet-4-6") as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", "claude-sonnet-4-6")
        # NEVER: span.set_attribute("prompt", prompt) — content not in attrs
        resp = client.messages.create(...)
        span.set_attribute("gen_ai.response.id", resp.id)
        span.set_attribute("gen_ai.usage.input_tokens", resp.usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", resp.usage.output_tokens)
        span.set_attribute(
            "gen_ai.usage.cache_read_input_tokens",
            resp.usage.cache_read_input_tokens or 0,
        )
        span.set_attribute(
            "gen_ai.usage.cache_creation_input_tokens",
            resp.usage.cache_creation_input_tokens or 0,
        )
        span.set_attribute("gen_ai.response.finish_reasons", [resp.stop_reason])
        return resp.content[0].text
```

TypeScript reference impl:

```typescript
import { trace } from "@opentelemetry/api";
const tracer = trace.getTracer("my-llm-service");

await tracer.startActiveSpan("chat claude-sonnet-4-6", async (span) => {
  span.setAttribute("gen_ai.system", "anthropic");
  span.setAttribute("gen_ai.request.model", "claude-sonnet-4-6");
  const resp = await client.messages.create(...);
  span.setAttribute("gen_ai.usage.input_tokens", resp.usage.input_tokens);
  span.setAttribute("gen_ai.usage.output_tokens", resp.usage.output_tokens);
  span.end();
});
```

Rail spans nest the same way:

```python
with tracer.start_as_current_span("rail.input.injection_scan") as rail_span:
    result = scan_for_injection(body)
    rail_span.set_attribute("rail.action", "reject" if result["is_injection"] else "pass")
    rail_span.set_attribute("rail.detections", result["detections"])
    if result["is_injection"]:
        return "blocked"

with tracer.start_as_current_span("chat claude-sonnet-4-6"):
    # LLM call as above
```

---

## Pattern 6: Content-capture off by default

```yaml
tracing:
  enabled: true
  span_format: "opentelemetry"
  enable_content_capture: false  # default
```

Reason: span attributes are typically retained ≥30 days in ingestors and shared across teams; prompt content + response content can carry PII, secrets, IP, voice samples. Default-off for content prevents leakage into ingestor.

Per-surface, per-environment override:

1. **NEVER in production by default.** Dev environments only. Production override requires an explicit decision log entry + auditor + 30-day TTL + DLP filter on the ingestor side.
2. **Captured content is span EVENTS, not span ATTRIBUTES.** Events have separate retention controls in most ingestors; attributes are indexed and shared.
3. **Redaction at emit time, not ingestor time.** Strip patterns like `key=`, `token=`, `secret=`, `password=`, `Bearer <token>` before emit. Belt-and-suspenders: sanitize-emit AND sanitize-ingest.

---

## Coverage matrix (audit template)

Use this matrix to score your surface BEFORE shipping. Any P0/P1 gap = file an issue and ship the rail.

| Surface | INPUT | RETRIEVAL | DIALOG | EXECUTION | OUTPUT |
|---|:---:|:---:|:---:|:---:|:---:|
| `<your surface 1>` | ? | ? | ? | ? | ? |
| `<your surface 2>` | ? | ? | ? | ? | ? |

Mark each cell ✅ (rail wired), ⚠️ (informal but no formal rail), ❌ (no rail), `n/a` (stage doesn't apply to this surface).

---

## What to do NEXT

1. Score your LLM-calling surfaces against the five-rail matrix.
2. For each `❌` cell at P0/P1 priority, file a ticket.
3. Ship the simplest rail that closes the gap. REJECT mode is the safest default.
4. Wire OpenTelemetry from day 1, even if you haven't picked an ingestor yet — the wire format is universal.
5. Measure: did the rail fire? Did it block what it should have? Did it block what it shouldn't have? Iterate on the prompt / signatures / config based on real fire data.

---

## Source attribution

Patterns adopted from [NVIDIA-NeMo/Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) (Apache-2.0). YARA rules and code snippets cited verbatim where indicated; SPDX header preserved per Apache-2.0 attribution requirement.

For the full framework experience (Colang DSL + 26 vendor integrations + unified runtime), install `nemoguardrails` directly. This quickstart is for the case where you want the principles without the framework weight.
