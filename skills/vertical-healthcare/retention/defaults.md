# Retention defaults: healthcare vertical

These defaults map to HIPAA's documentation retention requirement at 45 CFR 164.530(j), the HITECH Act breach-notification record requirements, and the most common state-level add-ons. They are starting points, not legal opinions; verify against the covered entity's privacy officer, security officer, and counsel before going live.

A retention rule is a `(category, trigger, period)` tuple. The substrate enforces the rule at the category level by default; per-state and matter-type modifiers stack additively.

## Default table

| Category | Trigger | Default retention | Basis |
|---|---|---|---|
| patient-scoped-fact | last access OR patient discharge | 6 years from later | 45 CFR 164.530(j) (HIPAA documentation retention) |
| clinical-decision | decision date | 6 years from decision date | 45 CFR 164.530(j); state medical-records add-ons may extend |
| phi-tagged-doc | document creation | 6 years from creation | 45 CFR 164.530(j) |
| phi-tagged-doc | psychotherapy note subset | 7 years from creation | 45 CFR 164.508(a)(2) special handling, plus state professional licensing rules |
| baa-counterparty | BAA termination | 6 years from termination | 45 CFR 164.504(e); BAA recordkeeping floor |
| retention-policy | policy supersession | indefinite | governance audit trail |
| hipaa-incident | incident closure | 6 years from closure | 45 CFR 164.530(j) |
| breach-notification | notification date | 6 years from notification | 45 CFR 164.414 (HITECH burden-of-proof requirement) |

## State-level add-ons

The covered entity reviews and applies these on top of the HIPAA baseline. The substrate enforces the maximum across all applicable jurisdictions.

| Jurisdiction | Statute | Effect |
|---|---|---|
| California | Cal. Health & Safety Code § 123145 (hospital records); Cal. Civ. Code § 56 (CMIA) | Adult medical records: 7 years post-discharge; minor patient records: until age 19 OR 7 years post-discharge, whichever is later |
| Texas | Tex. Health & Safety Code § 241.103; Tex. Med. Records Privacy Act (HB 300) | Adult records: 10 years from last treatment; minor records: until age 20 |
| New York | NY Pub. Health Law § 18; 10 NYCRR 405.10 | Adult records: 6 years (10 years for hospital records); minor records: 6 years post-majority |
| Florida | Fla. Stat. § 458.331(1)(m); Fla. Admin. Code 64B8-10.002 | Adult records: 5 years from last contact; minor records: until age 18 + 5 years |
| Massachusetts | 243 CMR 2.07 (Board of Registration in Medicine) | Adult records: 7 years from last contact; minor records: until age 24 |

When the covered entity operates in multiple states, the longest applicable retention wins. The substrate computes the maximum across the patient's tagged jurisdictions and the encounter's site jurisdiction.

## Special-case modifiers

| Case | Modifier | Reason |
|---|---|---|
| Decedent records | retain 50 years post-death | 45 CFR 164.502(f) HIPAA decedent rule |
| Minor patients | retain until age of majority + state baseline | 45 CFR 164.530(j) plus state-bar variations |
| 42 CFR Part 2 (SUD treatment) | separate access logs retained per Part 2 | Distinct from HIPAA; consult Part 2 specialist before configuring |
| Research-consent records | retain for life of research project + 6 years | Common Rule 45 CFR 46.115; HIPAA research authorization 164.508(b) |
| Psychotherapy notes (separate from medical record) | 7 years | Higher floor due to special-handling status under 164.508(a)(2) |

Modifiers stack additively on the base retention.

## Override mechanism

The covered entity overrides any default by writing a `retention-policy` document with `overrides_default: true` and a citation. The override applies only within the entity's local install; pack defaults remain canonical for new installs and for documentation purposes.

State variations should be applied via `retention-policy` overrides at install rather than by editing this file.

## What is NOT in this table

- Trust account or financial records: out of scope for this pack; see vertical-finance.
- 42 CFR Part 2 records: the substrate has separate access logs for Part 2 but does not encode Part 2 retention rules in this table; the covered entity engages a Part 2 specialist before going live.
- Records subject to HIPAA litigation hold or DOJ investigation: a hold suspends the retention clock; the substrate has a hold mechanism but the table does not encode hold logic.
- Joint Commission accreditation records: facility-specific; the entity sets these as overrides per its accreditation cycle.
- Workers' compensation records: state-specific and not always HIPAA-covered; out of scope here.

## Provenance

Every entry in the table cites the rule it maps to. CFR citations are public; state citations cite the statute or administrative code section. Verify against the covered entity's privacy officer and counsel before go-live; the pack ships defaults, the entity owns compliance.
