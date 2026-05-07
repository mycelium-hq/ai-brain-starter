# Decision audit: clinical-decision trail

A clinical decision without a defensible evidence chain is a malpractice exposure, a peer-review finding, and a payer-audit denial. This document specs the chain the substrate enforces for every `clinical-decision` write.

## Rule

Every `clinical-decision` document MUST have a non-empty `input_data_references` list at write time. The substrate refuses to mark a clinical decision as final until the chain is complete: input data, decision, decision-maker, supporting evidence (when claimed), alternatives considered (when documented), and the patient or family participation flag (when applicable).

## The chain

Every clinical decision carries:

1. **Input data.** What did the decision-maker know at the time? `input_data_references` lists every `patient-scoped-fact` and `phi-tagged-doc` the decision-maker reviewed. The list is non-empty by enforcement.
2. **The decision itself.** `decision_text` (frozen at write time), `decision_type` (one of: diagnosis, treatment, medication, procedure, referral, discharge, care-plan, other), `decision_date`.
3. **Decision-maker.** `decision_maker` is the credentialed provider accountable. The substrate verifies `decision_maker` is currently credentialed for the matter type at the encounter's facility (via the credentialing connector when configured; otherwise warns).
4. **Supporting evidence.** `supporting_evidence_references` lists clinical guidelines, prior-case references, or literature the decision-maker leaned on. Optional but strongly encouraged for non-routine decisions.
5. **Alternatives considered.** `alternatives_considered` (free text or list) records what else was on the table. Optional; required for `treatment` and `procedure` decisions where the chosen path is non-default per the institution's clinical pathway.
6. **Shared decision-making.** `shared_decision_making` (boolean) flags decisions where the patient or personal representative actively participated. The substrate does not gate on the value but downstream queries (informed-consent dashboards, patient-experience metrics) depend on it.

## What runs at write

On every `clinical-decision` write:

1. **Schema check.** Required frontmatter present (`decision_id`, `patient_internal_id`, `encounter_id`, `decision_text`, `decision_type`, `decision_date`, `decision_maker`, `input_data_references`).
2. **Reference resolution.** Every `input_data_references` ID resolves to a real document. Dangling references block the write.
3. **Credentialing check.** `decision_maker` is verified as credentialed for `decision_type` at the encounter's facility. If credentialing connector unavailable, the substrate warns and proceeds; the privacy/clinical informatics officer reviews on the next audit cycle.
4. **Encounter validity.** `encounter_id` resolves to a current or recently-closed encounter for the same `patient_internal_id`. Cross-patient encounter references block.
5. **Time consistency.** `decision_date` must be within the encounter's open window or no more than the institution-configured grace period (default: 72 hours after encounter close; covers retrospective documentation).
6. **Stamp generation.** A stamp record is written: SHA256 over the canonical JSON of the chain, `stamp_timestamp` (server UTC), `stamp_hash`. Edits to the underlying decision create new stamps; original stamps are preserved.

## Reviewer chain (when applicable)

Decisions flagged for peer review (via `peer_review_required: true` or by institution policy) carry an additional `reviewer_chain` log:

- `reviewer` (person reference)
- `reviewer_role` (peer reviewer, attending, medical director, quality)
- `review_timestamp`
- `review_disposition` (concur, concur-with-comment, dissent, refer-to-committee)
- `review_comment` (when disposition includes comment)

The reviewer chain is append-only. A dissenting review does NOT block the original decision (the original decision-maker is accountable) but it surfaces in quality dashboards and triggers an institution-defined escalation.

## What this trail does NOT do

- It does not validate clinical correctness. The substrate does not opine on whether a diagnosis is right; it captures who decided, on what basis, with what alternatives, with what review.
- It does not enforce institutional clinical pathways. Pathway enforcement is a separate hook the institution configures; this trail captures whether a pathway was followed.
- It does not handle group-decision scenarios (tumor boards, multidisciplinary teams) without a specialized adapter; v1 captures the accountable decision-maker plus an optional `team_members` list.
- It does not auto-detect deviations from prior decisions on the same patient; trend analysis is a query-layer concern.

## Audit log

For every `clinical-decision` write, finalization, edit, or revocation, the substrate logs:

- `timestamp` (UTC, server-side)
- `actor` (person reference)
- `decision_id`
- `event_type` (write, finalize, edit, revoke, peer-review)
- `chain_state_before` (hash of the prior canonical JSON; null on first write)
- `chain_state_after` (hash of the new canonical JSON)
- `disposition` (success, blocked, error, requires-review)

The log is retained per `retention/defaults.md` (6 years from event date, longer when state-bar variations apply).

## Provenance

This trail enforces the patient-record completeness expectations under 45 CFR 164.526 (right to amend), the documentation requirements implicit in 45 CFR 164.530(j), CMS Conditions of Participation for hospitals (42 CFR 482.24(c) on medical record content), and the Joint Commission record-of-care standards (RC.02.01.01 series). State medical-board record-content rules apply on top; the institution layers them at install via `retention-policy` documents.
