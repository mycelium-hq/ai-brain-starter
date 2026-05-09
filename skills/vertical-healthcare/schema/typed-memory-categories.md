# Healthcare vertical: typed-memory categories

Seven categories ship with the healthcare pack. Each lists the required frontmatter the substrate enforces at write time, plus optional frontmatter that downstream queries depend on.

A document that does not match its declared category schema is rejected at write time and surfaced as a recoverable error.

## patient-scoped-fact

Any fact about a patient. Tagged with the patient's tenant-internal identifier (never a raw HIPAA identifier; identifiers are mapped into a separate identity store).

```yaml
type: patient-scoped-fact
fact_id: required, unique within tenant
patient_internal_id: required, FK to patient identity store
encounter_id: optional, FK to encounter (when the fact is encounter-scoped)
fact_type: required, one of [diagnosis, observation, medication, procedure, allergy, social-history, family-history, plan, communication, other]
fact_text: required, plain text
recorded_date: required, ISO 8601 datetime with timezone
recorded_by: required, person reference
source_system: required, one of [epic, cerner, salesforce-health-cloud, manual, other]
source_resource_id: optional, the FHIR resource ID or equivalent
phi_tagged: required, boolean, defaults true
sensitive: required, boolean, defaults false (true for behavioral health, HIV, substance use, reproductive)
```

## clinical-decision

A clinical recommendation, treatment decision, or care-plan change. Drives the decision trail in `decision-audit/clinical-decision-trail.md`.

```yaml
type: clinical-decision
decision_id: required, unique within tenant
patient_internal_id: required, FK to patient identity store
encounter_id: required, FK to encounter
decision_text: required, plain text
decision_type: required, one of [diagnosis, treatment, medication, procedure, referral, discharge, care-plan, other]
decision_date: required, ISO 8601 datetime with timezone
decision_maker: required, person reference (the credentialed provider accountable)
input_data_references: required, list of fact_id or doc_id (must be non-empty)
alternatives_considered: optional, plain text or list
supporting_evidence_references: optional, list of doc_id (clinical guidelines, prior cases, literature)
shared_decision_making: optional, boolean (whether the patient or family participated in the decision)
phi_tagged: required, boolean, defaults true
```

## phi-tagged-doc

Any document containing PHI. Drives the firewall in `decision-audit/phi-handling.md`.

```yaml
type: phi-tagged-doc
doc_id: required, unique within tenant
patient_internal_id: optional, FK to patient identity store (omit only for de-identified docs)
encounter_id: optional, FK to encounter
title: required
phi_identifiers_present: required, list of integers 1 through 18 (the HIPAA identifier catalog)
created_date: required, ISO 8601 datetime with timezone
created_by: required, person reference
source_system: required
storage_location: required, FK to connector storage path
sensitive: required, boolean
de_identification_status: required, one of [identified, limited-data-set, safe-harbor-deidentified, expert-determination-deidentified]
external_share_blocked: required, boolean, defaults true
```

## baa-counterparty

A business associate (or subcontractor of a business associate) bound by a BAA. Drives the BAA-execution status check.

```yaml
type: baa-counterparty
counterparty_id: required, unique within tenant
legal_name: required
counterparty_type: required, one of [business-associate, subcontractor, hybrid-entity, other]
ba_role: required, plain text describing the BA function (claims processing, IT services, transcription, etc.)
baa_executed_date: required, ISO 8601 date
baa_effective_date: required, ISO 8601 date
baa_termination_date: optional, ISO 8601 date
baa_doc_id: required, FK to phi-tagged-doc (the executed BAA)
phi_categories_disclosed: required, list of strings (treatment, payment, operations, research, marketing, other)
breach_notification_window_days: required, integer (defaults 60 per HIPAA, may be tighter per BAA)
status: required, one of [active, terminated, suspended]
```

## retention-policy

A retention rule.

```yaml
type: retention-policy
policy_id: required, unique within tenant
applies_to_category: required
applies_to_state: optional, list of US state codes
retention_trigger: required, one of [creation, last-touch, encounter-close, patient-deceased, age-of-majority, statutory-event]
retention_period_days: required, integer (or symbolic identifier for "until age 18 plus N")
basis: required, citation
overrides_default: required, boolean
created_date: required, ISO 8601 date
```

## hipaa-incident

A HIPAA security or privacy incident. Tracked from detection through closure.

```yaml
type: hipaa-incident
incident_id: required, unique within tenant
incident_type: required, one of [unauthorized-access, unauthorized-disclosure, lost-device, malware, phishing, insider-misuse, vendor-incident, other]
detection_date: required, ISO 8601 datetime with timezone
detected_by: required, person reference
description: required, plain text
patients_affected_estimate: optional, integer
investigation_status: required, one of [open, in-progress, closed-no-breach, closed-breach-confirmed, closed-other]
investigation_lead: required, person reference (privacy or security officer)
closure_date: optional, ISO 8601 date
closure_disposition: optional, plain text
breach_notification_id: optional, FK to breach-notification record (when the incident is determined to be a breach)
```

## breach-notification

A breach notification under the HIPAA Breach Notification Rule.

```yaml
type: breach-notification
notification_id: required, unique within tenant
incident_id: required, FK to hipaa-incident
breach_determination_date: required, ISO 8601 date
patients_affected_count: required, integer
phi_categories_breached: required, list of integers 1 through 18
risk_assessment_doc_id: required, FK to phi-tagged-doc
notification_to_individuals_date: optional, ISO 8601 date (required within 60 days of discovery)
notification_to_hhs_date: optional, ISO 8601 date
notification_to_media_required: required, boolean (true when 500+ residents of a state are affected)
notification_to_media_date: optional, ISO 8601 date
ocr_breach_report_id: optional, the HHS OCR submission identifier
state_notifications_required: required, list of US state codes
state_notifications_completed: optional, list of US state codes with dates
```

## Schema enforcement

The substrate enforces required fields at write time. Documents missing required fields are rejected with recoverable errors. The PHI fields (`phi_tagged`, `phi_identifiers_present`, `external_share_blocked`) are load-bearing for the firewall in `decision-audit/phi-handling.md`; do not weaken them locally.

The patient identity store is a separate component (not in this schema). Patient internal IDs in this schema are pointers; the actual identifier mapping (MRN, SSN partial, DOB) lives in a tightly-controlled identity service that the substrate does not directly query for ad-hoc operations.
