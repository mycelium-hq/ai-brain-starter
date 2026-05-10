# Connector: LinkedIn

LinkedIn is the primary distribution surface for B2B creator content: thought-leader posts, business commentary, conference talks, professional development. The LinkedIn API is heavily restricted; most creator workflows rely on a mix of the public Marketing API tier and session-based access.

## API surface

- Base URL: `https://api.linkedin.com/v2/`
- Documentation: https://learn.microsoft.com/en-us/linkedin/
- Auth: OAuth 2.0 with member-scoped tokens. Apps must be approved by LinkedIn for production scopes.
- Rate limits: app-tier dependent. The Community Management API (which covers post-publishing) is gated behind an application process.

## Operational reality

LinkedIn's API restricts read access on competitor-style data. The connector covers what the official API exposes plus a session-based fallback for the rest:

- API-accessible: the creator's own posts (with full metrics) via `/me/posts`, the creator's own DMs via the messaging API (after app review), basic follower count.
- Session-fallback: post engagement breakdown (who engaged, in what role, at what company), DM threads pre-app-approval, mention notifications, content performance benchmarks against the creator's network.

The pack defaults to API mode when the creator has been approved and falls back to session mode otherwise.

## Resources mapped to typed-memory categories

| LinkedIn resource | Substrate category | Sync direction |
|---|---|---|
| Creator's posts | `content-piece` with `platform: linkedin-post` or `linkedin-article` | inbound only |
| Post analytics (impressions, reactions, comments, shares) | `content-piece` metric fields | inbound only |
| Per-engager attribution (who liked, what company, what role) | `audience-segment` enrichment + `dm-conversation` link | inbound only (session mode for full breakdown) |
| Direct messages | `dm-conversation` with `platform: linkedin` | bidirectional via approved-app messaging API; session mode for fallback |
| Connection requests | `dm-conversation` with `subtype: connection-request` | bidirectional |
| Mentions and @-tags | `dm-conversation` with `subtype: linkedin-mention` | inbound only |
| Newsletter (LinkedIn-native newsletter) | `content-piece` with `platform: linkedin-newsletter` | inbound only |

## Auth setup

API mode:
1. Creator visits https://www.linkedin.com/developers/, creates a new app.
2. Selects relevant products: "Sign In with LinkedIn", "Marketing Developer Platform", "Community Management API" (if applying for write access).
3. App goes through LinkedIn's review process for production scopes; this can take 2-6 weeks.
4. Substrate stores client ID and client secret in the operator-scoped secret store.
5. Creator authorizes via OAuth with these scopes: `r_liteprofile`, `r_emailaddress`, `r_organization_social` (for company-page-attached creators), `w_member_social` (write access if approved).

Session mode:
1. Creator logs in to https://linkedin.com/ in a browser.
2. Captures the `li_at` cookie value via DevTools.
3. Stores via `concierge-mint linkedin-cookie <value>`.
4. Cookie rotates roughly every 30-60 days.

## Sync cadence

- **Post ingest:** every 4 hours. Pulls last 25 posts plus any post modified in the last 7 days. Newsletter editions get pulled separately on the same cadence.
- **Engagement breakdown:** Monday 9am via `/weekly-creator-report`. Surfaces per-post engager breakdown by company size, role title, and industry. This is the highest-signal LinkedIn data point for B2B creators because it answers "is my content reaching the buyers I want to reach."
- **DM triage:** every 1 hour in API mode (Pro app); every 3 hours in session mode.
- **Mentions ingest:** every 2 hours.
- **Connection-request triage:** daily at 9am. The `/dm-closer` skill classifies incoming connection requests (warm intro / cold prospect / random spam) and surfaces qualified inbound to the creator.

## B2B-specific signal

LinkedIn's distinctive value is per-engager job title and company. The connector preserves this in the typed-memory layer so the creator can answer questions like:

- Which content formats convert C-level engagers vs IC engagers
- Which posts reached buyers at companies in our target ICP
- Are my Reels or carousels driving more qualified leads
- Who keeps engaging post after post and might be open to a DM

The `/weekly-creator-report` skill surfaces top-3 engagers from the creator's ICP each week as warm DM candidates.

## Newsletter handling

LinkedIn-native newsletters have a different distribution model than feed posts: subscribers opt in once, every issue email-pushes to them. The connector treats newsletter editions as `content-piece` with `format: newsletter-edition` and tracks open rate, click rate, and subscriber growth separately from feed metrics.

For creators running both a Substack and a LinkedIn newsletter, the typed-memory layer cross-references on topic so the `/repurposing-engine` skill can suggest cross-posts that fit each surface's voice register.

## Write-back patterns

The connector writes to LinkedIn in three cases, all gated on creator approval:

1. **Post publishing** via `/ugcPosts` (API mode, requires `w_member_social`). Drafts come from `/content-engine` or `/repurposing-engine`. Substrate enforces sign-off.
2. **DM replies** via approved Messaging API (Pro tier app) or session fallback.
3. **Connection-request acceptance/decline** drafted by `/dm-closer` based on intent classification.

Article publishing (long-form) and newsletter editions are write-back via separate endpoints; the pack supports both but defaults to manual publish since LinkedIn's editor has formatting features (custom hero images, embedded video, etc.) that the API does not fully cover.

## Privacy + retention

- Engager identity (name + company + title) is PII. LinkedIn's terms permit the creator to use this for their own creator workflow but prohibit reselling or republishing.
- DM content is sensitive. Retention defaults to 90 days unless extended.
- Connection-request notes follow same rules as DMs.
- Newsletter subscriber lists fall under the same retention as Substack subscribers (7 years for tax/legal recordkeeping in most jurisdictions).

## Known platform constraints

- LinkedIn deprecates API endpoints aggressively. The connector pins to v2 with soft-warn on deprecation notices in API responses.
- The Community Management API approval process is opaque and slow. Many creators run for years on session mode without getting approved.
- LinkedIn's algorithm surfaces a narrow slice of the creator's audience per post. Reach is highly volatile post-to-post; the connector flags outlier reaches as anomalies for review.
- Carousel posts (image-set format) have a separate analytics surface; the connector handles both feed-post and carousel formats.
