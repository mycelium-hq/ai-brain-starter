---
name: influencer-pack
description: Pre-configured creator-economy vertical pack for the ai-brain-starter substrate. Ships typed-memory categories for audience, DMs, content, collabs, and creator revenue; connector configs for Instagram, TikTok, YouTube, Substack, X, LinkedIn, Stan Store, Stripe, Patreon; retention defaults aligned with Meta + TikTok + YouTube data-handling expectations; decision-audit patterns for sponsored-disclosure and brand-deal terms. Use when onboarding a creator, personal-brand operator, or content-engine team that needs the substrate to come pre-shaped to the work rather than starting from a blank vault.
trigger: /influencer-pack
argument-hint: "init | status | rebuild [--platform <name>]"
---

# /influencer-pack

A pre-configured pack that turns the empty substrate into a creator-economy ready system in one install. The pack ships typed-memory categories that match how audience, content, DMs, and collabs actually move; connectors for the platforms creators already use; retention defaults that map to Meta and TikTok and YouTube data-handling expectations; and decision-audit patterns for sponsored-content disclosure and brand-deal terms.

## Why this exists

A blank install of the substrate forces every creator to invent the same vocabulary on day one: what is an audience segment, what is a DM intent, what is a collab stage, how do I attribute revenue across sponsorship + subscription + product + course + speaking + affiliate. The vocabulary is not novel. Creators run roughly the same primitives, against roughly the same set of platforms.

This pack ships the primitives so the creator can spend day one on what is actually theirs (their voice, their audience-relationship history, their content engine) instead of re-deriving the category structure.

## What this pack sets up

Run `/influencer-pack init` and the pack writes:

| Layer | What ships | Where it lands |
|---|---|---|
| Schema | 9 typed-memory categories with frontmatter contracts | `schema/typed-memory-categories.md` |
| Connectors | 16 platform connector specs (Instagram, TikTok, YouTube, Substack, X, LinkedIn, Stan Store, Stripe, Patreon, more) | `connectors/*.md` |
| Retention | Per-category retention defaults aligned with platform terms of service and creator-economy norms | `retention/defaults.md` |
| Decision audit | Sponsored-content disclosure pattern and brand-deal acceptance pattern | `decision-audit/*.md` |

Nothing is auto-applied to a live install. The pack stages drafts under `drafts/` and prints the path; the operator reviews and accepts before merging into the production memory layer.

## Required companion skills

The influencer-pack assumes these substrate skills are also installed in `~/.claude/skills/`. The connectors call into them directly. Install them alongside the pack:

| Companion skill | Purpose | Source |
|---|---|---|
| `ingest-youtube` | Pulls YouTube transcripts into the vault as queryable markdown so podcast appearances, video essays, and competitor analysis flow into the same typed-memory layer the rest of the pack queries. Required for the `/repurposing-engine` and `/voice-fingerprint-update` skills. | Bundled in this repo at `skills/ingest-youtube/` |
| `ingest-slack` | Pulls Slack channels (creator community, agency channel) into the vault for cross-platform context. | Bundled in this repo at `skills/ingest-slack/` |
| `humanizer` | Voice-fingerprint pass on AI-generated content drafts before publish so the creator's voice does not flatten across the engine output. | `https://github.com/adelaidasofia/humanizer` |
| `graphify` | Knowledge graph extraction across the typed-memory layer so the creator can see content + DMs + collabs as one navigable surface. | Bundled in this repo at `skills/graphify/` |

## Skill bundle (creator-facing commands)

| Skill | What it does | Trigger |
|---|---|---|
| `/dm-closer` | Drafts DM responses in the creator's tone, qualifies fan vs prospect vs brand-collab, escalates high-value contacts to manual review. | Always-on |
| `/content-engine` | Generates short-form posts (Reels, Shorts, TikToks) from anchor recordings plus AI b-roll plus trend formats. | Weekly batch |
| `/weekly-creator-report` | Monday-morning rollup: revenue by source, top content by reach plus revenue, audience growth, collab pipeline status. | Cron at 7am Monday |
| `/collab-pipeline` | Tracks inbound brand asks plus outbound creator-to-creator collabs with stage, terms, next-step. | Always-on |
| `/voice-fingerprint-update` | Re-trains the written-voice fingerprint on the last 30 days of approved content. Reads from `External Inputs/YouTube/` (via `ingest-youtube`), the Substack archive, and the IG caption history. | Monthly cron |
| `/repurposing-engine` | Turns a long-form recording (podcast, YouTube video, keynote) into platform-native cuts: short-form video, newsletter post, X thread, LinkedIn post. Reads transcripts from the typed-memory layer, which means `ingest-youtube` must run first on the source URL. | Per-recording |
| `/launch-automation` | Course or cohort or paid-product launch sequence with email plus DM plus Story plus Reel cadence. | Per-launch |

## Init flow

1. The operator runs `/influencer-pack init`.
2. The pack reads the existing substrate state and reports any conflicts (categories already defined, connectors already configured).
3. Drafts land at `drafts/<timestamp>/` under the pack root with the proposed schema, connector configs, and retention defaults.
4. The operator reviews the drafts. They can edit in place or run `/influencer-pack init --regenerate <file>` to redraft a single file.
5. When the operator accepts, the pack writes to the production memory layer and registers the companion skills as installed dependencies.

## Status check

`/influencer-pack status` reports:

- Which typed-memory categories are live versus draft
- Which connectors are configured versus pending
- Retention rules applied vs default
- Companion skill install state (`ingest-youtube`, `humanizer`, `graphify`)
- Most recent ingest run per connector
- Pending items in the creator's review queue (DMs, collab proposals, sponsored-content disclosures)

## Rebuild

`/influencer-pack rebuild --platform <name>` re-pulls the connector spec from the latest version in this repo, diffs against the local install, and stages an upgrade plan. Use after a major platform API change (Meta Graph version bumps, YouTube Data API revisions).

## Companion-skill detail: ingest-youtube

The `/repurposing-engine` and `/voice-fingerprint-update` skills both depend on YouTube transcripts being in the typed-memory layer. The flow:

1. Operator runs `/ingest-youtube <url>` (single video) or `/ingest-youtube <channel> --days N` (recent uploads).
2. `ingest-youtube` calls `yt-dlp`, cleans the VTT subtitle file, and writes `External Inputs/YouTube/<channel-slug>/<YYYY-MM-DD>-<video-slug>.md` with full transcript and metadata.
3. The next time `/voice-fingerprint-update` runs, it picks up the new transcripts and re-trains.
4. The next time `/repurposing-engine` runs against that source URL, it reads the cached transcript instead of re-fetching.

This is why the pack lists `ingest-youtube` as a hard dependency, not an optional integration. Without it, the creator-facing skills cannot reach the source content.

See `connectors/youtube.md` for the platform-specific notes (manual subtitles vs auto-captions, channel-mode pagination, language preference defaults).
