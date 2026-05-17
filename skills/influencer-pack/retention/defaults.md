# Retention defaults: influencer pack

Per-category retention rules for typed-memory entries created by the influencer pack. The substrate enforces these at the storage layer; entries past their retention window get auto-archived (moved to a cold-storage path) but never deleted without an explicit operator command.

The defaults below balance creator workflow needs against platform terms-of-service, regional privacy laws (GDPR EU, CCPA California, LGPD Brazil), and tax recordkeeping (most jurisdictions require 7 years for revenue-related records).

## Per-category defaults

| Category | Default retention | Rationale |
|---|---|---|
| `audience-segment` (aggregate) | indefinite | non-PII, useful for trend analysis |
| `dm-conversation` (most subtypes) | 90 days | privacy-respecting; creator can extend per-thread |
| `dm-conversation` (with `priority: vip` or linked to active `collab-deal`) | 1 year | ongoing relationship needs context |
| `dm-conversation` (with `subtype: brand-collab-inbound`) | 1 year | NDA + pipeline tracking |
| `content-piece` (creator's own) | indefinite | creator's published work, queryable forever |
| `content-piece` (with `audience: paid` or `founding`) | indefinite | retention follows the platform's subscriber retention |
| `content-source` (external research) | 2 years | freshness matters; reference material goes stale |
| `collab-deal` (status: in-delivery, signed, paid) | 7 years | tax + legal recordkeeping |
| `collab-deal` (status: declined, ghosted) | 1 year | trend analysis; no tax obligation |
| `creator-revenue` | 7 years | tax recordkeeping |
| `voice-fingerprint` (written) | indefinite | recompute is expensive; keep until the creator changes voice deliberately |
| `voice-fingerprint-audio` | creator-controlled | encrypted, retention is whatever the creator decides |
| `audience-question` | indefinite | question patterns persist across years |
| `content-idea` | indefinite | the creator's content-roadmap history; cheap to keep |
| `idea-discard` | indefinite | the idea engine's training signal; must never auto-archive, or the taste profile loses its basis |
| `taste-profile` | indefinite | one living record per creator, recomputed in place |

## Jurisdictional overrides

The pack init step asks for the creator's tax-residency jurisdiction and sets retention overrides per the local rules:

- **US**: 7 years for revenue-related records (IRS), 4 years for employment records (federal). Most categories follow the defaults above.
- **EU (GDPR)**: stricter on PII retention; DM content default lowers to 60 days, customer email retention follows the legal-basis (contract = 7 years; consent = until withdrawn). The pack init step writes a per-category lawful-basis note for each.
- **UK (post-Brexit)**: matches EU rules for retention; 6-year default for VAT records.
- **Canada (CRA + PIPEDA)**: 6 years for tax records, principle of "no longer than necessary" for personal data.
- **Brazil (LGPD)**: similar to GDPR; 5-year default for fiscal records.
- **Mexico**: 5-year default for fiscal records.
- **Other**: pack init prompts for the local rule and stores the answer.

## Override mechanism

The creator can override any default per record via the `retention_until: <ISO date>` frontmatter field. The substrate respects per-record overrides over category defaults.

The creator can also set per-category overrides by editing this file and re-running `/influencer-pack init --regenerate retention/defaults.md`.

## Right to be forgotten

Audience members and subscribers may request data deletion. The substrate supports this via a dedicated removal pipeline:

1. Operator runs `/influencer-pack forget --email <address>` (or by handle for platforms that don't expose email).
2. Substrate finds all typed-memory entries referencing that email or handle.
3. Lists them for operator review (so the operator can confirm the request matches the records).
4. On confirmation, the substrate replaces PII fields with hash-chained tombstones (preserves analytical aggregates while removing the identifier).
5. Audit log records the request, requester, operator confirmation, and tombstone IDs.

The forget pipeline is not destructive; analytical aggregates remain intact. Only the identifier is removed.
