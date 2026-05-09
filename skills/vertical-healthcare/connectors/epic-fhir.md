# Connector: Epic FHIR

Epic is the dominant EHR at large US health systems. This connector targets the FHIR R4 surface and uses SMART-on-FHIR for auth.

## API surface

- Base URL: per-tenant Epic FHIR endpoint, varies (`https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/` is a common shape for Epic-hosted environments)
- Documentation: https://fhir.epic.com
- Auth: SMART-on-FHIR with OAuth 2.0 (backend services flow for system-level access; authorization code flow for user-context access)

## Resources mapped to typed-memory categories

| FHIR resource | Substrate category | Sync direction |
|---|---|---|
| Patient | patient identity store + reference | inbound only |
| Encounter | encounter reference (used by patient-scoped-fact) | inbound only |
| Observation | patient-scoped-fact | inbound only |
| Condition | patient-scoped-fact (diagnosis subtype) | inbound only |
| MedicationRequest | patient-scoped-fact (medication subtype) | inbound only |
| AllergyIntolerance | patient-scoped-fact (allergy subtype) | inbound only |
| Procedure | patient-scoped-fact (procedure subtype) | inbound only |
| DocumentReference | phi-tagged-doc | inbound only |
| CarePlan | clinical-decision (care-plan subtype) | inbound only |
| ServiceRequest | clinical-decision (referral subtype) | inbound only |

The connector is read-only. Epic is the EHR source of truth; the substrate mirrors structured FHIR data for memory and audit, never authors back.

## Auth setup

1. Health system registers a SMART-on-FHIR app via Epic's App Orchard or via direct Epic admin enrollment.
2. Backend services flow uses asymmetric key (JWKS) signing; substrate stores the private key in a tenant-scoped secret store, publishes the public key at a JWKS endpoint Epic can reach.
3. Authorization code flow (when user-context access is needed) uses standard SMART scopes (`patient/*.read`, `user/*.read`).
4. Per-patient access is gated by the patient's chart context; the substrate does not bypass Epic's break-glass or chart-access controls.

## Sync cadence

- Patient master: nightly (patient demographics change rarely).
- Encounters: every 30 minutes (active encounters drive most query volume).
- Observations, Conditions, Medications, Allergies, Procedures: every hour.
- DocumentReference: every 4 hours (document volume is high; metadata-only sync).
- CarePlan, ServiceRequest: every 2 hours.

The connector defaults conservatively; the health system tunes via config.

## Privilege handling

Epic's chart-access controls (break-glass, sensitive-chart, behavioral-health restrictions) are honored. The connector reads only what the authorizing user or system principal is entitled to read. PHI markers from Epic (sensitive-chart flags, 42 CFR Part 2 subset) are stamped onto the substrate's `phi_tagged` and `sensitive` fields.

If Epic surfaces a chart with a 42 CFR Part 2 marker, the connector does NOT pull that chart's data unless the substrate has been explicitly configured for Part 2 handling; Part 2 is out of scope for v1, and the connector errs on the side of refusal.

## Rate limits

Epic's FHIR API has tenant-scoped rate limits. The connector backs off on 429 with exponential retry; chronic 429s pause sync and notify the administrator.

## Failure modes

- JWKS rotation: the connector publishes the new public key at the JWKS endpoint and rotates the private key in the secret store; Epic picks up the new key on next request.
- Chart access revoked: the connector logs the access change, drops cached data for the affected chart from any non-audit-scoped store, continues sync for unaffected charts.
- FHIR version drift: the connector targets R4; if the tenant moves to R5 or beyond, the connector updates per the FHIR migration guidance.

## What this connector does NOT do

- Authoring back to Epic (no MyChart messages, no order entry, no chart writes).
- Pulling 42 CFR Part 2 records (out of scope for v1).
- Pulling psychotherapy notes (HIPAA prohibits routine disclosure; the connector skips by default).
- Bulk historical backfill beyond 24 months without explicit administrator request.
