---
status: accepted
date: 2026-05-09
---

## Context

The substrate teaches a pattern (skills, hooks, vault structure, install scripts, episodic memory). Downstream maintainers may operate paid runtimes that build on the substrate. There has been recurring pressure to ship downstream-runtime features (paid connectors, workflow content, audit analytics) directly in the substrate, on the theory that "more value out of the box" wins more users.

## Decision

The substrate is bounded to teaching the pattern. Specifically OUT OF SCOPE for the public substrate:

1. Paid workflow content (per-vertical question packs, redlining templates, compliance evidence templates)
2. Multi-tenant connectors (any per-tenant credential isolation, audit logging, rate-limit isolation)
3. Audit analytics for legal-grade defensibility (hash-chain integrity, append-only retention guarantees)
4. Hosted billing / per-tenant SLA management

In scope and shipped publicly:
- Skills + hooks + extractor templates that any single-user vault can run
- Single-user connectors (OAuth-per-install Slack/Notion/Linear/Gmail/GitHub ingest)
- Closed-loop episodic-to-procedural memory architecture (`Meta/Learnings/` + promotion script)
- The teaching pattern itself (this ADR is part of it)

## Why

- The substrate's value is teaching the pattern; users do not need a hosted runtime to extract that value
- Downstream-runtime features are per-vertical and per-customer; shipping them publicly either over-promises on the substrate or leaks per-vertical work product
- Multi-tenant connectors carry per-tenant credential and rate-limit complexity that single-user public install cannot meaningfully model
- Audit defensibility is a legal-grade claim; half-shipped audit code in a public substrate becomes liability when users build legal claims on it without the runtime's hosting + retention + isolation guarantees
- Open-core split is the stable commercial position: substrate-as-pattern + runtime-as-moat. Open-substrate + paid-runtime-on-top is unstable (competitors fork the runtime); open-everything is unstable (no commercial sustainment)

## Consequences

- Substrate maintainers run downstream private repos for runtime-class features
- Hookify-style rules (`warn-public-repo-create`, `warn-mit-on-content-repo`) belong in maintainer forks, not in the substrate itself
- The CONTEXT.md "Open-core boundary" term defines this and survives across maintainer rotations
- This is permanent. Reversal would require a fundamental shift in commercial model (pivot to consulting-only or training-only) or a workflow becoming so commoditized that no paying client values the runtime version
