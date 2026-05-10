# Connector: TikTok

TikTok is the second-most-common platform for creator installs. The TikTok API surface is narrower than Instagram's and has stricter rate limits, but the connector covers content ingest, DMs, and basic analytics.

## API surface

- Base URL: `https://open.tiktokapis.com/v2/`
- Documentation: https://developers.tiktok.com/doc/overview
- Auth: OAuth 2.0 via TikTok for Developers (sandbox tier for testing, production tier after app review).
- Rate limits: 1,000 calls per app per day per user on the standard tier. Quota increases require app review with documented use case.

## Account-type prerequisites

Creators need a TikTok account with at least 1,000 followers to access the Login Kit and Display API. Below 1,000 followers, the connector reads only public metadata via web scraping fallback (degraded mode, marked as such in metadata).

## Resources mapped to typed-memory categories

| TikTok resource | Substrate category | Sync direction |
|---|---|---|
| `/video/list/` (creator's posted videos) | `content-piece` with `platform: tiktok` | inbound only |
| `/video/query/` (video metadata: title, description, duration, music, hashtags) | `content-piece` enrichment fields | inbound only |
| `/research/video/insights/` (Research API: views, likes, comments, shares; available on Research tier only) | `content-piece` metric fields | inbound only |
| `/user/info/` (display name, follower count, following count) | `audience-segment` aggregate | inbound only |
| Direct messages | `dm-conversation` | bidirectional (write-back limited; see Write-back patterns below) |
| Comments | `dm-conversation` (with `subtype: comment`) | inbound only on standard tier; bidirectional on Research tier |

## Auth setup

1. Creator visits https://developers.tiktok.com/, creates an app of type "Login Kit" or "Content Posting" depending on use case.
2. Apps start in Sandbox mode; only the creator's own account and explicitly added test accounts can authorize. Production status requires app review.
3. Substrate stores the client key and client secret in the operator-scoped secret store.
4. Creator authorizes via OAuth with these scopes: `user.info.basic`, `video.list`, `video.upload` (only if write-back planned), `comment.list`, `comment.list.manage`.

## Sync cadence

- **Content ingest:** every 6 hours by default. Pulls the last 30 videos. TikTok does not surface Stories or live streams in the standard API.
- **Insights refresh:** Monday 7am local time. Standard tier returns view + like + comment counts; Research tier adds completion rate, watch time distribution, audience retention.
- **DM triage:** TikTok DMs are largely creator-to-creator. The connector polls every 1 hour. DMs from brands typically arrive via Email or via Linktree-style outbound, not via in-app DM.
- **Comment triage:** every 2 hours via the Comment List API. Higher-volume creators may need to batch this overnight if quota tightens.

## Write-back patterns

TikTok's API restricts write operations more aggressively than Instagram or Twitter. The connector supports:

1. **Comment replies** via `/comment/reply/` (Research tier only). Standard tier: comments are read-only.
2. **Comment moderation** (hide spam, pin top comment) via `/comment/manage/` if the creator has the `comment.list.manage` scope.

DM write-back is NOT available via the public API. DMs can only be sent through the TikTok mobile or web app. The `/dm-closer` skill drafts replies and surfaces them as approval-required items; the creator copies and pastes into the TikTok app to send.

## Repurposing flow

The `/repurposing-engine` skill treats TikTok as both a source and a target:

- **Source:** the creator's own TikToks become inputs for cross-platform repurposing into Reels (vertical 9:16 fits both), YouTube Shorts (also 9:16), and X video posts.
- **Target:** repurposed clips from longer-form sources (podcast clips, keynote highlights) get rendered to TikTok dimensions and dropped into a "ready to post" folder. The connector does not auto-publish; the creator posts manually through the TikTok app to preserve the trending-music workflow that requires in-app discovery.

## Privacy + retention

- DM content is sensitive. Retention defaults to 90 days unless the creator extends.
- TikTok handles are pseudonymous in many cases; treat them as PII and follow the same hashing pattern as Instagram if the creator opts in.
- Comments are public on the platform but creator-private in the typed-memory layer. Default retention 1 year.
- TikTok terms of service prohibit redistribution of video content via API beyond fair-use research and creator workflow tooling. The connector stores video metadata and creator-owned content; it does not re-host other users' videos.

## Known platform constraints

- TikTok's "For You" page algorithm is opaque; the API does not expose recommended-content data even for the creator's own account.
- The Research API tier requires academic affiliation in many jurisdictions. Commercial creator workflows typically use the standard tier with degraded analytics.
- Music licensing complicates cross-platform repurposing. TikToks using trending audio cannot be re-uploaded to Reels with the same audio without licensing risk; the connector flags this and the `/repurposing-engine` skill swaps to royalty-free audio when crossing platforms.
- Live stream API is separate and requires creator affiliation with TikTok LIVE program. Out of scope for the standard pack.
