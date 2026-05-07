# Decision audit: PHI handling

A PHI mishandling event is a HIPAA breach, a HITECH Act notification obligation, and (in many cases) a regulator referral and a class-action substrate. This document specs the firewall that runs at every PHI write, every PHI access, and every cross-boundary move.

## Rule

Every document written with `phi_tagged: true` MUST declare which of the 18 HIPAA identifiers (per 45 CFR 164.514(b)(2)) are present. The substrate verifies the declaration at write time; a document whose body contains an identifier not declared in `phi_identifiers_present` is rejected with a recoverable error. Every PHI access is logged with role, encounter or matter context, and disposition.

## The 18 HIPAA identifiers

Per 45 CFR 164.514(b)(2), the safe-harbor de-identification standard. Each identifier is numbered in the substrate's `phi_identifiers_present` list:

1. Names
2. All geographic subdivisions smaller than a state (street address, city, county, precinct, ZIP code at any granularity finer than the first three digits when the geographic unit is small enough that the first three digits map to <20,000 people)
3. All elements of dates (except year) directly related to an individual: birth date, admission date, discharge date, death date, all ages over 89 and all dates indicative of such age
4. Telephone numbers
5. Fax numbers
6. Email addresses
7. Social Security numbers
8. Medical record numbers
9. Health plan beneficiary numbers
10. Account numbers
11. Certificate or license numbers
12. Vehicle identifiers and serial numbers, including license plate numbers
13. Device identifiers and serial numbers
14. Web URLs
15. IP addresses
16. Biometric identifiers, including finger and voice prints
17. Full-face photographs and any comparable images
18. Any other unique identifying number, characteristic, or code (catch-all)

The substrate ships a regex-and-NER detector for identifiers 1, 4, 5, 6, 7, 14, 15. Identifiers 2, 3 require contextual extraction; the substrate flags candidate spans and asks for declaration. Identifiers 8 through 13 require enumeration of the covered entity's identifier patterns at install time. Identifiers 16 through 18 cannot be auto-detected reliably; the entity is responsible for declaring them.

## What runs at write

When a document is written with `phi_tagged: true`:

1. **Detection sweep.** Run the auto-detectable identifier scan on the document body. Compare against `phi_identifiers_present`.
2. **Coverage check.** Every detected identifier must be declared. Undeclared detections block the write.
3. **Tenant boundary check.** PHI documents cannot reference patients outside the writing user's authorized tenant scope. The substrate refuses cross-tenant PHI writes.
4. **Sensitive-subset stamp.** If the document contains identifiers tied to behavioral health, HIV status, substance-use treatment, or reproductive health, the document is stamped `sensitive: true` and special access controls apply (see `42 CFR Part 2` handling note below).
5. **Minimum-necessary review.** The substrate flags documents that include identifiers not strictly necessary for the document's stated purpose, per 45 CFR 164.502(b). The flag is advisory, not blocking; the privacy officer decides.

## What runs at access

Every read of a `phi-tagged-doc`, `patient-scoped-fact`, or `clinical-decision` document logs:

- `timestamp` (UTC, server-side)
- `accessor` (person reference)
- `accessor_role` (provider, billing, scheduling, research, audit, other)
- `purpose` (treatment, payment, healthcare operations, research, audit, marketing, other) per 45 CFR 164.506 / 164.508 categories
- `encounter_id` (when access is encounter-scoped)
- `disposition` (accessed, declined-by-policy, blocked-by-firewall, escalated)
- `auth_basis` (treatment-relationship, BAA, written authorization, court-order, other)

The access log retention follows `retention/defaults.md` (6 years from access). The log is itself PHI; access to the access log is itself logged (recursive logging stops at depth 2; meta-meta access is stamped but not deep-logged).

## Cross-boundary moves

PHI cannot move out of a tenant boundary except via:

- **BAA-stamped channel.** Egress to a destination registered as a `baa-counterparty` with a current, non-expired BAA. The substrate refuses egress to any destination not pre-registered.
- **Written authorization.** A patient or personal representative authorizes specific disclosure per 45 CFR 164.508. The authorization is itself a `phi-tagged-doc` and is referenced in the egress log.
- **Required-by-law disclosure.** Court order, subpoena, or public-health reporting per 45 CFR 164.512. The disclosure is logged with the legal basis.
- **De-identification.** The document has been processed through the safe-harbor pipeline (all 18 identifiers removed or generalized) OR through expert determination per 164.514(b)(1). De-identified output carries `phi_tagged: false` and `de_identification_method` frontmatter.

## 42 CFR Part 2 handling

Substance-use disorder treatment records under 42 CFR Part 2 have stricter consent and re-disclosure rules than HIPAA. The substrate v1 does NOT auto-detect Part 2 records and does NOT enforce Part 2 consent flows. Covered entities that handle Part 2 data should configure a separate Part 2 store at install time and route Part 2 documents to that store; the EHR connectors (`epic-fhir.md`, `cerner-fhir.md`) refuse to pull charts flagged Part 2 unless explicitly configured.

## Audit log

Every PHI handling decision logs:

- The five fields above (timestamp, accessor, accessor_role, purpose, disposition)
- The document's `phi_identifiers_present` list (frozen at access time)
- The applicable BAA, authorization, or legal basis (frozen at access time)
- The decision rationale when disposition is `declined-by-policy` or `blocked-by-firewall`

The audit log is content-addressable and append-only. Edits to a log entry create a new entry referencing the old; the original is preserved.

## What this firewall does NOT do

- It does not replace the privacy officer or the security officer. The covered entity's officers still own the policy and the breach response; the substrate raises and logs.
- It does not handle HIPAA Security Rule technical safeguards (encryption at rest, access controls, audit hardware) directly; those are infrastructure concerns the entity addresses outside the substrate.
- It does not handle marketing-disclosure or sale-of-PHI-disclosure flows beyond logging the disposition; explicit authorization is the entity's responsibility.
- It does not decode 42 CFR Part 2 records.

## Provenance

The firewall enforces 45 CFR 164.514 (de-identification standard), 164.502 (uses and disclosures), 164.506 (treatment, payment, operations), 164.508 (authorizations), 164.512 (required-by-law), 164.530(j) (documentation retention), and HITECH Act §13402 (breach notification trigger). State variations apply; the substrate layers stricter state rules where applicable per the covered entity's jurisdictional configuration.
