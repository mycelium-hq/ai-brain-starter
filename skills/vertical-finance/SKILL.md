---
name: vertical-finance
description: Pre-configured finance vertical pack for the ai-brain-starter substrate. Ships typed-memory categories for deals, counterparties, SOX 404 controls, and audit evidence; retention defaults aligned with SOX, SEC 17a-4, and per-jurisdiction variations; connectors for Workday, NetSuite, and SAP Finance; decision-audit patterns for SOX evidence stamping and board-pack version trails. Use when onboarding a CFO organization, internal audit team, or finance operations group that needs the substrate to come pre-shaped to financial reporting and audit obligations.
trigger: /vertical-finance
argument-hint: "init | status | rebuild [--control <id>]"
---

# /vertical-finance

A pre-configured pack that turns the empty substrate into a finance-ready system in one install. The pack ships typed-memory categories that match the shape of a finance organization (deals, counterparties, SOX controls, audit evidence, journal entries, board decisions), connectors for the three ERP and HRIS platforms most F500s already license, retention defaults that map to SOX 404 evidence retention and SEC broker-dealer rules, and decision-audit patterns that produce a tamper-evident trail from board pack back to source.

## Why this exists

Finance organizations operate under continuous audit pressure. Every material decision needs a traceable evidence chain. Every external auditor cycle re-asks the same questions: where is the SOX 404 evidence, who approved the journal entry, why was this control overridden, what version of the board pack went to the audit committee.

A blank substrate install forces every finance org to re-derive the same evidence-stamping conventions and the same retention rules. This pack ships the conventions and the rules so the org can spend day one on its own controls map rather than on schema design.

## What this pack sets up

| Layer | What ships | Where it lands |
|---|---|---|
| Schema | 9 typed-memory categories with frontmatter contracts | `schema/typed-memory-categories.md` |
| Connectors | Workday, NetSuite, SAP Finance specs and auth flows | `connectors/*.md` |
| Retention | Per-category retention rules mapped to SOX 404, SEC 17a-4, and jurisdiction variations | `retention/defaults.md` |
| Decision audit | SOX 404 evidence stamping and board-pack version trails | `decision-audit/*.md` |

Nothing is auto-applied. The pack stages drafts under `drafts/` and prints the path; the controller, internal audit lead, and CFO review and accept before merging into the production memory layer.

## Categories shipped

- deal
- counterparty
- sox-control
- audit-evidence
- journal-entry
- expense-policy
- vendor
- internal-audit-finding
- board-pack-decision

See `schema/typed-memory-categories.md` for required and optional frontmatter.

## Connectors shipped

- `connectors/workday.md` — Workday Financial Management and HCM
- `connectors/netsuite.md` — NetSuite ERP via SuiteTalk REST
- `connectors/sap-finance.md` — SAP S/4HANA Finance via OData and CDS views

## Retention defaults shipped

- SOX 404 evidence: 7 years from fiscal year end (Sarbanes-Oxley Section 802 baseline).
- SEC 17a-4 broker-dealer records: 6 years (3 years easily accessible, additional 3 years archived).
- Audit-committee minutes and supporting evidence: 7 years (Sarbanes-Oxley Section 103 baseline).
- Per-jurisdiction overrides for EU (GDPR record-keeping), UK (FCA), Canada (CRA), Singapore (MAS), and Japan (J-SOX).

See `retention/defaults.md` for the full table.

## Decision-audit patterns shipped

- `decision-audit/sox-404-evidence.md` — every material decision gets a SOX 404 evidence stamp linking decision text, decision-maker, date, and supporting documents in the typed-memory graph.
- `decision-audit/board-pack-trail.md` — every board pack draft is versioned in Git; every quote in the pack traces back to a decision in the typed-memory graph; auditors can replay version history.

## When to use this pack

- A CFO organization is installing the substrate.
- Internal audit is building a continuous-audit knowledge layer.
- The controller's office is consolidating evidence repositories ahead of an external audit cycle.

## When NOT to use this pack

- Pure FP&A or treasury without audit obligations. Use a thinner subset.
- Public-company secondary-offering or transaction work; the legal pack handles transactional materials better.
- Pure HR or talent management; that lives in the broader Workday connector but is not the focus of this pack.

## Install

```bash
/vertical-finance init
```

Stages drafts, prints a review checklist, stops.

## Status

```bash
/vertical-finance status
```

Reports which categories are live, which connectors are configured, which retention rules have local overrides, and which SOX controls have evidence gaps in the past 90 days.

## What this pack does NOT include

- Specific control catalogs (the org maps its own).
- Tax provision workflows (out of scope for v1; the journal-entry category is a hook).
- Treasury workflows beyond cash-position evidence (out of scope for v1).
- Investor relations beyond board-pack evidence (out of scope for v1).
- Audit firm portals (Connect, Confirmation.com, etc.) beyond inbound document feeds.

## Provenance

Every retention default cites the rule. Every connector cites the API documentation URL and auth scheme. Every decision-audit pattern cites the SOX section, SEC rule, or other regulatory anchor. Drafts without provenance are gaps; surface them in review.
