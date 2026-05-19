---
name: vertical-healthcare
description: Pre-configured healthcare vertical pack for the ai-brain-starter substrate. Ships typed-memory categories for patient-scoped facts, clinical decisions, PHI-tagged docs, BAA counterparties, and breach notification; HIPAA-aligned retention defaults plus per-state add-ons; connectors for Epic FHIR, Cerner FHIR, and Salesforce Health Cloud; decision-audit patterns for PHI handling against the 18 HIPAA identifiers and clinical-decision evidence chains. Use when onboarding a covered entity, business associate, or health system that needs the substrate to come pre-shaped to HIPAA, BAA, and clinical-decision audit obligations.
trigger: /vertical-healthcare
argument-hint: "init | status | rebuild [--tenant <id>]"
---

# /vertical-healthcare

A pre-configured pack that turns the empty substrate into a healthcare-ready system in one install. The pack ships typed-memory categories that match how patient data, clinical decisions, and BAA relationships move through a covered entity; FHIR connectors for the two dominant EHR vendors; HIPAA retention defaults plus per-state add-ons; and decision-audit patterns that enforce PHI handling at the 18-identifier level and produce a verifiable clinical-decision evidence chain.

## Why this exists

Healthcare organizations operate under the strictest data-handling regime in commercial software: HIPAA, the HITECH Act, state-level add-ons (California CMIA, Texas HB 300, New York SHIELD), plus a forest of payer and joint-commission rules. A blank substrate install forces every covered entity to re-derive the same PHI-handling firewall and the same retention rules.

This pack ships the firewall and the rules so the org can spend day one on its own clinical workflows rather than on schema design and HIPAA mapping.

## What this pack sets up

| Layer | What ships | Where it lands |
|---|---|---|
| Schema | 7 typed-memory categories with frontmatter contracts | `schema/typed-memory-categories.md` |
| Connectors | Epic FHIR, Cerner FHIR, Salesforce Health Cloud specs and SMART-on-FHIR auth | `connectors/*.md` |
| Retention | HIPAA 6-year baseline, per-state add-ons, breach-notification log retention | `retention/defaults.md` |
| Decision audit | PHI handling against 18 HIPAA identifiers, clinical-decision evidence chains | `decision-audit/*.md` |

Nothing is auto-applied. Drafts stage under `drafts/`; the privacy officer, security officer, and clinical informatics lead review and merge.

## Categories shipped

- patient-scoped-fact
- clinical-decision
- phi-tagged-doc
- baa-counterparty
- retention-policy
- hipaa-incident
- breach-notification

## Connectors shipped

- `connectors/epic-fhir.md` : Epic via FHIR R4; SMART-on-FHIR auth; resource types covered
- `connectors/cerner-fhir.md` : Oracle Cerner via FHIR R4; SMART-on-FHIR auth; resource types covered
- `connectors/salesforce-health-cloud.md` : Salesforce Health Cloud connector; OAuth and Salesforce platform auth

## Retention defaults shipped

- HIPAA records: 6 years from creation or last effective date (45 CFR 164.530(j)).
- California CMIA add-on: 7 years for medical records.
- Minor patient records: until age of majority + retention floor (varies by state; California: age 18 + 7 years; Texas: age 18 + 7 years).
- Breach-notification log: 6 years.
- Decedent records: 50 years post-death (HIPAA decedent rule).

See `retention/defaults.md`.

## Decision-audit patterns shipped

- `decision-audit/phi-handling.md` : every PHI tag is verified at write time against the 18 HIPAA identifiers; PHI cannot cross tenant boundaries; audit log is BAA-default; every PHI access is logged with role, matter (encounter or case), and disposition.
- `decision-audit/clinical-decision-trail.md` : every clinical recommendation has a chain: input data, decision, decision-maker, supporting evidence, alternatives considered.

## When to use this pack

- A covered entity is installing the substrate.
- A business associate handling PHI on behalf of a covered entity is installing.
- A health system is consolidating across hospitals or clinics on a shared substrate.
- A digital health vendor needs HIPAA-compliant memory for clinical workflows.

## When NOT to use this pack

- Pure life-sciences research without PHI (use a thinner subset).
- Veterinary medicine (the schema would need extensive remapping).
- Non-clinical health-tech without patient data (skip; use the generic substrate).

## Install

```bash
/vertical-healthcare init
```

The init command:

1. Verifies the substrate is installed and at a compatible version.
2. Stages all schema, connector, retention, and decision-audit files under `drafts/healthcare/`. Nothing is auto-applied; the privacy officer, security officer, and clinical informatics lead must review and merge.
3. Prints a review checklist that names every file staged and the HIPAA / state-law citation each enforces.
4. Stops. The covered entity reviews and merges manually.

## Status

```bash
/vertical-healthcare status
```

Reports which categories are live, which connectors are configured, BAA execution status for each downstream counterparty, and any PHI access in the past 30 days that lacked a logged disposition.

## What this pack does NOT include

- Clinical decision support (CDS) algorithms (out of scope; the pack tracks decisions, it does not make them).
- Coding and billing workflows (use the finance pack plus a healthcare-specific billing layer).
- Pharmacy or DEA-controlled-substance tracking (out of scope for v1).
- Clinical trial data (use a research-specific schema; HIPAA does not cover de-identified research data the same way).
- 42 CFR Part 2 substance-use-disorder protections (these are stricter than HIPAA; v1 does not encode them).

## Provenance

Every retention default cites the rule. Every connector cites the FHIR or platform documentation URL. Every decision-audit pattern cites the HIPAA section, HITECH provision, or state law. Drafts without provenance are gaps.
