# Connector: Stripe

Stripe is the primary payment processor for most creator products: courses, paid subscriptions, digital downloads, ticketed events, 1-on-1 sessions, brand-deal cash flow. This connector specs the Stripe API surface and the typed-memory mapping for revenue tracking.

## API surface

- Base URL: `https://api.stripe.com/v1/`
- Documentation: https://stripe.com/docs/api
- Auth: API keys (test + live). The connector reads only; never holds the live secret key in any vault file. Live restricted keys with `read-only` scope are recommended.
- Rate limits: 100 requests per second on the live tier. Webhook delivery handles burst load.

## Resources mapped to typed-memory categories

| Stripe resource | Substrate category | Sync direction |
|---|---|---|
| `/charges` (one-time payments) | `creator-revenue` with `revenue_source: product` or `course` | inbound only |
| `/subscriptions` (recurring) | `creator-revenue` with `revenue_source: subscription` | inbound only |
| `/customers` (paying customer record) | `dm-conversation` link or `audience-segment` aggregate | inbound only |
| `/invoices` (per-billing-period charges, recurring + one-time) | `creator-revenue` enrichment | inbound only |
| `/payouts` (transfers from Stripe to creator's bank) | `creator-revenue` aggregation | inbound only |
| `/refunds` | `creator-revenue` with negative amount | inbound only |
| `/disputes` (chargebacks) | `creator-revenue` with negative amount + `notes: chargeback` | inbound only |
| Stripe Connect transfers (when the creator is a platform paying out to others, e.g. cohort facilitators) | `creator-revenue` outbound entry, separate `stripe-payout` type | inbound only |

## Auth setup

1. Creator logs in to https://dashboard.stripe.com/.
2. Navigate to Developers > API keys.
3. Create a Restricted Key with these permissions: Charges read, Subscriptions read, Customers read, Invoices read, Payouts read, Refunds read, Disputes read. No write permissions for the typed-memory pull.
4. Substrate stores the restricted key in the operator-scoped secret store.
5. Optional: configure webhook endpoint at `https://<runtime-host>/webhooks/stripe` for real-time event ingest. Webhooks reduce poll cadence and enable instant revenue notifications.

The pack init step generates the precise restricted-key permission set as a Stripe dashboard URL the creator can click to pre-fill, so they do not have to manually toggle 8 checkboxes.

## Sync cadence

- **Daily rollup:** 9am local time. Pulls the prior day's charges, subscriptions, refunds, and disputes. Writes one `creator-revenue` record per Stripe object.
- **Weekly aggregation:** Monday 8am via `/weekly-creator-report`. Aggregates by `revenue_source`, splits sponsorship vs subscription vs product vs course vs speaking vs affiliate, computes month-to-date and year-to-date totals.
- **Webhook-driven (optional):** if the creator wires the webhook endpoint, every Stripe event fires an immediate ingest call and the typed-memory layer reflects the change within seconds. Without webhooks, the daily rollup is sufficient for most creator workflows.
- **Tax prep batch:** annually, January 15th. Pulls full prior-year transaction set and rolls into a `creator-revenue` summary that maps to common 1099-K and Schedule C categories.

## Multi-product handling

Most creators run several products through the same Stripe account: a paid newsletter, a course, a coaching package, occasional one-off product launches. The connector reads the Stripe Product and Price metadata and maps each charge to a product line via:

1. The `product.metadata.creator_revenue_category` custom field (set during product creation).
2. If absent, the price's `nickname` field for heuristic matching.
3. If both absent, the charge is tagged `revenue_source: other` and the operator is prompted to set the creator-revenue-category metadata going forward.

The pack init step generates a Stripe-dashboard URL to bulk-edit existing products and add the metadata field.

## Connection to Substack and Patreon

Substack and Patreon both use Stripe under the hood for paid subscriptions but mediate the customer relationship through their own UI. The connector supports two modes:

1. **Direct Stripe ingest only:** simpler, treats Substack and Patreon revenue as `revenue_source: subscription` with `platform: stripe-substack` or `platform: stripe-patreon` metadata. Recommended for creators who do not want to authorize Substack and Patreon connectors separately.
2. **Layered ingest:** Substack and Patreon connectors pull subscription data from those platforms (with subscriber tier, signup source, attribution) and the Stripe connector cross-references on transaction ID to enrich the `creator-revenue` record. Recommended for creators who want full attribution.

## Privacy + retention

- Customer records are PII. Retention defaults to 7 years (matches IRS recordkeeping requirements in the US; varies by jurisdiction). The pack init step prompts for the creator's tax-residency jurisdiction and adjusts retention accordingly.
- Card-on-file data is NEVER stored in the typed-memory layer. Stripe handles PCI compliance; the substrate stores only the last-4 digits and brand if Stripe surfaces them, which it does only for some endpoints.
- Refunds and disputes contain customer-side complaint data; treat as sensitive and store with the same retention rules as customer records.

## Write-back patterns

This connector is read-only by default. Write operations (issuing refunds, modifying subscriptions, creating one-off invoices) require additional API key scopes and are explicitly out of scope for the pack.

If a creator wants to issue refunds programmatically, they can mint a separate Stripe restricted key with refund-write permission and pass it through the `creator-cli` tool, which is a separate package outside the pack boundary.

## Known platform constraints

- Stripe Connect (for creators who run a platform that pays out to other creators or facilitators) requires a Stripe Atlas or Connect account, separate from a standard Stripe account. The connector handles both but the auth flow differs; the pack init step detects which type the creator has.
- Stripe metadata fields are 500 characters max per key, 50 keys per object. The connector encodes the creator-revenue category and any UTM-attributed source into metadata; very-long-tail attribution may exceed this and gets truncated with a warning.
- International Stripe accounts (UK, EU, AU, CA, etc.) have slightly different fee structures. The connector stores fees at the per-charge level and the weekly report computes net-of-fees revenue correctly across multi-jurisdiction creators.
- Stripe's `events` endpoint goes back 30 days. Older data must be pulled from the relevant resource endpoint directly. The pack init step does a 30-day backfill on first run, then maintains incremental.
