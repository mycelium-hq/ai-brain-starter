# Retention defaults: legal vertical

These defaults map to ABA Model Rule 1.15 and the most common state-bar variations. They are starting points, not legal opinions; verify against your bar association before going live.

A retention rule is a `(category, matter-type, trigger, period)` tuple. The substrate enforces the rule at the category level by default; matter-type modifiers override.

## Default table

| Category | Matter type | Trigger | Default retention | Basis |
|---|---|---|---|---|
| matter | any | matter close | 7 years | ABA Model Rule 1.15 (client property), most state-bar minimums |
| privilege-tagged-doc | any | matter close | 7 years | ABA Model Rule 1.15, attorney-client privilege durability |
| privilege-tagged-doc | litigation | matter close | 10 years | Statute of repose for legal malpractice in many jurisdictions |
| billing-event | any | matter close | 7 years | IRS general business records (26 CFR 1.6001), state-bar minimums |
| deposition-note | litigation | matter close | 10 years | Appellate windows plus malpractice statute of repose |
| deposition-note | regulatory | matter close | 10 years | SEC and state regulator look-back windows |
| court-deadline | any | matter close | retained with matter | tied to matter retention |
| client | any | last matter close | 7 years after last matter | ABA Model Rule 1.15 client identification durability |
| opposing-counsel | any | matter close | 7 years | conflicts-check institutional memory |
| retention-policy | any | policy supersession | indefinite | governance audit trail |

## State-bar variations

Common variations the firm should review before going live. This is not exhaustive; consult the firm's compliance officer.

| Jurisdiction | Variation | Effect |
|---|---|---|
| California | Cal. Rules of Prof. Conduct 1.15 (formerly Rule 4-100) | 5-year minimum on client trust account records; documents per ABA baseline |
| New York | NY Rules of Prof. Conduct 1.15 | 7-year minimum; trust account records 7 years |
| Texas | Tex. Disc. Rules of Prof. Conduct 1.14 | 5-year minimum on client property records |
| Florida | Fla. Rules of Prof. Conduct 5-1.2 | 6-year minimum on trust account records |
| Illinois | Ill. Rules of Prof. Conduct 1.15(a) | 7-year minimum on trust account and client property records |

When the firm operates in multiple jurisdictions, the longest applicable retention wins. The substrate enforces the maximum across all matter jurisdictions tagged on the matter record.

## Matter-type modifiers

| Matter type | Modifier | Reason |
|---|---|---|
| litigation | +3 years on depositions and trial materials | appellate windows, malpractice repose |
| regulatory | +3 years on agency-facing materials | regulator look-back windows |
| ip | +5 years on patent files | patent term considerations |
| transactional (M&A) | +3 years on closing binders | post-closing claim windows |
| employment | +3 years on personnel-related work product | employment claim statutes of limitations |

Modifiers stack additively on top of the base retention.

## Override mechanism

A firm can override any default by writing a `retention-policy` document with `overrides_default: true`. The override applies only within the firm's local install; the pack's defaults remain canonical for new installs and for documentation purposes.

## What is NOT in this table

- Trust account records: the pack does not ship trust accounting workflows in v1. When trust accounting ships, retention rules will be added here.
- Privileged-doc retention beyond matter close in jurisdictions with permanent retention requirements (e.g., minor-client matters in some states): the firm sets these as overrides at install time.
- Records subject to litigation hold: a hold suspends the retention clock; the substrate has a hold mechanism but the retention table does not encode hold logic.

## Provenance

Every entry in the table cites the rule it maps to. ABA Model Rules are public; state rules cite the rule number and the most current revision. Verify against the firm's bar before go-live; we ship defaults, the firm owns compliance.
