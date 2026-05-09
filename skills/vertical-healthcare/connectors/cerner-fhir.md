# Connector: Cerner FHIR (Oracle Health)

Oracle Cerner Millennium is the second-largest EHR at US health systems. This connector targets the FHIR R4 surface and uses SMART-on-FHIR for auth.

## API surface

- Base URL: per-tenant Cerner FHIR endpoint, varies (`https://fhir-myrecord.cerner.com/r4/` is a common shape for production tenants)
- Documentation: https://fhir.cerner.com (Oracle Health Developers portal)
- Auth: SMART-on-FHIR with OAuth 2.0 (backend services flow and authorization code flow)

## Resources mapped to typed-memory categories

| FHIR resource | Substrate category | Sync direction |
|---|---|---|
| Patient | patient identity store + reference | inbound only |
| Encounter | encounter reference | inbound only |
| Observation | patient-scoped-fact | inbound only |
| Condition | patient-scoped-fact (diagnosis subtype) | inbound only |
| MedicationRequest | patient-scoped-fact (medication subtype) | inbound only |
| AllergyIntolerance | patient-scoped-fact (allergy subtype) | inbound only |
| Procedure | patient-scoped-fact (procedure subtype) | inbound only |
| DocumentReference | phi-tagged-doc | inbound only |
| CarePlan | clinical-decision (care-plan subtype) | inbound only |
| ServiceRequest | clinical-decision (referral subtype) | inbound only |

Read-only. Cerner is the source of truth.

## Auth setup

1. Health system registers a SMART-on-FHIR app via Cerner's developer portal (https://code.cerner.com).
2. Backend services flow with JWKS-signed assertions; substrate manages the keypair in the tenant secret store.
3. Authorization code flow with standard SMART scopes for user-context queries.

## Sync cadence

Same defaults as the Epic connector:

- Patient master: nightly.
- Encounters: every 30 minutes.
- Observations, Conditions, Medications, Allergies, Procedures: every hour.
- DocumentReference: every 4 hours.
- CarePlan, ServiceRequest: every 2 hours.

## Privilege handling

Cerner's privacy filters (sensitive-chart flags, behavioral-health markers, custodial restrictions) are honored. The connector reads only what the authorizing principal is entitled to. PHI markers stamp onto `phi_tagged` and `sensitive`.

42 CFR Part 2 records are out of scope for v1; the connector skips charts with that marker.

## Rate limits

Cerner's FHIR API has tenant-scoped rate limits documented in the developer portal. The connector backs off on 429.

## Failure modes

Same shapes as Epic: JWKS rotation, chart access revocation, FHIR version drift.

## What this connector does NOT do

- Authoring back to Cerner.
- Pulling 42 CFR Part 2 records.
- Pulling psychotherapy notes.
- Bulk historical backfill beyond 24 months without explicit request.

## Cerner-specific notes

- Cerner's `Patient.identifier` slice for MRN varies by tenant configuration. The connector reads the configured slice via the tenant's CapabilityStatement; if the slice is missing, the connector falls back to the system-level MRN identifier and surfaces a notice.
- Cerner's terminology bindings (especially for Observation.code) frequently use proprietary code systems alongside LOINC. The connector preserves both; downstream queries against patient-scoped-fact can match on either.
