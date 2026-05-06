# Vertical pack: legal

A drop-in configuration pack that turns the ai-brain-starter substrate into a legal-ready system: matter management, privileged document handling, retention defaults, and connectors for Clio, NetDocuments, and iManage.

## Who this is for

- Law firms (boutique, mid-market, AmLaw 200) installing the substrate for the first time.
- In-house legal departments at F500 buyers who want their legal team on the same substrate as the rest of the org but with legal-specific guardrails.
- Legal operations leads evaluating the substrate as a candidate for a knowledge layer over their existing document management system.

## What is in the box

| Layer | File | What it gives you |
|---|---|---|
| Schema | `schema/typed-memory-categories.md` | 8 typed-memory categories: matter, client, opposing-counsel, privilege-tagged-doc, retention-policy, billing-event, deposition-note, court-deadline. Each with required and optional frontmatter. |
| Connectors | `connectors/clio.md`, `connectors/netdocuments.md`, `connectors/imanage.md` | API endpoints, OAuth flows, sync cadence, write-back rules for the three platforms most firms already license. |
| Retention | `retention/defaults.md` | Defaults mapped to ABA Model Rule 1.15 plus state-bar variations and matter-type modifiers. |
| Decision audit | `decision-audit/privilege-handling.md`, `decision-audit/conflicts-check.md` | Privilege guardrails that block at write time. Conflicts graph that runs at every new client and matter intake. |

## Install

```bash
/vertical-legal init
```

The init command stages drafts, prints a review checklist, and stops. Nothing auto-applies. The firm reviews and merges manually into the production memory layer.

## Read first

If you only have time to skim one file before deciding whether the pack fits, read `decision-audit/privilege-handling.md`. Privilege handling is the load-bearing rule for legal work, and the pack's approach there will tell you whether the pack matches your firm's posture.

## What this pack does NOT include

- Specific firm playbooks (every firm has its own; the pack is the substrate).
- Trust accounting workflows (v1 hook only; full integration is out of scope).
- E-discovery platforms (Relativity, Everlaw, Reveal). These are downstream consumers of the matter scope.
- Practice management beyond Clio, NetDocuments, iManage. Adapt the Clio connector for Smokeball, PracticePanther, MyCase, or CosmoLex.
- Specific legal advice or jurisdictional opinion. The retention defaults are starting points, not legal opinions; verify against your bar association before going live.

## Roadmap

- v2: Trust accounting workflow.
- v2: Court-rules pack (PACER, state e-filing portals).
- v2: Time-and-billing connector pack (TimeSolv, Bill4Time, TabsPro).
- v3: E-discovery layer (Relativity, Everlaw).

## Support

Issues, drafts, and pack-specific questions belong on the ai-brain-starter repository. The pack is open source under the same license as the substrate.
