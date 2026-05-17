# Idea engine: mechanism

The idea engine is the influencer pack's content-generation spine. It proposes new content ideas to the creator, and it does two things a generic AI idea generator does not:

1. **Every idea is grounded in real audience evidence.** No proposed idea exists without a verbatim quote from a real comment, DM, or piece of the creator's own content behind it. The enforcing pattern is `decision-audit/evidence-grounding.md`.
2. **The engine learns the creator's taste.** Every idea the creator discards is logged with a reason and folded into a compounding `taste-profile`. Later generations read that profile and stop proposing what the creator keeps rejecting.

The engine reads from the typed-memory layer (`content-piece`, `dm-conversation`, `audience-question`) and writes `content-idea`, `idea-discard`, and `taste-profile` records back to it.

## The three buckets

Every generation run produces ideas in three buckets, because the three source surfaces carry different signal:

| Bucket | Source | What it surfaces |
|---|---|---|
| `audience-comments` | `dm-conversation` records with `subtype: comment`, plus `audience-question` | Recurring public questions and reactions, what the audience asks out loud |
| `audience-dms` | `dm-conversation` records (direct messages) | Private, higher-intent questions the audience will not ask in public |
| `top-content` | `content-piece` records ranked by engagement | What already worked; ideas are evolutions, not repeats |

A bucket can come back with fewer ideas than its target, or empty. Quality is the gate, not the count. An empty bucket is a valid result; a padded bucket is a defect.

## Generation flow

One generation run, per platform:

1. **Pull** the bucket sources from the typed-memory layer for the lookback window.
2. **Pre-filter** the comment and DM text through the noise filter (`idea-engine/pre-filter.md`) so adoration, bot, and trivial messages never reach the model. This is a cost control and a signal control.
3. **Group into patterns.** The model reads the full filtered set and groups it by recurring theme. Three differently-worded versions of the same question are one pattern, one idea, not three.
4. **Ground each idea in evidence.** Each candidate idea must carry at least one verbatim quote and at least one basis FK to the real record it came from. A candidate that cannot cite real evidence is dropped, not softened.
5. **Emit `content-idea` records** in the three-block shape below.
6. **Apply the taste profile.** The creator's current `taste-profile` is passed into the run; the model suppresses angles, formats, and topics the profile marks as rejected.

### The three-block idea shape

Every `content-idea` carries three blocks the creator can scan in seconds:

- **Evidence:** the verbatim quotes from real comments, DMs, or captions that motivated the idea.
- **Why it is good:** one or two sentences naming the pain, curiosity, or audience segment it serves.
- **Suggested angle:** hook, body focus, and close. The angle, not a finished script. The creator writes the script in their own voice.

## Evidence grounding

The engine is forbidden from inventing audience demand. Every `content-idea` is rejected at write time unless it carries a non-empty `evidence_quotes` list and at least one `basis_*` FK to a real record. Raw IDs and hashes are never written into human-facing text fields; an ID-strip backstop removes any that leak. The full rule, the write-time gate, and the audit trail are in `decision-audit/evidence-grounding.md`.

This is the difference between a tool the creator trusts and one that quietly hallucinates what the audience wants.

## The discard loop

When the creator rejects a proposed idea:

1. The engine writes an `idea-discard` record with the rejection `reason_code`, an optional note, and a frozen snapshot of the idea's angle, bucket, platform, and format.
2. The source `content-idea` record's `status` is set to `discarded`.
3. The next generation run reads recent discards and the `taste-profile` (below). It does not re-propose a discarded idea or a near-variant of one.

The discard is not a thumbs-down that disappears. It is a durable, reasoned signal. `idea-discard` records are retained indefinitely (`retention/defaults.md`) precisely because they are the engine's training data.

## The compounding taste profile

A naive engine feeds the last N discards into the prompt as a "do not repeat" list. That is anti-repetition, not learning: it works at 50 discards and degrades into noise at 500.

The idea engine compounds discards into a structured `taste-profile` instead, a weighted, confidence-scored model of the creator's preferences, recomputed on a cadence rather than regrown every run.

**Recompute.** On a schedule (default weekly) and on demand, the engine reads the creator's accumulated `idea-discard` records and accepted or published `content-idea` records, and recomputes the `taste-profile`:

- Each recurring rejection theme becomes a `rejected_angles` / `rejected_formats` / `rejected_topics` entry. Each recurring acceptance theme becomes a `preferred_*` entry.
- `weight` (0 to 1) is how strongly the theme recurs across the observed set.
- `confidence` scales with the number of observations supporting the theme, so a profile built on 6 discards is correctly weaker than one built on 200, and the engine does not over-fit to a tiny sample.

**Use.** Each generation run takes the current `taste-profile` as input. High-weight, high-confidence `rejected_*` entries suppress matching candidates before they are emitted; `preferred_*` entries bias ranking. The profile is one record per creator, recomputed in place, not an ever-growing prompt.

This is what makes the engine improve with use, and it is the creator's switching cost: the profile is theirs, and a competitor's tool starts from zero taste data.

## Prompt-cache architecture

A generation run sends two context blocks to the model:

1. **Cacheable block** holds the large, stable context: the bucket sources (top content, transcripts, filtered comments and DMs), audience demographics, the creator's voice fingerprint. This block is marked cacheable so repeat runs in a session reuse it at no input cost.
2. **Non-cached block** holds the run instruction, the current `taste-profile`, and the recent `idea-discard` set.

The taste profile and the discards go in the **non-cached** block on purpose. They change every time the creator discards an idea. If they were in the cacheable block, every discard would invalidate the cache and the next run would pay full input cost. Keeping the volatile learning signal out of the cached block is what keeps the engine cheap to run at scale.

## Open-core boundary

This file specifies the *mechanism*: the buckets, the flow, the discard loop, the compounding-profile math, the cache layout. The mechanism is open; anyone can build the engine from this spec.

Three things are deliberately not in this repo:

- The **calibrated noise-filter corpora:** the per-market, per-language pattern libraries that make the pre-filter sharp. The substrate ships the filter *interface* and a generic seed (`idea-engine/pre-filter.md`); the calibrated corpora live in the runtime layer.
- The **calibrated generation prompt:** the tuned model instruction. The substrate specifies what it must do; the tuned text lives in the runtime layer.
- The **per-creator `taste-profile` data:** the creator's own accumulated preference data. It belongs to the creator and is hosted in their runtime, never published.

A generic build from this spec works. A build with calibrated corpora and a populated taste profile works better. The gap between the two is the runtime layer's job, not a gap in this spec.
