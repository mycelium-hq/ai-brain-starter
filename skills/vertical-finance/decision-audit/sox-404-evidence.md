# Decision audit: SOX 404 evidence stamping

Every material decision needs a SOX 404 evidence stamp. The stamp is the audit trail that lets internal audit, external audit, and the audit committee replay the decision and verify it was supported when it was made.

## Rule

Every `deal`, `journal-entry`, and `board-pack-decision` flagged `material` or `highly-material` MUST have at least one `audit-evidence` record linked at the time the decision is finalized. The substrate refuses to mark the decision as accepted (or the journal entry as approved, or the deal as signed) until the evidence link exists.

## What the stamp captures

For each material decision, the substrate writes a stamp record containing:

- `decision_id` (FK to the decision record)
- `decision_text` (full text, frozen at stamp time)
- `decision_owner` (the executive accountable, frozen at stamp time)
- `decision_date` (frozen)
- `evidence_ids` (list of audit-evidence records, each with hash_sha256 frozen)
- `control_ids` (list of sox-control references)
- `stamp_timestamp` (UTC, generated server-side)
- `stamp_hash` (SHA256 over the canonical JSON of the above)

The stamp is content-addressable. Any later edit to the underlying decision text creates a new record; the original stamp remains for the auditor to read.

## What "material" means

Materiality is configurable per tenant. The default thresholds:

- Journal entry: USD 50,000 single entry, or any entry that crosses an accounting policy threshold (revenue recognition, lease accounting, impairment).
- Deal: any deal with `materiality: material` or `materiality: highly-material` flagged at the deal record.
- Board-pack decision: any decision with `materiality: material` or `materiality: highly-material` flagged at the decision record.

The materiality flag on the decision is the operator's call (or the audit committee's). The substrate enforces the stamp requirement when the flag is set; it does not set the flag on its own.

## Implementation

The stamp logic lives in three places:

1. **Decision-finalization hook.** When the operator marks a `deal`, `journal-entry`, or `board-pack-decision` as accepted, the hook checks for at least one linked `audit-evidence` record. Missing evidence blocks finalization with a recoverable error naming the missing link.
2. **Evidence-content hash.** Every `audit-evidence` record carries `hash_sha256`. The hash is computed at capture time and frozen. If the underlying file changes, the hash mismatch surfaces as a tamper alert.
3. **Stamp record write.** The stamp record is written to a tamper-evident append-only log under the tenant's audit scope. The log uses content-addressable storage; once a stamp is written, it cannot be edited or deleted (only appended-around).

## Audit log queries

Internal audit, external audit, and the audit committee can query:

- "Show me every material decision in fiscal Q3 with the evidence chain."
- "Show me every journal entry above threshold without a control reference."
- "Show me every stamp where the evidence hash mismatch was detected."
- "Show me every stamp written after the decision date (lagging evidence)."

The queries run against the stamp log and the typed-memory graph; they do not require direct ERP access.

## Lagging evidence

The substrate does not refuse a stamp where the evidence is captured after the decision date (some workflows require post-hoc evidence). Lagging evidence is logged in the stamp's `evidence_lag_days` field; the audit committee can set a policy that lagging evidence beyond N days requires committee review.

## What this stamp does NOT do

- It does not opine on whether the evidence is sufficient. The auditor still reviews the evidence at the cycle. The stamp guarantees the evidence existed at decision time; the auditor judges quality.
- It does not handle multi-entity rollup (consolidated decisions across subsidiaries). That is a parent-child tenant problem; the v1 pack assumes single-tenant scope.
- It does not handle compensating-control logic (when one control fails, another covers). Compensating-control mapping lives in the control catalog, not in the stamp.

## Provenance

Sarbanes-Oxley Section 404 requires management's annual assessment of the effectiveness of internal control over financial reporting. PCAOB Auditing Standard 2201 specifies the evidence requirements for the auditor. SEC interpretive guidance (Release 33-8810) further specifies management's evidence obligations. The stamp pattern in this pack supports those obligations; it does not replace the auditor's professional judgment.
