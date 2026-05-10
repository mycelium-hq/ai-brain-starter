# Connector: Patreon

Patreon is the dominant membership platform for creators with a recurring-subscription business model. The connector covers patron list ingest, tier breakdown, monthly revenue rollups, and patron-only post analytics.

## API surface

- Base URL: `https://www.patreon.com/api/oauth2/v2/`
- Documentation: https://docs.patreon.com/#api-reference
- Auth: OAuth 2.0 with separate scopes for patron-list read, post management, and campaign analytics.
- Rate limits: documented as "reasonable" (no hard published numbers); the connector throttles to 1 req/sec to stay safe.

## Resources mapped to typed-memory categories

| Patreon resource | Substrate category | Sync direction |
|---|---|---|
| `/api/oauth2/v2/campaigns` (the creator's campaign metadata) | `audience-segment` aggregate per tier | inbound only |
| `/api/oauth2/v2/campaigns/<id>/members` (patron list with tier and join date) | `creator-revenue` (per-patron monthly recurring) and `audience-segment` | inbound only |
| `/api/oauth2/v2/campaigns/<id>/posts` (creator's posts including patron-only) | `content-piece` with `platform: patreon` and `audience: <tier>` | inbound only |
| `/api/oauth2/v2/posts/<id>/analytics` (per-post views, likes, comments, paid-only conversions) | `content-piece` metric fields | inbound only |
| Direct messages (Patreon's in-app message system) | `dm-conversation` | bidirectional via authenticated POST (see Write-back patterns) |
| Comments on patron-only posts | `dm-conversation` (with `subtype: patreon-comment`) | bidirectional |

## Auth setup

1. Creator logs in to https://www.patreon.com/portal/registration/register-clients to register an OAuth client.
2. Selects "Creator" client type. Patreon has separate "Creator" and "Patron" client types; only Creator can read patron list data.
3. Substrate stores the client ID and client secret in the operator-scoped secret store.
4. Creator authorizes via OAuth with these scopes: `identity`, `campaigns`, `campaigns.members`, `campaigns.posts`, `w:campaigns.posts` (only if write-back planned).
5. Patreon issues a refresh token alongside the access token; refresh token does not expire as long as the OAuth client remains active.

## Sync cadence

- **Patron list refresh:** daily at 8am local. Pulls full member list, diffs against prior-day snapshot. Writes new patrons as new `creator-revenue` recurring entries with `revenue_source: subscription` and `platform: patreon`. Surfaces churned patrons (canceled subscriptions) and tier-upgrades (joined-tier change) as separate events.
- **Campaign analytics:** weekly via `/weekly-creator-report`. Aggregates by tier, computes MRR (monthly recurring revenue) per tier, growth rate, churn rate.
- **Post ingest:** every 6 hours. Pulls last 20 posts plus all posts modified in the last 7 days.
- **Comment + DM triage:** every 2 hours. Patreon DMs are higher-signal than most platforms because senders are paying customers; the `/dm-closer` skill weights Patreon DMs higher in the priority queue by default.
- **Tax-prep batch:** annually mid-January. Patreon issues 1099-K equivalent for US creators above the threshold; the connector pulls the source-of-truth revenue total to cross-check.

## Tier handling

A creator's Patreon campaign typically has 3-7 tiers (e.g. "Supporter $5", "Insider $15", "Founder $50"). The connector treats each tier as an `audience-segment` and tags every `content-piece` with its visibility tier. This enables queries like "what content do my $50/mo Founders engage with most" or "is my $15 Insider tier delivering enough exclusive value to justify the price."

Tier benefits (per-tier perks like Discord access, monthly Q&A, physical mail) are stored as `audience-segment.benefits` field. The pack init step prompts the creator to enumerate per-tier benefits so the typed-memory layer can later flag underdelivered benefits.

## Patron-only content

Patreon's whole value proposition is patron-exclusive content. The connector tags each `content-piece` with the minimum tier required to access it. This matters for:

- The `/repurposing-engine` skill, which must NOT cross-publish patron-only content to public platforms (Substack public posts, public Reels, etc.). The substrate enforces a hard guard on this.
- The `/voice-fingerprint-update` skill, which weights patron-only content alongside public content for voice training (the creator's voice is their voice regardless of audience).
- The `/weekly-creator-report` skill, which surfaces top-performing patron-only content as a signal for what could be expanded into a paid product or course.

## Bilingual creators

Creators who run separate EN and ES Patreon campaigns (rare; most creators run one campaign with multilingual content) can authorize multiple campaign IDs against the same OAuth client. The pack init step prompts for any additional campaigns and configures one connector instance per campaign.

## Write-back patterns

The connector writes to Patreon in three cases:

1. **DM replies** drafted by `/dm-closer` and approved by the creator. Patreon DM API allows authenticated POST.
2. **Comment replies** on patron-only posts. Same pattern as DMs.
3. **Patron-only post drafts** created by `/repurposing-engine` from a public source (e.g. expanding a public Substack post into a patron-only deep-dive). The connector creates a draft via `/posts` with `is_paid: true` and the appropriate tier-access scope; final publish stays in the creator's hands via the Patreon web UI.

## Privacy + retention

- Patron names + email addresses are PII. Retention defaults to indefinite while the patron is active. After a patron churns, retention shifts to 24 months for chargeback/dispute window then auto-purge.
- Pledge amounts per patron are sensitive (some patrons are visible on the campaign page, but per-patron private-tier data is NOT public). Treat as confidential.
- Patron messages contain personal context the patron expects to share only with the creator. Same retention as Instagram DMs (90 days default, creator can extend).

## Known platform constraints

- The Patreon API does not expose the exact reason a patron canceled (declined card, voluntary cancel, account closure). Churn events are surfaced without reason; the connector marks these and the creator can manually annotate if they reach out and learn the reason.
- Patreon does not expose individual patron engagement on free public posts (the platform has a partial public surface). Engagement on patron-only posts is fully exposed.
- The Patreon API has historically deprecated and rebuilt itself (v1 to v2 migration in 2018; ongoing v3 work). The connector pins to v2 with a soft-warn if the API surface changes.
- Some Patreon payment methods (PayPal, etc.) settle on different cadences than Stripe. The connector handles cadence delays and reconciles on the campaign-level monthly summary rather than per-charge.
