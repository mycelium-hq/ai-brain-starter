# Connector: Substack

Substack is the creator's owned-channel newsletter and membership platform. The Substack API is partially undocumented; the connector uses a mix of documented endpoints, the public RSS feed, and authenticated session-based scraping for analytics that aren't otherwise exposed.

## API surface

- Public RSS feed: `https://<publication>.substack.com/feed`
- Public API base: `https://<publication>.substack.com/api/v1/`
- Documentation: partial at https://substack.com/help/external-api, fuller community-maintained reverse-engineering at https://substack-api.readthedocs.io
- Auth: session cookies from `substack.sid` for authenticated calls (analytics, subscriber list, draft management). Session cookies are creator-scoped and rotate periodically.

## Account-type prerequisites

Any Substack publication works. The connector treats free, paid, and founding tiers as equivalent; the typed-memory layer stores tier as a field on `creator-revenue` and `audience-segment` records.

## Resources mapped to typed-memory categories

| Substack resource | Substrate category | Sync direction |
|---|---|---|
| RSS feed (public posts) | `content-piece` with `platform: substack` | inbound only |
| `/api/v1/posts` (full post content with private/paid status) | `content-piece` enrichment fields including `audience: free | paid | founding` | inbound only |
| `/api/v1/dashboard/posts` (analytics: opens, clicks, paid conversions) | `content-piece` metric fields | inbound only |
| `/api/v1/subscriber/<id>` (subscriber list with email + signup date + tier) | `audience-segment` (when aggregated) and individual subscriber records | inbound only |
| `/api/v1/comments` (per-post comment threads) | `dm-conversation` (with `subtype: substack-comment`) | inbound only on standard; write-back via authenticated POST is undocumented but works |
| `/api/v1/notes/feed` (Notes timeline) | `content-piece` with `platform: substack-note` | bidirectional (Notes can be published via the unofficial API) |
| Stripe revenue passthrough | `creator-revenue` with `revenue_source: subscription` | inbound only (via Substack-internal Stripe linkage) |

## Auth setup

The Substack API does not expose OAuth. Authentication is session-cookie based. Two paths:

1. **Manual cookie capture** (simplest for solo creators): creator logs in to Substack in a browser, opens DevTools, copies the `substack.sid` cookie value, and pastes it into the substrate's secret store via `concierge-mint substack-cookie <value>` or equivalent.
2. **Programmatic login** (for cohort installs): the substack-api Python library handles email + password login and stores the resulting session. Requires the creator to either share password (anti-pattern) or run the login flow themselves once. Cookie expires roughly every 30-60 days; the connector surfaces a re-auth prompt when calls start returning 401.

## Sync cadence

- **Post ingest:** every 4 hours via RSS for public posts. Authenticated `/api/v1/posts` pull every 12 hours adds private/paid status, draft list, and per-post analytics.
- **Subscriber ingest:** daily at 9am local. Substack does not push subscriber events; the connector pulls full subscriber list and diffs against the prior day's snapshot to detect new signups, upgrades, churn.
- **Comment ingest:** every 2 hours per published post. Comment volume is typically low on Substack relative to social platforms.
- **Notes ingest:** every 30 minutes when the creator is actively posting Notes; every 4 hours otherwise. Notes-mode is detected by recent `/api/v1/notes/feed` activity in the last 6 hours.
- **Revenue rollup:** weekly via `/weekly-creator-report`. Substack consolidates Stripe-side revenue into the dashboard so the connector reads from there instead of doubling the Stripe API call for Substack-originated subscriptions.

## Notes handling

Substack Notes are short-form posts that act as a microblog adjacent to the long-form newsletter. The connector treats Notes as `content-piece` records with `platform: substack-note` and tracks them separately from full posts because:

- Notes have different metric shapes (no opens, only views and reactions).
- Notes get repurposed into long-form posts, not the other way around. The `/repurposing-engine` skill flags Notes that are getting unusual traction as candidates for expansion.
- Notes have a different voice register; they are casual, reply-friendly, drafted in seconds. The voice-fingerprint training pipeline weights Notes lower than long-form posts when computing the writing fingerprint.

## Bilingual publications (multi-pub creators)

Many creators run a primary EN publication plus a secondary ES (or other-language) publication. The connector accepts a `--publication <slug>` flag to scope each ingest run to a single publication. The pack's init step prompts the creator to list all their publications and configures one connector instance per pub.

The typed-memory layer tags `content-piece` records with the source publication, so cross-publication queries (e.g. "what topics performed best across both my EN and ES newsletters") work natively in the graph.

## Write-back patterns

The connector writes to Substack in three cases:

1. **Note publishing** via the `substack-mcp` MCP server (out of scope for this pack but documented as a sibling tool). The pack supports drafting Notes in the typed-memory layer and handing them off to substack-mcp for publish.
2. **Post draft updates** via `/api/v1/posts/<id>/edit`. Used when `/repurposing-engine` regenerates a draft based on a podcast or video transcript.
3. **Comment replies** via authenticated POST to the comment endpoint. The endpoint is undocumented but stable; the connector logs every successful and failed call for forensics.

Publishing fully-formed posts via API is supported but the pack defaults to leaving final publish in the creator's hands via the Substack web UI, because last-minute editorial changes are common.

## Privacy + retention

- Subscriber email addresses are PII. Retention defaults to indefinite while the creator owns the publication; the substrate refuses to delete subscriber records without an explicit operator command.
- Comment author handles are pseudonymous on Substack but emails associated with comments are visible to the creator and are PII; treat them as such.
- Paid-subscriber data is regulatory-sensitive in some jurisdictions (PCI-adjacent because of Stripe linkage). The connector stores subscriber tier and join date but never stores card-on-file data.
- Substack terms of service permit creator-side analytics tooling that operates on their own publication; the connector falls cleanly within that boundary.

## Known platform constraints

- The unofficial API surface changes occasionally. The pack pins the substack-api library version and surfaces deprecation warnings during init.
- Some endpoints rate-limit at 5 requests per second per creator; the connector throttles automatically.
- Substack does not expose per-subscriber engagement (which posts a specific subscriber opened) via API. The dashboard shows aggregate cohort data only.
- Boosting and recommendation analytics are exposed via dashboard but not via API. The `/weekly-creator-report` skill scrapes these from the authenticated dashboard HTML when the cookie is fresh; surfaces a re-auth prompt when the scrape fails.
