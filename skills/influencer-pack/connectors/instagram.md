# Connector: Instagram

Instagram is the primary platform for most creator-economy installs. This connector specs the API surface, auth model, sync cadence, and write-back rules across Reels, Stories, posts, DMs, and Insights.

## API surface

- Base URL (Graph API): `https://graph.facebook.com/v23.0/`
- Documentation: https://developers.facebook.com/docs/instagram-api
- Auth: OAuth 2.0 via Meta for Developers, with a Facebook Page linked to the creator's Instagram Business or Creator account. Personal accounts cannot use the Graph API.
- Rate limits: rolling 200 calls per user per hour on standard tier. Apps in advanced access get higher caps after Meta's app review process.

## Account-type prerequisites

The connector requires the creator's Instagram account to be either Business or Creator (not Personal). The init step prints the conversion path if the account is currently Personal:

1. Open the Instagram mobile app.
2. Settings > Account > Switch to Professional Account.
3. Choose Creator (recommended) or Business.
4. Connect to a Facebook Page (create one if needed; it can be empty).
5. Re-run `/influencer-pack init --regenerate connectors/instagram.md` to verify.

## Resources mapped to typed-memory categories

| Instagram resource | Substrate category | Sync direction |
|---|---|---|
| `/{user-id}/media` (posts, Reels, Stories, IGTV) | `content-piece` with `platform: instagram-<format>` | inbound only |
| `/{media-id}/insights` (Reach, Impressions, Saves, Shares) | `content-piece` metric fields | inbound only |
| `/{ig-user-id}/insights` (Audience demographics) | `audience-segment` | inbound only |
| `/{conversation-id}/messages` (DM history per conversation) | `dm-conversation` | bidirectional (write-back via Messenger Platform send API) |
| `/{media-id}/comments` | `dm-conversation` (with `subtype: comment`) or `audience-question` | bidirectional |
| `/{user-id}/tags` (posts where the creator is tagged) | `collab-deal` (with `stage: in-delivery`) when the creator has an active deal with the tagger | inbound only |

## Auth setup

1. Creator visits https://developers.facebook.com/, creates an app of type "Business".
2. Adds the "Instagram Graph API" product to the app.
3. Connects the creator's Facebook Page to their Instagram Business/Creator account in the Meta Business Suite.
4. Substrate stores the app ID and app secret in the operator-scoped secret store, not in any vault file.
5. Creator authorizes the app via OAuth with these scopes: `instagram_basic`, `instagram_manage_comments`, `instagram_manage_messages`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`, `business_management`.
6. Substrate exchanges the short-lived token for a long-lived (60-day) token, then refreshes that token automatically before expiry.

## Sync cadence

- **Content ingest:** every 4 hours by default. Pulls the last 25 posts plus all Stories from the last 24 hours (Stories expire after 24h on the platform).
- **Insights refresh:** Monday 7am local time via `/weekly-creator-report` skill. Pulls per-content metrics for the last 30 days and rolls into `content-piece` records.
- **DM triage:** every 30 minutes by default. The `/dm-closer` skill scans new inbound messages, classifies intent, and either drafts a reply for review or auto-sends if the creator has set a per-intent allowlist.
- **Comment triage:** every 1 hour. Same pattern as DMs but lower velocity.
- **Audience demographics:** weekly via Insights API. Demographic data is aggregated to the cohort level by Meta; the connector cannot pull individual follower attributes.

## Stories handling

Stories expire after 24 hours on the platform. The connector pulls each Story's archive copy (creators can opt into auto-archive in Settings) and writes it to the typed-memory layer with `published_date` set to the original post time. If auto-archive is off, the connector pulls during the live window and depends on the creator running the sync at least every 18 hours to avoid gaps.

The Insights API returns Story metrics for 28 days post-publish on the standard tier, longer with paid Insights upgrades. The `/weekly-creator-report` skill reads from this window to roll Story performance into the weekly digest.

## DM handling

Instagram DMs split into two surfaces in the Graph API:

1. **Messenger inbox** (general conversations) accessible through the Instagram-connected Page's Messenger Platform endpoints.
2. **Message Requests** (from non-followers) accessible through a separate scope and only after the creator opens the request in-app at least once.

The connector reads from both. The `/dm-closer` skill applies the same intent classification across them (fan, prospect, brand-collab, creator-collab, support, spam) and routes high-priority threads to the creator's review queue regardless of which inbox they originated in.

## Write-back patterns

The connector writes to Instagram in three cases, all gated on creator approval:

1. **DM replies** drafted by `/dm-closer` and approved by the creator. Substrate enforces a sign-off step before any reply posts.
2. **Comment replies** drafted by `/dm-closer` (same pattern, comment subtype). Same sign-off gate.
3. **Story link stickers and post captions** generated by `/content-engine` for the creator to review and post manually. The connector does not auto-publish posts or Stories; that stays in the creator's hands via the native Instagram app.

Posting Reels via API requires the Content Publishing API (separate scope) and is explicitly out of scope for this connector. Creators publish through the native app; the connector reads what was published.

## Privacy + retention

- DM content is sensitive. Retention defaults to 90 days unless the creator extends per-conversation.
- DM authors' handles are stored as primary keys in `dm-conversation` records. Tier-A creators may opt to hash handles in their typed-memory layer; the connector supports `--hash-handles` flag.
- Comment authors' handles follow the same pattern as DM handles.
- Insights are aggregate (cohort-level) data; no individual-follower retention concerns apply.

## Known platform constraints

- The Graph API does NOT expose Personal account data. Creators must convert to Business or Creator account first; this is a one-way Meta decision per their developer terms.
- The Instagram-connected Page must remain published and the Page admin must remain a follower of the Instagram account; either condition breaking will revoke the API connection.
- Story Insights have a 28-day window on the standard tier. Longer retention requires Meta Business Suite Premium.
- Reels Insights for boosted Reels include extra metrics (cost per result, cost per click) that the connector reads when present and surfaces in `/weekly-creator-report`.
- Live API is separate from the Insights API; live-stream chat is handled by the YouTube Live API for cross-platform creators or by the dedicated Live API for IG-only.
