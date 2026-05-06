# Legal vertical: typed-memory categories

Eight categories ship with the legal pack. Each category lists the required frontmatter that the substrate enforces at write time, plus optional frontmatter that downstream queries depend on.

A document that does not match its declared category schema is rejected at write time and surfaced as a recoverable error to the operator.

## matter

The unit of work. Every document in the legal pack ties back to a matter (or to a client at intake before a matter is opened).

```yaml
type: matter
matter_id: required, unique within tenant
client_id: required, FK to client
matter_name: required, human-readable
matter_type: required, one of [litigation, transactional, advisory, regulatory, ip, employment, other]
opened_date: required, ISO 8601 date
status: required, one of [open, closed, on-hold]
closed_date: optional, ISO 8601 date, required when status is closed
responsible_attorney: required, person reference
billing_arrangement: optional, one of [hourly, flat, contingency, hybrid, pro-bono]
jurisdiction: optional, ISO 3166 country plus optional state or province
practice_group: optional
```

## client

The party we represent. One client may have many matters. Adding a client triggers a conflicts-check pass; see `decision-audit/conflicts-check.md`.

```yaml
type: client
client_id: required, unique within tenant
client_name: required
client_type: required, one of [individual, corporation, llc, partnership, government, non-profit, other]
intake_date: required, ISO 8601 date
intake_attorney: required, person reference
conflicts_cleared_date: required, ISO 8601 date
conflicts_cleared_by: required, person reference
billing_contact: optional, person reference
preferred_billing_rate: optional
preferred_communication: optional, one of [email, phone, portal, secure-message]
```

## opposing-counsel

Tracked as a first-class entity for conflicts checking and to maintain an institutional memory of past adversaries.

```yaml
type: opposing-counsel
counsel_id: required, unique within tenant
counsel_name: required
firm_name: optional
matter_id: required, FK to matter
role: required, one of [opposing-counsel, co-counsel, intervenor-counsel, amicus-counsel]
contact_email: optional
contact_phone: optional
admitted_jurisdictions: optional
notes_at_intake: optional
```

## privilege-tagged-doc

Any document held under attorney-client privilege or work-product doctrine. Privilege tags drive the firewall in `decision-audit/privilege-handling.md`.

```yaml
type: privilege-tagged-doc
doc_id: required, unique within tenant
matter_id: required, FK to matter
title: required
privilege_basis: required, one of [attorney-client, work-product, joint-defense, common-interest, fiduciary, other]
created_date: required, ISO 8601 date
created_by: required, person reference
storage_location: required, FK to connector storage path
sensitive: required, boolean, defaults true
shareable_with: optional, list of person or role references inside the matter scope
external_share_blocked: required, boolean, defaults true
```

## retention-policy

A retention rule that applies to a category, a matter type, or a specific document. Rules in this category override the defaults in `retention/defaults.md` for the local install.

```yaml
type: retention-policy
policy_id: required, unique within tenant
applies_to_category: required, one of [matter, privilege-tagged-doc, billing-event, deposition-note, court-deadline]
applies_to_matter_type: optional, list of matter_type values
retention_trigger: required, one of [matter-close, doc-creation, last-touch, statutory-event]
retention_period_days: required, integer
basis: required, citation of rule (e.g., "ABA Model Rule 1.15", "California Rules of Professional Conduct 1.15")
overrides_default: required, boolean
created_date: required, ISO 8601 date
```

## billing-event

A unit of billable activity. Tracked for client billing, audit, and retention.

```yaml
type: billing-event
event_id: required, unique within tenant
matter_id: required, FK to matter
client_id: required, FK to client
attorney: required, person reference
event_date: required, ISO 8601 date
description: required, plain text
hours: optional, decimal
rate: optional, decimal
amount: optional, decimal
billable: required, boolean
status: required, one of [draft, billed, paid, written-off]
invoice_id: optional, FK to invoice when billed
```

## deposition-note

Notes from a deposition. Held under work-product privilege by default. Retention is longer than ordinary matter documents.

```yaml
type: deposition-note
note_id: required, unique within tenant
matter_id: required, FK to matter
deponent_name: required
deponent_role: required, one of [party, witness, expert, custodian, other]
deposition_date: required, ISO 8601 date
taken_by: required, person reference
court_reporter: optional
location: optional
exhibits_referenced: optional, list of doc_id
transcript_received: required, boolean
transcript_doc_id: optional, FK to privilege-tagged-doc
```

## court-deadline

A docketed deadline. Drives calendar reminders and retention triggers.

```yaml
type: court-deadline
deadline_id: required, unique within tenant
matter_id: required, FK to matter
court_name: required
case_number: required
deadline_date: required, ISO 8601 datetime with timezone
deadline_type: required, one of [filing, response, hearing, trial, status-conference, motion-cutoff, discovery-cutoff, other]
description: required
calendared: required, boolean
calendared_by: optional, person reference
extension_granted: optional, boolean
extension_basis: optional, plain text
```

## Schema enforcement

The substrate enforces required fields at write time. A document missing a required field is rejected with a recoverable error naming the missing fields. Optional fields are not enforced but are validated for type if present.

When extending these schemas locally, add fields to the optional list; do not remove required fields or the firewalls in `decision-audit/` lose load-bearing context.
