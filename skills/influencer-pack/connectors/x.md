# Connector: X (Twitter)

X (formerly Twitter) is a primary distribution surface for thought-leader and writer creators. The X API has gone through significant pricing and policy changes since 2023; this connector handles both the paid API tiers and a session-based fallback for read-only access on creators without paid tier.

## API surface

- Base URL: `https://api.twitter.com/2/`
- Documentation: https://docs.x.com/x-api
- Auth: OAuth 2.0 with PKCE (recommended) or OAuth 1.0a (legacy). Authorization happens via X for Developers.
- Pricing tiers (subject to change):
  - Free: 1,500 tweets/month read access, no DM access. Effectively just enough to verify auth.
  - Basic: $200/month. 10,000 tweets/month read, 50,000 tweets/month write, no DM API.
  - Pro: $5,000/month. 1M tweets/month, full DM API access.
  - Enterprise: contact sales. Full firehose.
- Rate limits per tier are documented at https://docs.x.com/x-api/fundamentals/rate-limits.

## Two operational modes

Most creator workflows do not justify Pro tier ($5K/mo). The connector supports two modes:

1. **API mode (Basic tier or higher):** authenticated tweet ingest, basic analytics, reply posting via API. No DM access on Basic tier.
2. **Session-cookie fallback (free for creators without paid API):** session-based scraping of the creator's own timeline, mentions, and DMs through the authenticated web UI. Slower, less reliable, but free. The connector automatically falls back to session mode if the API key is not configured or the rate limit blocks an ingest.

The pack init step asks the creator which mode they want and configures accordingly. Session mode is the default for cohort-tier creators.

## Resources mapped to typed-memory categories

| X resource | Substrate category | Sync direction |
|---|---|---|
| Creator's tweets and threads | `content-piece` with `platform: x-post` or `x-thread` | inbound only |
| Tweet metrics (impressions, engagements, profile visits) | `content-piece` metric fields | inbound only |
| DMs (Pro tier only via API; session mode for fallback) | `dm-conversation` with `platform: x` | bidirectional |
| Mentions (replies and quote-tweets to the creator) | `dm-conversation` with `subtype: x-mention` | inbound only |
| Spaces (audio rooms hosted or attended by the creator) | `content-piece` with `format: audio` and `platform: x-space` | inbound only |
| Followers list aggregate metrics (count, growth rate) | `audience-segment` aggregate | inbound only |
| Bookmarks (the creator's own bookmark list) | `content-source` with `source_platform: x` | inbound only |

## Auth setup

API mode:
1. Creator visits https://developer.x.com/, applies for a developer account.
2. Creates an X app, generates OAuth 2.0 credentials.
3. If the creator wants DM access, upgrades to Pro tier.
4. Substrate stores the client ID, client secret, and bearer token in the operator-scoped secret store.
5. Creator authorizes via OAuth with these scopes: `tweet.read`, `users.read`, `dm.read` (Pro only), `tweet.write` (only if write-back planned), `dm.write` (Pro only).

Session-cookie mode:
1. Creator logs in to https://x.com/ in a browser.
2. Captures the `auth_token` cookie value via DevTools.
3. Stores via `concierge-mint x-cookie <value>`.
4. Cookie rotates roughly every 30 days; the connector surfaces re-auth prompts.

## Sync cadence

- **Tweet ingest:** every 2 hours. Pulls last 50 tweets and resolves any thread chains. Threads are stored as a single `content-piece` with `format: thread` and the full sequence as the body.
- **Metrics refresh:** every 6 hours via the standard tier `/tweets/<id>` endpoint. Engagement metrics update for ~30 days post-publish; older tweets get static snapshots.
- **Mentions ingest:** every 1 hour. Mentions get classified by intent (fan / prospect / brand-collab / creator-collab / spam) just like DMs.
- **DM triage (Pro tier):** every 30 minutes. Same `/dm-closer` skill flow as Instagram.
- **DM triage (session mode):** every 2 hours, scrape-based. Slower and partial; some DM views require manual page-load.
- **Bookmark ingest:** weekly. The creator's bookmarks are typically reference material for content; the `content-source` entries become inputs to `/repurposing-engine`.

## Thread handling

X threads are the single most-distinctive content format on the platform. The connector treats a thread as one `content-piece` with `format: thread` and stores the full sequence as the body, preserving tweet boundaries with double-newline separators. Per-tweet metrics get rolled up to thread-level (sum of impressions, etc.) with a per-tweet breakdown stored in metadata.

The `/repurposing-engine` skill treats threads as primary source material:

- A thread can become a Substack post (expand each tweet into a paragraph).
- A thread can become a LinkedIn post (compress to single-post form, retain the framing).
- A thread can become a YouTube short narrated by the creator's voice fingerprint.

## Spaces handling

Spaces are X's audio-room product. The connector ingests Spaces hosted or attended by the creator, including title, scheduled time, host, speaker list, and recording URL when available.

Spaces recordings are not always saved by the host. When a recording exists, the connector pulls the audio via the X API or web fallback and runs it through the same Whisper transcription path that `ingest-youtube` uses for no-subtitle videos. The transcript becomes a `content-source` (if attended) or `content-piece` (if hosted).

## Write-back patterns

The connector writes to X in three cases, all gated on creator approval:

1. **Tweet posting** drafted by `/content-engine` or `/repurposing-engine`. The substrate enforces a sign-off step before any tweet posts. Threads are posted as a single API batch via `/tweets` with replies chained.
2. **DM replies** via the DM API on Pro tier or session-mode fallback. Same approval gate.
3. **Quote-tweets** of the creator's own past content for re-circulation, drafted by `/content-engine` and gated on creator approval.

## Privacy + retention

- DM content is sensitive. Retention defaults to 90 days unless the creator extends.
- Mention authors' handles are stored as primary keys; treat as PII in jurisdictions with strict data-retention rules (EU, CA, etc.).
- Bookmark URLs are creator-private (X does not surface bookmarks publicly); retention defaults to indefinite.
- Spaces recordings can contain audience voices when an audience member is invited to speak. Retention follows the highest-sensitivity rule of the participants the creator can identify.

## Known platform constraints

- The X API has changed pricing and policy frequently since 2023. The pack pins to current docs and surfaces deprecation warnings during init.
- Free tier is effectively unusable for creator workflows; Basic ($200/mo) is the minimum useful tier and Pro ($5K/mo) is required for DM API access.
- Session-cookie mode breaks when X enforces 2FA or rotates cookie schemas. The connector logs failures and prompts re-auth.
- Tweet impressions are exposed only to the tweet's author (via the analytics page); the connector reads from the analytics page in session mode and from the API in API mode. Both paths return the same number.
- X's recommendation algorithm shapes who sees a given tweet. The API does not expose recommendation-side data; the only signal is the impression count.
