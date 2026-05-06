# Connector: NetSuite

NetSuite ERP is common at mid-market F500 buyers and at acquired subsidiaries that have not consolidated onto a parent's ERP. This connector specs the SuiteTalk REST surface.

## API surface

- Base URL: `https://<account-id>.suitetalk.api.netsuite.com/services/rest/` (account-scoped)
- Documentation: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1559132219.html
- Auth: Token-based authentication (TBA) with OAuth 1.0a, per-account credential set.

## Resources mapped to typed-memory categories

| NetSuite resource | Substrate category | Sync direction |
|---|---|---|
| Vendor | vendor | bidirectional |
| Journal Entry | journal-entry | inbound only |
| Account | reference data for materiality | inbound only |
| Transaction (with type filter) | journal-entry, audit-evidence enrichment | inbound only |
| Employee | person reference enrichment | inbound only |
| Approval Routing | enforcement input for journal-entry approval gate | inbound only |
| Subsidiary | tenant-scope routing | inbound only |

## Auth setup

1. NetSuite administrator enables the SuiteTalk REST API and Token-Based Authentication features.
2. Administrator creates an Integration record (gives client credentials) and an Access Token tied to a service-account user with scoped permissions.
3. Substrate stores the consumer key, consumer secret, token ID, and token secret in the firm-scoped secret store.
4. Per-subsidiary scoping is supported via subsidiary filters on the queries.

## Sync cadence

- Vendors: daily.
- Journal entries: every 2 hours during close; every 6 hours otherwise.
- Account balances: end-of-day.
- Transactions: every 4 hours (the connector filters to journal entries, vendor bills, customer invoices, deposits).
- Employees: daily.
- Approval routing: weekly.

## Write-back rules

Same posture as the Workday connector:

1. Vendor onboarding flag updates.
2. Journal-entry control-reference tags via NetSuite custom fields if configured.

The connector does not create vendors, journal entries, or transactions. Authoring lives in NetSuite.

## Subsidiary handling

NetSuite OneWorld instances span multiple subsidiaries. The substrate's tenant scope can be configured to:

- One substrate tenant per NetSuite subsidiary (preferred for clear segregation).
- One substrate tenant for the consolidated NetSuite account, with subsidiary as a frontmatter field on every record.

The default is one tenant per subsidiary; the firm overrides if they want consolidation in the substrate.

## Rate limits

NetSuite has request-per-minute and concurrent-request limits. The connector defaults to conservative cadences; the firm tunes via config.

## Failure modes

- Token rotation: the substrate prompts the administrator to regenerate; sync pauses for that integration during rotation.
- Schema drift in custom fields: drift logged; sync continues.
- Subsidiary access changes: connector pauses for the affected subsidiary, notifies the administrator.

## What this connector does NOT do

- NetSuite SuiteScript execution (out of scope; the substrate does not run code in NetSuite).
- NetSuite Advanced Inventory (out of scope; surfaces in the manufacturing pack).
- NetSuite SuiteCommerce or webstore (out of scope).
