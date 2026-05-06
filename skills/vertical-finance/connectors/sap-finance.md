# Connector: SAP Finance

SAP S/4HANA Finance (and the legacy ECC FI module) is the dominant ERP at large F500 buyers. This connector specs the OData and CDS view surface; legacy ECC instances are supported via SAP Process Integration (PI) or SAP Cloud Platform Integration (CPI) bridges, but the canonical target is S/4HANA Cloud or on-premise S/4HANA with OData enabled.

## API surface

- Base URL: per-tenant, varies (`https://<host>:<port>/sap/opu/odata/sap/` is a common shape)
- Documentation: https://api.sap.com (S/4HANA Cloud APIs catalog)
- Auth: OAuth 2.0 with SAP Cloud Identity Services for cloud; basic auth or X.509 for on-premise.

## Resources mapped to typed-memory categories

| SAP entity / OData service | Substrate category | Sync direction |
|---|---|---|
| Business Partner (BP) supplier role | vendor | bidirectional |
| Journal Entry (FI documents, BKPF/BSEG via OData) | journal-entry | inbound only |
| GL Account Master | reference data for materiality | inbound only |
| Cost Center / Profit Center | reference data | inbound only |
| Approval Workflow (S/4HANA Workflow service) | enforcement input | inbound only |
| Material (manufacturing tie-in) | hand-off to the manufacturing pack | inbound only |

## Auth setup

1. SAP Basis or BTP administrator registers the OAuth client in SAP Cloud Identity Services.
2. Service user with scoped authorizations (S_BTCH_ADM, FI/CO display roles) is created and tied to the OAuth client.
3. Substrate stores the client ID, client secret, and tenant base URL in the firm-scoped secret store.
4. For on-premise S/4HANA, the substrate supports basic auth as a fallback; production deployments should use OAuth via SAP BTP.

## Sync cadence

- Business partners (suppliers): daily.
- Journal entries: every 2 hours during close; every 6 hours otherwise.
- GL master: weekly (account master is stable).
- Cost centers: weekly.
- Approval workflow: weekly.

## Write-back rules

1. Vendor onboarding flag updates against business partner extensions if the firm's BP schema supports them.
2. Journal-entry control reference via SAP custom field (Z-field) if the tenant's chart of accounts has been extended to carry it.

The connector does not create journal entries, business partners, or master data. Authoring lives in SAP.

## Materiality threshold

S/4HANA's parallel ledgers and currency translation mean a single journal entry can have multiple amounts (local currency, group currency, hard currency). The substrate uses the group currency amount converted to USD for materiality. The conversion uses the SAP-provided rate at posting date; if the rate is missing, the connector fails the materiality check and surfaces the entry for manual review.

## Rate limits

S/4HANA Cloud has per-tenant call limits documented in the API catalog. On-premise S/4HANA limits depend on the firm's licensing and hardware; the connector defaults conservatively.

## Failure modes

- OAuth token rotation: handled transparently with refresh tokens.
- Tenant downtime: the connector retries on backoff; chronic failure surfaces a notice.
- Schema drift in Z-fields: drift logged, sync continues for unaffected fields.
- Currency rate gaps: materiality check fails, entry surfaces for manual review.

## What this connector does NOT do

- SAP HANA database direct query (out of scope; the connector goes through documented APIs).
- SAP HCM (out of scope; Workday is the HCM target).
- SAP MM and PP modules (manufacturing pack handles those tie-ins).
- Legacy ECC without OData (the firm uses PI or CPI bridges; the connector targets S/4HANA Cloud or on-premise S/4HANA with OData).
