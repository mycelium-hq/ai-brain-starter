# Connector: Salesforce Health Cloud

Salesforce Health Cloud is a health-CRM platform on top of the Salesforce platform. Used by payers, providers, and life-sciences orgs to manage care coordination, member engagement, and outreach. Sits next to (not inside) the EHR; this connector pulls care-coordination data, not clinical records.

## API surface

- Base URL: per-tenant Salesforce instance (`https://<my-domain>.my.salesforce.com`)
- API: REST API + Bulk API 2.0 + Streaming API for change events
- Documentation: https://help.salesforce.com/s/articleView?id=ind.healthcare.htm
- Auth: OAuth 2.0 (JWT bearer flow for backend services; web server flow for user-context access)

## Resources mapped to typed-memory categories

Health Cloud uses standard Salesforce SObjects with healthcare-specific extensions (the Health Cloud managed package). The connector targets the canonical Health Cloud objects:

| Salesforce SObject | Substrate category | Sync direction |
|---|---|---|
| Account (Person Account: Patient) | patient identity store + reference | inbound only |
| HealthCloudGA__EhrEncounter__c | encounter reference | inbound only |
| HealthCloudGA__EhrCondition__c | patient-scoped-fact (diagnosis subtype) | inbound only |
| HealthCloudGA__EhrMedicationStatement__c | patient-scoped-fact (medication subtype) | inbound only |
| HealthCloudGA__EhrAllergyIntolerance__c | patient-scoped-fact (allergy subtype) | inbound only |
| HealthCloudGA__EhrObservation__c | patient-scoped-fact (observation subtype) | inbound only |
| CareProgram | clinical-decision (care-program-enrollment subtype) | inbound only |
| CareRequest | clinical-decision (referral or care-request subtype) | inbound only |
| CarePlanTemplate, CarePlan | clinical-decision (care-plan subtype) | inbound only |
| ContentDocument (PHI-tagged) | phi-tagged-doc | inbound only |
| Account (BAA-flagged business partner) | baa-counterparty | inbound + writeback for BAA status |

The connector is read-only for clinical data. Health Cloud is the care-coordination source of truth; the substrate mirrors structured care data for memory and audit, never authors clinical decisions back to Health Cloud.

## Auth setup

1. Health system (or payer) registers a Salesforce Connected App with OAuth scopes (`api`, `refresh_token`, `offline_access`) and Health Cloud-specific scopes when needed.
2. JWT bearer flow uses an X.509 certificate uploaded to the Connected App; the substrate stores the private key in a tenant-scoped secret store and signs JWTs at request time.
3. User-context access (when a clinician needs to act on Health Cloud data) uses the standard web server flow with PKCE.
4. Per-record access is gated by Salesforce sharing rules and field-level security; the substrate does not bypass these.

## Sync cadence

- Person Accounts (patients): nightly (demographic changes are rare).
- EhrEncounter: every 30 minutes (active encounters drive most query volume).
- EhrCondition / EhrMedicationStatement / EhrAllergyIntolerance / EhrObservation: every hour.
- CarePlan / CareRequest / CareProgram: every 2 hours.
- ContentDocument (PHI-tagged): every 4 hours; metadata-only sync, body fetched on demand.
- Streaming API change events: real-time when configured (CDC channel for canonical SObjects).

The connector defaults conservatively; the entity tunes via config based on its API limits and usage patterns.

## Privilege handling

Salesforce sharing rules, field-level security, and Health Cloud's record-type permissions govern what the connector can read. The substrate does NOT bypass any of these; if the API user does not have access, the substrate logs the access denial and continues with the records it can read.

PHI markers from Health Cloud (`Sensitive__c` field, behavioral-health record type, 42 CFR Part 2 stamp where the entity has configured Part 2 handling on the Salesforce side) are stamped onto the substrate's `phi_tagged` and `sensitive` fields.

If a record carries a 42 CFR Part 2 marker, the connector does NOT pull that record's data unless the substrate has been explicitly configured for Part 2 handling; Part 2 is out of scope for v1.

## Rate limits

Salesforce enforces a 24-hour API request limit (varies by edition: typically 100k requests / day for Enterprise, 1M+ for Unlimited with Health Cloud). The Bulk API 2.0 has a separate batch quota.

The connector backs off on `REQUEST_LIMIT_EXCEEDED` and `EXCEEDED_ID_LIMIT` errors with exponential retry. Chronic limit errors pause sync and notify the administrator. The connector publishes a daily request-volume report so the administrator can size capacity.

## Failure modes

- **Cert rotation:** the substrate publishes the new public key on the Connected App and rotates the private key in the secret store; Salesforce picks up the new key on next request.
- **Sharing-rule revocation:** the connector logs the access change, drops cached data for the affected record from any non-audit-scoped store, continues sync for unaffected records.
- **Health Cloud package version drift:** the connector targets the current major Health Cloud package; on package upgrade, the substrate validates that target SObjects still exist with expected fields.
- **Streaming-event channel disconnect:** the connector falls back to polling cadence and re-establishes the streaming channel on next sync window.

## What this connector does NOT do

- Authoring clinical decisions back to Health Cloud (care-coordination users, not EHR-substitute users; clinical decisions belong in the EHR).
- Pulling 42 CFR Part 2 records (out of scope for v1).
- Pulling encrypted Salesforce Shield-protected fields without explicit decryption-permission configuration.
- Bulk historical backfill beyond 24 months without explicit administrator request.
- Acting as a Salesforce-to-Salesforce relay between two Health Cloud orgs.
