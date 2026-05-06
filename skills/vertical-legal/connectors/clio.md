# Connector: Clio

Clio is the most common practice-management platform at boutique and mid-market firms. This connector specs the API surface, auth model, sync cadence, and write-back rules.

## API surface

- Base URL: `https://app.clio.com/api/v4/`
- Documentation: https://docs.developers.clio.com/
- Auth: OAuth 2.0 authorization code flow per firm; access tokens expire after 7 days, refresh tokens long-lived.

## Resources mapped to typed-memory categories

| Clio resource | Substrate category | Sync direction |
|---|---|---|
| `/matters` | matter | bidirectional |
| `/contacts` | client (when `type: Person` or `type: Company` is a client), opposing-counsel | bidirectional |
| `/documents` | privilege-tagged-doc (with privilege tag enrichment from custom field) | inbound only |
| `/activities` | billing-event | bidirectional |
| `/calendar_entries` | court-deadline (filtered to docketed-deadline subtype) | bidirectional |

## Auth setup

1. Firm administrator registers an OAuth application at https://app.clio.com/settings/developer_applications.
2. Substrate stores the client ID and client secret in the firm-scoped secret store, not in any vault file.
3. Each user authorizes once via OAuth authorization code flow; the substrate stores the per-user refresh token under the user's auth scope.
4. Tokens refresh automatically on every sync.

## Sync cadence

- Matters: hourly during business hours (8 AM to 8 PM local), daily overnight.
- Contacts: every 6 hours; conflicts checks force an inline sync at intake.
- Documents: hourly metadata sync; document bodies sync on demand when the substrate references them.
- Activities: every 15 minutes (billing fidelity matters).
- Calendar entries: hourly.

## Write-back rules

The connector writes back to Clio in three cases:

1. **Activities (billing events).** When the substrate captures a billable event (from a meeting note, an email thread, a session log), the connector writes a draft activity to Clio. The activity is created in `non-billable-no-charge` mode with a `pending review` tag; the attorney finalizes and submits in Clio.
2. **Calendar entries (court deadlines).** When the substrate detects a court deadline from a docketing-clerk email or a filed order, the connector writes a draft calendar entry to Clio with the deadline and a 7-day-out reminder.
3. **Matter notes.** Memos and decision-audit log entries that the operator marks `share_with_clio: true` are written as matter notes.

The connector does NOT write back to:

- Contacts (clients and opposing counsel must be created in Clio first; we mirror, we do not author).
- Documents (the firm's document management system is the source of truth; we do not push docs back into Clio).
- Trust account ledger (out of scope for v1).

## Privilege handling

Documents pulled from Clio inherit a privilege tag based on the matter's `privilege_default` custom field plus per-document overrides. If the firm has not set up the custom field, the connector defaults every document to `privilege_basis: attorney-client` and surfaces a notice asking the firm to configure the custom field for higher-fidelity tagging.

The connector never sends privileged document bodies outside the matter scope; the firewall in `decision-audit/privilege-handling.md` runs on write to local storage and on every read from a query that crosses matter boundaries.

## Rate limits

Clio API is rate-limited per token. The connector backs off on 429 with exponential retry; chronic 429s are surfaced as a sync-health warning to the firm administrator.

## Failure modes

- Token expiry without refresh token: the user re-authorizes; the connector pauses sync for that user until re-auth completes.
- Schema drift in Clio custom fields: the connector logs the drift to the audit log and surfaces a configuration prompt; sync continues for unaffected fields.
- Network timeouts: the connector retries with backoff; chronic failures pause sync and notify the administrator.

## What this connector does NOT do

- Two-way document body sync (we mirror metadata; bodies stay where they live).
- Trust accounting writes (out of scope for v1).
- Bulk historical backfill beyond the most recent 24 months (the firm requests a deeper backfill explicitly; the connector pages the API politely).
