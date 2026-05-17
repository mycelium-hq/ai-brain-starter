# Idea engine: pre-filter

Before any comment or DM text reaches the generation model, the idea engine runs it through a noise filter. The filter does two jobs:

- **Cost control.** A creator with an engaged audience receives a large volume of low-substance messages — pure adoration, one-word reactions, automated funnel messages. Sending those to the model is paid input tokens for zero signal.
- **Signal control.** The model proposes better ideas when it reads substance, not noise. Adoration and bot text dilute the pattern-grouping step.

This file specifies the filter *interface* and the generic rule set. The calibrated, per-language pattern corpora that make the filter sharp are not in this repo — see "Open-core boundary" below.

## Interface

The filter exposes three predicates. A generation run calls them over every candidate comment and DM before the pattern-grouping step.

```
is_substantive_comment(text) -> bool
    True if the comment carries enough substance to inform an idea.

is_substantive_dm(text) -> bool
    True if the direct message carries enough substance to inform an idea.
    More permissive than the comment predicate (DMs are higher-intent by
    default) but adds an automated-message check.

is_likely_automated(text) -> bool
    True if the text looks machine-generated: funnel onboarding, keyword
    auto-replies, link-only or contact-only messages.
```

Text that fails its predicate is excluded from the generation context. It is not deleted from the typed-memory layer — the `dm-conversation` record stays; it is simply not passed to the model for this run.

## Generic rule set

The substrate ships this generic, language-agnostic seed. It is deliberately conservative — it drops only clear noise:

- **Drop** text that is only emoji or punctuation.
- **Drop** text that is only a URL, only an email address, or only a contact handle.
- **Drop** text that, after trimming generic praise tokens, has fewer than ~15 characters of remaining substance.
- **Keep** any text containing a question mark — a question is strong signal even when short.
- **Drop** text matching the automated-message rules (funnel-onboarding phrasing, keyword auto-reply triggers, "link in bio" style calls to action).

A run never drops a `content-piece` caption or transcript through this filter. The filter applies to *audience* text (comments, DMs), not the creator's own content.

## Calibration is per-creator

Two calibration inputs sharpen the filter beyond the generic seed, and both are gathered at install, not shipped in this repo:

- **Language and market corpora.** Adoration phrasing, praise tokens, and bot patterns are language- and market-specific. The generic seed catches obvious noise in any language; a corpus tuned to the creator's actual audience language catches far more.
- **The creator's own automation vocabulary.** If the creator runs a chatbot or a funnel, its stock phrases appear inside their own DM threads. The install step asks the creator for the names and stock phrases of their bots, courses, and funnels, and adds them to the automated-message rules so the engine does not mistake the creator's own funnel output for audience signal.

## Open-core boundary

The interface and the generic rule set above are open — they are the pattern, and they are enough to build a working filter.

The **calibrated corpora** — the per-language adoration and bot pattern libraries, and the per-creator automation vocabulary — are not in this repo. They are calibrated against real audience data, they are the difference between a filter that catches obvious noise and one that catches most of it, and they live in the runtime layer. See `idea-engine/mechanism.md` "Open-core boundary".
