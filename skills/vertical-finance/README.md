# Vertical pack: finance

A drop-in configuration pack that turns the ai-brain-starter substrate into a finance-ready system: deal tracking, SOX 404 evidence stamping, audit-committee trails, and connectors for Workday, NetSuite, and SAP Finance.

## Who this is for

- F500 CFO organizations installing the substrate for the first time.
- Internal audit teams building a continuous-audit knowledge layer.
- Controllers consolidating evidence repositories ahead of an external audit cycle.
- Audit-committee chairs who want a verifiable version history of every board pack.

## What is in the box

| Layer | File | What it gives you |
|---|---|---|
| Schema | `schema/typed-memory-categories.md` | 9 typed-memory categories: deal, counterparty, sox-control, audit-evidence, journal-entry, expense-policy, vendor, internal-audit-finding, board-pack-decision. |
| Connectors | `connectors/workday.md`, `connectors/netsuite.md`, `connectors/sap-finance.md` | API endpoints, auth flows, sync cadence, write-back rules. |
| Retention | `retention/defaults.md` | SOX 404 (7 years), SEC 17a-4 (6 years), and per-jurisdiction variations. |
| Decision audit | `decision-audit/sox-404-evidence.md`, `decision-audit/board-pack-trail.md` | Evidence stamping and board-pack version trails that auditors can replay. |

## Install

```bash
/vertical-finance init
```

Stages drafts, prints a review checklist, stops.

## Read first

If you only have time to skim one file, read `decision-audit/sox-404-evidence.md`. The evidence-stamping pattern is the load-bearing rule for finance work; if it does not match your control framework, the rest of the pack will not fit either.

## What this pack does NOT include

- Specific control catalogs.
- Tax provision workflows.
- Treasury beyond cash-position evidence.
- Investor relations beyond board-pack evidence.
- External audit firm portals beyond inbound document feeds.

## Roadmap

- v2: Tax provision workflow.
- v2: Treasury workflow (cash positioning, FX, hedging).
- v2: ESG and sustainability reporting evidence layer.
- v3: Continuous transaction monitoring layer.

## Support

Issues and pack-specific questions belong on the ai-brain-starter repository.
