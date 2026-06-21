---
status: accepted
date: 2026-05-09
amended: 2026-06-20
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
- **Deliberately free assets** — a public asset that maps to a paid capability is NOT a boundary violation if it is a deliberate free ship-decision (codified Done ticket / self-label in SKILL.md / entry in `.github/free-tier-allowlist.txt`). See "Intentional free set" below.

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

## Guard model (v2, 2026-06-20 — MYC-1339)

### v1 denylist (introduced 2026-06-18, MYC-1338) — insufficient

`scripts/check-open-core-boundary.sh` v1 used a denylist: fail on `^skills/vertical-*/`, `^skills/influencer-pack/`, `^skills/*/connectors/`, `^skills/*/decision-audit/`. This model was blind to:

- Unknown skill names (a non-listed leaked path passes silently)
- Top-level capability packs (e.g. `agentic-os/`) — none of the patterns matched
- Intentional free assets that happen to map to paid capabilities

The v1 guard ran GREEN while both `agentic-os/` and `skills/security-snapshot/` were present, because neither matched any denylist pattern. Root cause: **Guard verified on proxy, not harm** (MEMORY.md pattern `feedback_guard_verified_on_proxy_not_harm.md`).

### v2 allowlist (MYC-1339)

The guard now maintains a canonical allowlist at `.github/free-tier-allowlist.txt`. Any `skills/` subdirectory or capability-pack-shaped top-level dir **not in the allowlist** causes CI to fail. Default = blocked.

- Allowlist entries carry a rationale tag: `teaching | personal | lead-magnet | template-MYC254 | ingest-exemplar | safety`
- The existing denylist patterns are kept as belt-and-suspenders
- **Fail closed**: a missing or empty allowlist exits non-zero immediately
- **Negative control**: `tests/integration/test_open_core_boundary.sh` (4 cases) proves the guard fails on a synthetic premium path (EXIT 1) and passes on the clean tree (EXIT 0). Wired into CI via `scripts/ci.sh`.

## Intentional free set

Some assets map to paid capabilities but are **deliberately shipped free**. These are in the allowlist and are NOT boundary violations:

| Asset | Rationale | Codified decision |
|---|---|---|
| `agentic-os/` | Free template teaching the multi-agent pattern | MYC-254 (Done) — "ai-brain-starter (public template teaches the pattern)" |
| `skills/security-snapshot/` | Self-labeled "Free lead magnet for consulting practices" in SKILL.md | Self-label in SKILL.md |
| `skills/ingest-github/`, `skills/ingest-youtube/`, `skills/ingest-health/` | Single-user OAuth ingest exemplars showing the connector pattern; no per-tenant concerns | Kept in v1.5.0 prune (MYC-1338) |

## Lesson — intentional-free-check before removing a public asset (MYC-1338 regression)

MYC-1338 removed `agentic-os/` and `skills/security-snapshot/` as boundary violations. Both were intentional free assets — the MYC-1338 audit treated "maps to a paid capability" as "leak" without checking:

1. Is there a codified Done ticket recording a deliberate free-ship decision? (MYC-254 for `agentic-os`)
2. Does the SKILL.md carry a self-label like "Free lead magnet"? (`security-snapshot`)
3. Is the path in the allowlist?

In open-core, many free patterns map to paid capabilities — that IS the model. The paid moat is the runtime enforcement, not the teaching pattern. **Removing a deliberately free teaching asset undoes the open-core strategy, not enforces it.**

Before removing any public asset for boundary reasons, check these three gates. If any is present, the asset is intentionally free and must stay (or be deliberately re-decided with a new ADR amendment, not silently pruned). Citation: MYC-254 (template decision), MYC-1338 (the regression), MYC-1339 (the fix + this amendment).
