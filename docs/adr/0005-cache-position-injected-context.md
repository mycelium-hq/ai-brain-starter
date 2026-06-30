---
status: accepted
date: 2026-06-30
---

# 0005 - Cache-position the per-message injected context (`once` is dead in settings.json)

## Context

UserPromptSubmit (UPS) hooks inject `additionalContext` into the model's context.
A footprint audit (MYC-2348 Stage 0) found the substrate re-injecting stable,
prompt-independent blocks on **every message** - a recurring paid-inference cost
plus context-budget burn that compounds at scale. The content is VALUE
(project-scoped instincts, session-start guidance), so the fix is cache
*positioning*, not removal.

Two substrate hooks carried `"once": true` in the root `hooks.json`, intending
"inject once per session": `session-start-context.py` (the SESSION-START guidance
block) and `inject-instinct-context.py` (the high-confidence instinct list, whose
selection is purely project-scoped - it discards the prompt).

**The surprise that drove this ADR:** `once` is **ignored in settings.json**.
Per the Claude Code hooks doc, verbatim: *"`once` - If true, runs once per session
then is removed. Only honored for hooks declared in skill frontmatter; ignored in
settings files and agent frontmatter."* The installer
(`install-hooks-user-level.py`) merges this `hooks.json` into
`~/.claude/settings.json` - exactly where `once` is dead. So both hooks fired on
**every** UPS. Firsthand transcript proof (one real session): the instinct block
was injected **14x** and the session-start block **17x** as
`hook_additional_context` attachments with `hookEvent: UserPromptSubmit` - once per
user prompt, every message. SessionStart, by contrast, fired **7x** = once per
session-segment (startup + resumes/compactions).

A hook author cannot set `cache_control` - the Claude Code harness owns the API
request structure. What the substrate CAN control is **which event injects**:
SessionStart fires once per session-segment and lands its `additionalContext` in
the stable prefix (the prefix the cache covers - that same session showed 374/400
turns served from cache, peak 711K cache-read tokens). UPS injects into the
per-turn tail, which is fresh every message.

This also revised a premise of [ADR 0004](0004-footprint-sla-gate.md): its fan-out
gate *excluded* `once: true` entries from the per-message count ("they fire once
per session"). In settings.json they don't - so the gate undercounted.

## Decision

1. **Move the two stable injectors UPS -> SessionStart.** They emit
   `hookEventName: "SessionStart"` and are wired in the SessionStart block. They now
   fire once per session-segment (startup / resume / post-compact - re-seeded after
   a compaction, never re-paid per message), landing in the cached prefix. Their
   per-message marginal cost becomes a cache-read, not a fresh injection. `once` is
   dropped (a SessionStart hook is once-per-segment by the event's nature).

2. **Correct the SLA gate's `once` handling.** `once: true` no longer discounts the
   fan-out (it is dead in settings.json). A `once: true` anywhere in the
   settings-merged `hooks.json` is a **hard breach** (axis E): it silently makes a
   "once-per-session" hook re-fire every event. The fix the breach demands is this
   ADR's move (to SessionStart) or dropping the no-op flag.

3. **Implement axis D (per-message injected tokens).** `--measure --execute`
   executes each UPS substrate hook with a NEUTRAL prompt in a sandboxed HOME and
   sums emitted `additionalContext` tokens (~bytes/4) vs a fixed advisory ceiling
   (`injected_tokens_per_message`, default 100). A conditional hook emits nothing on
   a neutral prompt (-> 0); an unconditional stable injector shows its full block -
   the signal that it belongs on SessionStart. Real-fleet number is
   install/runner-dependent -> advisory; the LOGIC is gated deterministically by
   `--selftest` pos/neg synthetic controls (an unconditional injector scores high, a
   conditional one scores 0).

## Why

- Moving the injectors is the only substrate-level lever for cache position (the
  harness owns `cache_control`), and it is also semantically correct: this content
  IS session-start content (one hook is literally `session-start-context.py`).
- The gate must measure reality. Trusting a flag the harness ignores made a
  just-shipped gate undercount the exact cost this work targets. Counting `once` +
  flagging it as a dead-flag breach makes the gate honest and kills the bug class
  (you cannot wire a dead-`once` hook without the gate forcing the conversation).
- Axis D stays advisory (per ADR 0004: execution is flaky/install-specific and CI
  must not execute the real fleet), but its LOGIC is now real and CI-gated via
  selftest controls - no longer a stub that prints "needs a vault".

## Consequences

- Per-message injected tokens from the substrate's UPS injectors: measured **0**
  after the move (every remaining UPS substrate hook is prompt-conditional). The
  instinct + session-start blocks are paid once per segment and cache-read within
  it, not re-billed per prompt.
- Salience is preserved: SessionStart content stays in the context window for every
  prompt in the segment (it is in the prefix) - it is just not duplicated 14-17x.
- A future hook that injects a stable block every message (UPS + unconditional, or
  any `once: true`) turns CI red - the intended ratchet.
- Reversal (moving them back to UPS) re-opens the recurring-injection waste; the
  test_footprint_sla.sh section-6 guard + the axis-E breach prevent it silently.
- Founder-personal `~/.claude` UPS injectors (e.g. a CONTEXT.md auto-loader) exhibit
  the same class but are NOT in this public substrate - out of scope here.
