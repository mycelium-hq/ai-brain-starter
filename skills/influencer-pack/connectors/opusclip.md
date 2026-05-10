# Connector: OpusClip / Klap

OpusClip and Klap are AI tools that turn long-form video (1+ hour podcast or keynote) into platform-optimized short-form clips. The connector treats them as a tooling step in the `/repurposing-engine` workflow.

## API surface

- OpusClip: https://www.opus.pro/. API in early access at https://www.opus.pro/api. Most workflows use the web app.
- Klap: https://klap.app/. API at https://klap.app/api. Web app is the primary surface.
- Auth: web-app login or API key (paid tier).

## Resources mapped to typed-memory categories

| Asset | Substrate category | Sync direction |
|---|---|---|
| Generated short clips from a long-form source | `content-piece` (one per clip) with `format: short-form` and `derived_from: <source content_id>` | manual (creator exports + drops into vault folder) |
| Per-clip score (the tool's predicted virality) | `content-piece` enrichment with `predicted_score: <0-100>` | manual entry from the tool's UI |

## Operator workflow

1. `/ingest-youtube` (or equivalent for podcast platforms) pulls the long-form source into the typed-memory layer as a `content-piece`.
2. Creator opens OpusClip or Klap, imports the source URL or video file, runs auto-clip generation.
3. Tool produces 5-15 candidate clips with predicted-virality scores.
4. Creator reviews and selects the top 3-5.
5. Selected clips export to `External Inputs/OpusClip/<YYYY-MM-DD>/<source-slug>/clip-<n>.mp4`.
6. `/repurposing-engine` skill picks up the exported clips, generates platform-specific captions for each (one for Reels, one for TikTok, one for Shorts, one for X), and stages them as draft `content-piece` records.

## Score-tracking

The tools expose a per-clip predicted-virality score. The pack stores this score in `content-piece.predicted_score` and the `/weekly-creator-report` skill compares predicted versus actual performance after the clip publishes. This delta becomes a feedback signal for which long-form sources produce reliably good shorts.

## Privacy + retention

- Source long-form videos may contain unreleased material (drafts, brand-deal previews). The creator imports only what is publishable; the connector does not enforce this.
- Generated clips inherit the retention rules of the source (if the source is patron-only, the clip cannot cross-publish; the substrate enforces this guard).
- Both tools store source video on their servers as part of the workflow; substrate does not control that retention.

## Alternatives the pack supports interchangeably

- Submagic
- Vizard.ai
- Hippo Video
- Munch
- 2short.ai

Same workflow: long-form source into the tool, AI-generated short clips out, drop into vault, `/repurposing-engine` consumes. The init step asks which tool the creator uses and configures the folder names.
