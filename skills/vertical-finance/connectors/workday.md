# Connector: Workday

Workday Financial Management and HCM share a tenant. This connector specs the API surface for the financial side; the HCM side surfaces person references for control owners and audit-evidence captured-by attribution.

## API surface

- Base URL: `https://wd2-impl-services1.workday.com/ccx/service/<tenant>/` (varies by deployment data center)
- Documentation: https://community.workday.com/api
- Auth: OAuth 2.0 with Workday Integration System User (ISU); tenant-scoped credential set.

## Resources mapped to typed-memory categories

| Workday resource | Substrate category | Sync direction |
|---|---|---|
| Suppliers | vendor | bidirectional |
| Journal Entries | journal-entry | inbound only |
| General Ledger Account Balances | reference data for materiality calculations | inbound only |
| Expense Reports | audit-evidence enrichment | inbound only |
| Workers (employees) | person reference enrichment | inbound only |
| Approval Chains | enforcement input for journal-entry approval gate | inbound only |

## Auth setup

1. Workday tenant administrator creates an Integration System User (ISU) with scoped permissions for the resources above.
2. Substrate stores ISU credentials in the firm-scoped secret store.
3. OAuth 2.0 client registered via Workday's tenant-level OAuth configuration.
4. Tokens refresh on Workday's standard cycle; the connector handles expiry transparently.

## Sync cadence

- Suppliers: daily (vendor master changes are infrequent).
- Journal entries: every 2 hours during a close period; every 6 hours otherwise.
- Account balances: end-of-day; trial-balance feeds drive the materiality threshold.
- Expense reports: daily.
- Workers: daily.
- Approval chains: weekly (changes are rare).

## Write-back rules

The connector writes back to Workday in two cases:

1. **Vendor onboarding flags.** When the substrate's vendor onboarding flow completes (W-9 received, sanctions check cleared), the connector posts the corresponding flag updates to the Supplier record. The connector never creates suppliers (that authoring lives in Workday's procurement workflow).
2. **Journal-entry tags.** When the substrate links a journal entry to a SOX control, the connector writes the control reference back to a Workday journal-entry tag if the tenant supports tags. If not supported, the link lives only in the substrate.

## Approval threshold enforcement

The journal-entry schema includes `above_threshold` and `approved_by`. The threshold is configurable per tenant, defaulting to USD 50,000. When a journal entry is pulled from Workday with `amount_usd >= threshold`, the substrate refuses to mark the entry as accepted unless `approved_by` resolves to a Workday-authorized approver per the approval chain. This prevents an approval gap where Workday allowed the entry but the substrate's audit trail would lack the approver attribution.

## Rate limits

Workday has tenant-scoped concurrency limits. The connector defaults to a single-threaded pull and lets the firm parallelize via config if the tenant allows.

## Failure modes

- ISU password rotation: the connector pauses sync, the tenant administrator updates the credential.
- Tenant downtime windows: the connector retries on a backoff schedule; sustained failure surfaces a notice.
- Schema drift in custom workdaytypes: drift logged, sync continues for unaffected types.

## What this connector does NOT do

- Workday HCM payroll data ingestion (out of scope; payroll is a separate retention regime).
- Workday Adaptive Planning (forecasting) ingestion (out of scope for v1).
- Cross-tenant queries (the substrate is tenant-scoped; multi-tenant rollup is a separate use case).
