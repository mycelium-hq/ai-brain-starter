# Connector: Stan Store

Stan Store is a creator-economy storefront-plus-link-in-bio platform popular with Instagram and TikTok creators. The platform aggregates digital products, courses, coaching, ticketed events, and affiliate links into a single creator-branded page. The connector covers product list ingest, sales analytics, and click-attribution.

## API surface

- Stan Store does not publish a public API. The connector uses authenticated session-based ingest from the creator dashboard at `https://www.stan.store/dashboard`.
- Auth: session cookies from the creator's logged-in browser. The pack init step walks through cookie capture in the same flow as Substack.
- Rate limits: undocumented; the connector throttles to 1 req/sec to stay safe.

The lack of public API is a known constraint. Stan Store has acknowledged a public API as roadmap but the timeline is not committed; the connector is built to swap to API mode the moment it ships, with the session-cookie path as fallback.

## Resources mapped to typed-memory categories

| Stan Store resource | Substrate category | Sync direction |
|---|---|---|
| Product list (digital downloads, courses, coaching offers, events) | `content-piece` with `platform: stan-store` and `format: <product-type>` | inbound only |
| Sales (per-transaction with product, customer email, amount, UTM source) | `creator-revenue` with `revenue_source: <product | course | speaking>` | inbound only |
| Click events (per-link click on the link-in-bio page with UTM source) | `audience-segment` aggregate (clicks-per-source) | inbound only |
| Customer list (paying customers with email + order history) | `dm-conversation` link or `audience-segment` aggregate | inbound only |
| Email-capture leads (people who opted in but did not purchase) | `audience-segment` with `tier: lead` | inbound only |

## Auth setup

1. Creator logs in to https://www.stan.store/dashboard in a browser.
2. Opens DevTools, navigates to Application > Cookies, copies the session cookie value.
3. Stores via `concierge-mint stan-store-cookie <value>` or equivalent.
4. Cookie expires periodically; the connector surfaces a re-auth prompt when calls return 401.

The pack init step generates the Stan Store dashboard URL the creator can click directly to streamline this.

## Sync cadence

- **Product ingest:** daily at 9am local. Pulls full product catalog with current price, status (active/draft/archived), and inventory if applicable.
- **Sales rollup:** every 4 hours. Pulls last 24 hours of transactions, writes one `creator-revenue` record per sale.
- **Click ingest:** every 2 hours. Pulls last 6 hours of click events; aggregates by source UTM and writes to `audience-segment` aggregate counters.
- **Lead capture:** daily at 9am. Pulls full lead list with opt-in date and source. Diffs against prior-day snapshot to detect new leads.
- **Weekly rollup:** Monday 8am via `/weekly-creator-report`. Aggregates by product, computes conversion rate (clicks → leads → sales), surfaces top-performing products and underperforming products.

## Cross-platform attribution

Stan Store's primary value is link-in-bio attribution: which Instagram caption or TikTok comment drove which sale. The connector preserves this by reading the UTM source on every click and sale. The typed-memory layer cross-references this against `content-piece` records (Instagram posts, TikTok videos) to surface revenue-per-piece.

The `/weekly-creator-report` skill uses this cross-reference to produce questions like "this Reel drove 47 link-in-bio clicks but zero sales; what's the friction" or "this caption pattern converts at 4.2% versus the average of 1.8%; ship more of these."

## Affiliate tracking

Stan Store supports affiliate links where the creator earns a commission for driving traffic to other creators' or brands' products. The connector tags affiliate revenue as `revenue_source: affiliate` and stores the merchant name in the `counterparty` field.

For creators running heavy affiliate programs, the pack init step optionally enables a separate `/affiliate-pipeline` skill that tracks per-merchant performance, payout schedules, and contract renewal dates. This skill is bundled with the pack.

## Privacy + retention

- Customer email addresses are PII. Retention default is 7 years (matches IRS recordkeeping and most consumer-protection rules in US/EU/CA jurisdictions).
- Lead emails (opted-in but not purchased) follow the same retention but the creator can choose to purge after 12 months for non-engaging leads. The pack init step prompts for this preference.
- UTM source data is non-PII and retained indefinitely for trend analysis.
- Coaching and ticketed-event customers may have additional context fields (booking time, special requests) that contain PII; these get the same 7-year retention.

## Write-back patterns

The connector is read-only. Stan Store does not currently support write operations via session-cookie auth. Product creation, price updates, and customer messaging happen in the Stan Store native dashboard.

When the public API ships, the connector will gain write capability for product updates and customer messaging; the substrate already supports the typed-memory write path, only the connector needs the API switch.

## Known platform constraints

- Session cookies expire roughly every 30-90 days. The connector caches and surfaces re-auth prompts proactively when calls start to fail.
- Stan Store does not expose product cost-of-goods (the creator's cost basis on a digital download is zero, but on a physical product it matters). The connector stores revenue at gross level and the creator can subtract cost-of-goods downstream if needed.
- Stan Store's reporting UI sometimes shows different numbers than the Stripe dashboard for the same period (timing differences, refund handling). The pack treats Stan Store as the canonical source for product-level attribution and Stripe as the canonical source for cash-flow accounting; the weekly report reconciles both.
- The session-cookie path is the only access mode currently. If Stan Store rolls out 2FA enforcement, the cookie path may break; the connector will need an updated auth pattern at that point.
