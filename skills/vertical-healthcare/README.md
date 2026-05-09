# Vertical pack: healthcare

A drop-in configuration pack that turns the ai-brain-starter substrate into a healthcare-ready system: PHI handling, clinical-decision trails, BAA counterparty tracking, and connectors for Epic, Cerner, and Salesforce Health Cloud.

## Who this is for

- Covered entities (hospitals, health systems, clinics, payers) installing the substrate.
- Business associates handling PHI on behalf of covered entities.
- Digital health vendors needing HIPAA-compliant memory for clinical workflows.

## What is in the box

| Layer | File | What it gives you |
|---|---|---|
| Schema | `schema/typed-memory-categories.md` | 7 typed-memory categories: patient-scoped-fact, clinical-decision, phi-tagged-doc, baa-counterparty, retention-policy, hipaa-incident, breach-notification. |
| Connectors | `connectors/epic-fhir.md`, `connectors/cerner-fhir.md`, `connectors/salesforce-health-cloud.md` | FHIR R4 endpoints, SMART-on-FHIR auth, resource coverage. |
| Retention | `retention/defaults.md` | HIPAA 6-year baseline plus per-state add-ons. |
| Decision audit | `decision-audit/phi-handling.md`, `decision-audit/clinical-decision-trail.md` | 18-HIPAA-identifier firewall and clinical-decision evidence chains. |

## Install

```bash
/vertical-healthcare init
```

Stages drafts, prints a review checklist, stops.

## Read first

If you only have time to skim one file, read `decision-audit/phi-handling.md`. PHI handling is the load-bearing rule; if it does not match your privacy officer's posture, the rest will not fit.

## What this pack does NOT include

- Clinical decision support algorithms.
- Coding and billing workflows.
- Pharmacy or DEA-controlled-substance tracking.
- Clinical trial data handling.
- 42 CFR Part 2 substance-use-disorder protections.

## Roadmap

- v2: 42 CFR Part 2 layer for substance-use-disorder protected records.
- v2: DEA-controlled-substance tracking.
- v2: Joint Commission accreditation evidence layer.
- v3: Pharmacy and 340B compliance layer.

## Support

Issues and pack-specific questions belong on the ai-brain-starter repository. The pack is open source; HIPAA compliance remains the covered entity's obligation.
