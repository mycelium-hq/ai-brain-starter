# Influencer pack: typed-memory categories

Twelve categories ship with the influencer pack. Each category lists the required frontmatter that the substrate enforces at write time, plus optional frontmatter that downstream queries depend on.

A document that does not match its declared category schema is rejected at write time and surfaced as a recoverable error to the operator.

The final three categories (`content-idea`, `idea-discard`, `taste-profile`) back the idea engine, the pack's content-generation spine. See `idea-engine/mechanism.md`.

## audience-segment

A cohort of engaged followers grouped by topic, geography, or platform. The unit of analysis for content-engine targeting and voice-fingerprint relevance scoring.

```yaml
type: audience-segment
segment_id: required, unique within tenant
segment_name: required, human-readable
platform: required, one of [instagram, tiktok, youtube, substack, x, linkedin, patreon, multi]
size_estimate: required, integer (engaged followers, not raw count)
engagement_rate: optional, float between 0 and 1
top_topics: required, list of topic tags
geography_breakdown: optional, ISO 3166 country codes with percent split
age_breakdown: optional, age-bucket percent split
created_date: required, ISO 8601
last_refreshed: required, ISO 8601 (segment definitions go stale)
```

## dm-conversation

Every direct-message thread with intent classification and current status. Includes IG DMs, TikTok DMs, Substack chat, X DMs, LinkedIn messages, YouTube comments tagged for triage, and live stream chat.

```yaml
type: dm-conversation
conversation_id: required, unique within tenant
platform: required, one of [instagram, tiktok, substack, x, linkedin, youtube-comment, youtube-live-chat, other]
contact_handle: required
contact_display_name: optional
intent: required, one of [fan, prospect, brand-collab, creator-collab, support, spam]
status: required, one of [open, replied, escalated, closed]
opened_date: required, ISO 8601
last_message_date: required, ISO 8601
last_message_direction: required, one of [inbound, outbound]
priority: optional, one of [low, normal, high, vip]
linked_collab: optional, FK to collab-deal
linked_creator_revenue: optional, FK to creator-revenue
```

## content-piece

Every published unit of content the creator has shipped. One row per Reel, Story, post, newsletter issue, podcast episode, video, short, tweet thread, LinkedIn post.

```yaml
type: content-piece
content_id: required, unique within tenant
platform: required, one of [instagram-reel, instagram-story, instagram-post, tiktok, youtube-video, youtube-short, substack, x-post, x-thread, linkedin-post, podcast-episode, other]
title: required, human-readable
published_date: required, ISO 8601
published_url: required when public
duration_seconds: optional (video and audio formats)
view_count: optional, integer (refreshed by /weekly-creator-report)
engagement_count: optional, integer (likes plus comments plus shares)
revenue_attributed: optional, USD float (for sponsored or affiliate content)
voice_fit_score: optional, float between 0 and 1 (from /voice-fingerprint scoring)
linked_audience_segments: optional, list of segment_id FKs
linked_collab: optional, FK to collab-deal (when piece is sponsored)
content_pillar: optional, one of [anchor, ai-enhanced, trend, sponsored, personal]
```

## collab-deal

Brand sponsorships and creator-to-creator collaborations with stage, terms, and deliverables.

```yaml
type: collab-deal
deal_id: required, unique within tenant
deal_type: required, one of [brand-sponsor, creator-collab, affiliate, ambassador, ugc, other]
counterparty_name: required (brand or creator handle)
counterparty_contact: required, email or platform handle
stage: required, one of [inbound-pending, qualified, negotiating, signed, in-delivery, delivered, paid, declined, ghosted]
total_value_usd: optional, float (sum across cash + product + pauta)
cash_component_usd: optional, float
product_component_usd: optional, float (estimated retail value of any product comp)
pauta_component_usd: optional, float (audience-side promotion or barter value)
deliverables: required, list of deliverable strings (e.g. "1 Reel + 2 Stories + 1 newsletter mention")
deadline: optional, ISO 8601
disclosure_required: required, boolean (FTC, ASA, ASCI per jurisdiction)
linked_content: optional, list of content_id FKs (the actual published pieces)
opened_date: required, ISO 8601
closed_date: optional, ISO 8601
```

## creator-revenue

Income line-items across all monetization paths. Designed to roll up into the weekly report and the year-end tax pull.

```yaml
type: creator-revenue
revenue_id: required, unique within tenant
revenue_source: required, one of [sponsorship, subscription, product, course, speaking, affiliate, ad-share, donation, other]
amount_usd: required, float
received_date: required, ISO 8601
linked_collab: optional, FK to collab-deal (when sponsorship)
linked_content: optional, list of content_id FKs (when content-attributed)
platform: optional (e.g. "stripe", "patreon", "stan-store", "youtube-adsense")
counterparty: optional (brand name, customer name, platform name)
tax_category: optional, one of [self-employment, royalty, gift, capital-gain, other]
notes: optional
```

## voice-fingerprint

The creator's actual written-voice patterns extracted from approved content. Used by every content-generation skill to anchor the rewrite.

```yaml
type: voice-fingerprint
fingerprint_id: required, unique within tenant (typically one active per creator)
trained_on_corpus: required, list of content_id FKs that fed the training pass
trained_date: required, ISO 8601
sentence_length_distribution: required (mean, median, p90 word counts)
top_n_words: required, ranked list with frequencies
sentence_starters: required, ranked list of opening n-grams
quirks: optional, list of phrases the creator uses that the rule library would otherwise strip
language_codes: required, list of ISO 639 codes the fingerprint covers
```

## voice-fingerprint-audio

Optional. The creator's encrypted spoken-voice fingerprint for TTS narration.

```yaml
type: voice-fingerprint-audio
audio_fingerprint_id: required, unique within tenant
encrypted_blob_path: required (file path to .voicedna.enc, creator-owned password)
provider: required, one of [voicedna, cartesia, elevenlabs, other]
trained_on_audio: required, list of audio file paths or URLs that fed the model
trained_date: required, ISO 8601
language_codes: required, list of ISO 639 codes
status: required, one of [active, deprecated, revoked]
revoked_date: optional, ISO 8601
revoked_reason: optional
```

## audience-question

Recurring questions surfaced from DMs, comments, community channels, email, and form submissions. The signal that drives content-roadmap and FAQ generation.

```yaml
type: audience-question
question_id: required, unique within tenant
canonical_question: required, human-readable single-sentence
source_count: required, integer (how many separate audience surfaces have asked this)
sources: required, list of FKs (dm-conversation, content-piece comments, form submissions)
first_seen_date: required, ISO 8601
last_seen_date: required, ISO 8601
status: required, one of [open, content-planned, content-published, archived]
linked_content: optional, FK to content-piece that addresses it
```

## content-source

External content the creator has ingested for research, reference, or repurposing input. NOT the creator's own published work (that is `content-piece`).

```yaml
type: content-source
source_id: required, unique within tenant
source_url: required
source_platform: required, one of [youtube, podcast, substack, blog, book, paper, other]
title: required
author: optional
ingested_date: required, ISO 8601
language: required, ISO 639 code
transcript_word_count: required, integer
why_kept: required, one of [reference, inspiration, competitive-analysis, repurposing-input, fact-check]
linked_content: optional, list of content_id FKs (when this source informed a published piece)
```

## content-idea

A single generated content idea: one proposed Reel, carousel, video, or newsletter, grounded in real audience evidence. The output unit of the idea engine. Every `content-idea` must trace to at least one real audience record; an idea with no evidence is rejected at write time (see `decision-audit/evidence-grounding.md`).

```yaml
type: content-idea
idea_id: required, unique within tenant
generated_date: required, ISO 8601
batch_id: required (groups every idea emitted by one generation run)
source_bucket: required, one of [audience-comments, audience-dms, top-content]
platforms: required, list, subset of [instagram, tiktok, youtube, substack, x, linkedin]
angle: required, one-line thesis of the idea (no raw IDs or hashes in this field)
format: required, one of [reel, carousel, image-post, story, short, long-video, newsletter, thread, post]
evidence_quotes: required, non-empty list of verbatim quotes from real audience records
why_good: required, 1-2 sentences (the pain, curiosity, or segment the idea serves)
suggested_angle: required, hook + body focus + close (the angle, not a full script)
basis_content_ids: optional, list of content-piece FKs
basis_conversation_ids: optional, list of dm-conversation FKs
basis_question_ids: optional, list of audience-question FKs
status: required, one of [proposed, accepted, discarded, published]
linked_content: optional, FK to content-piece once the idea is published
```

At least one of `basis_content_ids`, `basis_conversation_ids`, `basis_question_ids` must be non-empty, and `evidence_quotes` must be non-empty. The substrate rejects a `content-idea` that fails either condition. This is the evidence-grounding invariant; the enforcing pattern is `decision-audit/evidence-grounding.md`.

## idea-discard

The record of a creator rejecting a generated idea, with the reason. The idea engine's learning signal: every discard feeds the `taste-profile` recompute so future generations stop proposing what the creator keeps rejecting.

```yaml
type: idea-discard
discard_id: required, unique within tenant
idea_id: required, FK to content-idea
discarded_date: required, ISO 8601
reason_code: required, one of [topic-covered, not-interested, too-basic, off-voice, wrong-format, other]
reason_note: optional, free text the creator adds
angle_snapshot: required (the discarded idea's angle, frozen so the signal survives if the content-idea record is later archived)
source_bucket: required (frozen from the discarded idea)
platform: required (frozen from the discarded idea)
```

`angle_snapshot`, `source_bucket`, and `platform` are copied (frozen) onto the discard record rather than read through the FK, so the learning signal survives independently of the `content-idea` it came from.

## taste-profile

The compounding model of one creator's idea preferences, recomputed from their accumulated `idea-discard` and accepted `content-idea` records. This is what makes the idea engine learn: a weighted, confidence-scored model, not a rolling list of recent rejections. Distinct from `voice-fingerprint`, which models how the creator *writes*; this models what the creator wants to *make*.

```yaml
type: taste-profile
profile_id: required, unique within tenant (one active profile per creator)
updated_date: required, ISO 8601
discards_observed: required, integer (count of idea-discard records folded into this profile)
accepts_observed: required, integer (count of accepted or published content-idea records folded in)
rejected_angles: required, list of {pattern, weight, confidence} entries
rejected_formats: required, list of {format, weight, confidence} entries
rejected_topics: required, list of {topic, weight, confidence} entries
preferred_angles: required, list of {pattern, weight, confidence} entries
preferred_formats: required, list of {format, weight, confidence} entries
preferred_topics: required, list of {topic, weight, confidence} entries
recompute_basis: required, list of idea-discard and content-idea FKs folded in the most recent recompute
```

`weight` is how strongly a signal recurs (0 to 1); `confidence` scales with how many observations support it, so a profile built on 6 discards is correctly treated as weaker than one built on 200. The recompute cadence and the weighting math are in `idea-engine/mechanism.md`.
