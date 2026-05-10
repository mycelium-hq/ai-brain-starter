# Connector: Buffer / Later / Metricool

Buffer, Later, and Metricool are cross-platform schedulers used to queue content across Instagram, TikTok, X, LinkedIn, Facebook, Pinterest, and YouTube from a single dashboard. The connector covers all three (they have similar APIs) plus other schedulers that follow the same pattern.

## API surface

- Buffer: https://buffer.com/. Public API at https://buffer.com/developers/api. OAuth 2.0.
- Later: https://later.com/. Public API at https://developers.later.com/. OAuth 2.0.
- Metricool: https://metricool.com/. API at https://metricool.com/api. API key auth.
- Auth: tool-specific. The connector pulls credentials from the operator-scoped secret store.

## Resources mapped to typed-memory categories

| Asset | Substrate category | Sync direction |
|---|---|---|
| Scheduled posts (queued but not yet published) | `content-piece` with `status: scheduled` and `scheduled_at: <ISO>` | bidirectional (read scheduled queue; write new schedule entries) |
| Published-via-scheduler posts | `content-piece` with `published_via: <buffer | later | metricool>` | inbound only (cross-references with platform connectors) |
| Optimal-posting-time recommendations (Metricool primarily) | `audience-segment` enrichment with `best_time: <HH:MM>` per platform | inbound only |

## Operator workflow

1. `/content-engine` skill drafts a week's content slate (Reels, TikToks, X threads, LinkedIn posts).
2. Drafts get assembled into a single batch import file at `External Inputs/Buffer/Schedule/<YYYY-MM-DD>-week.csv`.
3. Creator imports the batch into Buffer/Later/Metricool, reviews proposed schedule, adjusts times to fit native-app trending windows.
4. Scheduled queue gets pulled back into the typed-memory layer with `status: scheduled` and the platform-specific scheduled time.
5. Once posts publish, the platform connectors (Instagram, TikTok, etc.) pick up the published version with metrics.

## Calendar coordination

The pack init step asks which scheduling tool the creator uses (one or more). For creators using multiple tools across teams (e.g. Buffer for personal + Metricool for client work), the connector handles multi-account state per tool.

The `/weekly-creator-report` skill cross-references scheduled-vs-published-vs-engaged to surface "scheduled but never went live" anomalies (most often a token expired mid-week).

## Privacy + retention

- Scheduled drafts may contain unreleased brand-deal material. Retention follows the published-piece retention if the post goes live; gets purged 30 days after scheduled date if cancelled.
- All three tools store creator content on their servers; substrate does not control that retention.

## Alternatives the pack supports interchangeably

- Hootsuite
- Sprout Social
- SocialPilot
- Loomly
- Publer
- Postiz

Same pattern: batch import from vault, queue in tool, scheduled state pulled back, published state cross-referenced with platform connectors.
