# Finance vertical: typed-memory categories

Nine categories ship with the finance pack. Each category lists the required frontmatter that the substrate enforces at write time, plus optional frontmatter that downstream queries depend on.

A document that does not match its declared category schema is rejected at write time and surfaced as a recoverable error to the operator.

## deal

A deal: an M&A transaction, a financing, a strategic investment, a divestiture, or a major commercial agreement.

```yaml
type: deal
deal_id: required, unique within tenant
deal_name: required
deal_type: required, one of [m-and-a-buy, m-and-a-sell, financing-debt, financing-equity, joint-venture, divestiture, commercial-agreement, other]
status: required, one of [pipeline, diligence, signing, closing, closed, terminated]
target_close_date: optional, ISO 8601 date
actual_close_date: optional, ISO 8601 date
deal_lead: required, person reference
counterparty_id: required, FK to counterparty
deal_size_usd: optional, decimal (USD equivalent at signing)
materiality: required, one of [non-material, material, highly-material]
audit_evidence_attached: optional, list of audit_evidence_id
```

## counterparty

The other side of a deal or commercial relationship.

```yaml
type: counterparty
counterparty_id: required, unique within tenant
legal_name: required
entity_type: required, one of [public-corp, private-corp, llc, partnership, fund, government, individual, other]
jurisdiction_of_incorporation: required
parent_entity_id: optional, FK to counterparty
ultimate_parent_entity_id: optional, FK to counterparty
sanctions_check_date: optional, ISO 8601 date
sanctions_check_disposition: optional, one of [cleared, blocked, pending]
kyc_completed_date: optional, ISO 8601 date
```

## sox-control

A SOX 404 internal control. Each control is owned, tested, and stamped with evidence per the audit cycle.

```yaml
type: sox-control
control_id: required, unique within tenant
control_name: required
control_objective: required, plain text
control_owner: required, person reference
control_frequency: required, one of [transactional, daily, weekly, monthly, quarterly, annual]
control_type: required, one of [preventative, detective, automated, manual, hybrid]
risk_rating: required, one of [low, medium, high]
significant_account: optional, GL account or grouping
testing_status: required, one of [not-tested, in-progress, tested-pass, tested-fail, remediation, retired]
last_tested_date: optional, ISO 8601 date
next_test_due_date: optional, ISO 8601 date
```

## audit-evidence

A piece of evidence supporting a control test, a journal entry, a deal close, or a board decision.

```yaml
type: audit-evidence
evidence_id: required, unique within tenant
evidence_type: required, one of [screenshot, system-log, signed-doc, third-party-confirm, calculation-workbook, transcript, other]
captured_date: required, ISO 8601 date
captured_by: required, person reference
linked_to_category: required, one of [sox-control, journal-entry, deal, board-pack-decision, internal-audit-finding]
linked_to_id: required, FK to the linked record
storage_location: required, FK to connector storage path
hash_sha256: required, content hash for tamper evidence
retention_through: required, ISO 8601 date (computed from retention rules)
```

## journal-entry

A general ledger journal entry. Tracked for audit trail and SOX evidence.

```yaml
type: journal-entry
entry_id: required, unique within tenant
posting_date: required, ISO 8601 date
period: required, fiscal period identifier
entered_by: required, person reference
approved_by: optional, person reference (required for entries above approval threshold)
account_debits: required, list of {account, amount, currency}
account_credits: required, list of {account, amount, currency}
amount_usd: required, decimal (USD equivalent)
description: required, plain text
supporting_evidence: optional, list of evidence_id
control_reference: optional, list of control_id
above_threshold: required, boolean (configurable per tenant)
```

## expense-policy

A documented policy. Used as the rule the operator's expense reports test against.

```yaml
type: expense-policy
policy_id: required, unique within tenant
policy_name: required
applies_to_category: required, one of [travel, meals, lodging, gifts, entertainment, training, equipment, other]
threshold_amount_usd: optional, decimal
approval_required_above_threshold: required, boolean
documentation_required: required, list of [receipt, business-purpose, attendees, mileage-log, other]
effective_date: required, ISO 8601 date
superseded_date: optional, ISO 8601 date
superseded_by: optional, FK to expense-policy
```

## vendor

A counterparty in the procure-to-pay flow. Tracked separately from `counterparty` because the vendor master has tighter onboarding and tax requirements.

```yaml
type: vendor
vendor_id: required, unique within tenant
legal_name: required
tax_id: optional, masked at rest
w9_received: required, boolean
w9_received_date: optional, ISO 8601 date
sanctions_check_date: optional, ISO 8601 date
sanctions_check_disposition: optional, one of [cleared, blocked, pending]
payment_terms: optional, one of [net-15, net-30, net-45, net-60, net-90, immediate, other]
preferred_payment_method: optional
status: required, one of [active, inactive, blocked]
```

## internal-audit-finding

A finding from internal audit. Tracked as a first-class entity for remediation.

```yaml
type: internal-audit-finding
finding_id: required, unique within tenant
audit_cycle: required, identifier of the audit engagement
finding_title: required
severity: required, one of [observation, low, medium, high, critical]
control_referenced: optional, list of control_id
finding_date: required, ISO 8601 date
finding_description: required, plain text
recommendation: required, plain text
management_response: optional, plain text
remediation_owner: optional, person reference
remediation_due_date: optional, ISO 8601 date
remediation_status: required, one of [open, in-progress, remediated, accepted-risk, closed]
```

## board-pack-decision

A decision recorded in the board pack. Drives the audit committee version trail.

```yaml
type: board-pack-decision
decision_id: required, unique within tenant
board_meeting_date: required, ISO 8601 date
board_pack_version: required, semver or build identifier
decision_text: required, plain text
decision_owner: required, person reference (the executive accountable)
materiality: required, one of [routine, material, highly-material]
supporting_evidence: required, list of evidence_id (must be non-empty for material and highly-material decisions)
audit_committee_review_required: required, boolean
audit_committee_reviewed_date: optional, ISO 8601 date
audit_committee_disposition: optional, one of [approved, conditioned, deferred, declined]
```

## Schema enforcement

The substrate enforces required fields at write time. Documents missing required fields are rejected with a recoverable error. Optional fields are not enforced but are validated for type if present.

The materiality enforcement on `deal`, `journal-entry`, and `board-pack-decision` is load-bearing for SOX 404 evidence; do not weaken it locally without documenting the override in `retention-policy`.
