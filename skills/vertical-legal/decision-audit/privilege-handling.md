# Decision audit: privilege handling

Privilege is the load-bearing rule for legal work. Lose privilege and the firm has malpractice exposure, sanctionable disclosure, and regulator-attention risk. This document specs the firewall that runs at write time and at every read that crosses matter boundaries.

## Rule

A document tagged `privilege-tagged-doc` cannot leave the matter scope. Any agent action that would expose privileged content outside the matter scope blocks at write time and surfaces a recoverable error to the operator.

## What "matter scope" means

The matter scope is the set of:

- Documents whose `matter_id` equals the matter's `matter_id`.
- People whose role on the matter is one of `[responsible_attorney, partner_in_charge, associate, paralegal, contract_attorney, expert_witness, retained_under_kovel]`.
- Communications threads referenced by `matter_id` in their frontmatter.

A document, person, or thread that is not in the matter scope is outside the firewall.

## What "exposing privileged content" means

Six action shapes count as exposure:

1. Writing a privileged document body or excerpt to a file outside the matter scope (including a different matter's scope).
2. Including a privileged document body or excerpt in a query result returned to a user outside the matter scope.
3. Including a privileged document body or excerpt in an outbound message (email, Slack, ticket, comment).
4. Including a privileged document body or excerpt in a model context window for a query that originated outside the matter scope.
5. Caching a privileged document body or excerpt in a shared cache (vector store, retrieval cache, summary cache) that is queryable outside the matter scope.
6. Logging a privileged document body or excerpt to an audit log that is queryable outside the matter scope.

Each of these has a write-time check.

## Implementation

The firewall lives in three places:

1. **Write-time check.** Every Write or Edit to a path containing a privileged document body, or every tool call that includes a privileged excerpt as a parameter, runs through a hook that:
   - Reads the source document's `matter_id` and `external_share_blocked` flag.
   - Reads the destination scope (target file path, target message recipient, target query origin).
   - Blocks if scopes do not match. The block is recoverable: the operator can either retag the source document, change the destination, or invoke an explicit privilege-waiver record (rare; logged with full justification).
2. **Read-time check on cross-matter queries.** Queries that span more than one matter run through a filter that drops privileged documents whose matter_id does not match the requesting user's matter assignments.
3. **Cache write check.** The retrieval cache and summary cache refuse to write privileged content to any cache key that is not matter-scoped. A cache miss is preferred to a leak.

## Audit log

Every privilege-related read and write logs:

- `timestamp`
- `actor` (person reference)
- `actor_role`
- `matter_id`
- `doc_id`
- `action` (read, write, query-include, cache-write, message-attach, redaction-applied)
- `disposition` (allowed, blocked, waived-with-justification)
- `justification` (when waived)

The audit log lives in the matter's audit scope and is retained per the matter retention policy.

## Privilege waiver

A waiver is an explicit operator action with a logged justification. Waivers are rare and require:

- The operator names the basis for waiver (e.g., subject-matter waiver in litigation, regulator-mandated production, court-ordered disclosure).
- The destination is specified.
- A second reviewer (configurable: partner, general counsel, ethics committee) approves before the waiver writes.

The waiver is logged with full text in the matter's audit scope. A waiver does not automatically waive privilege for the rest of the matter; the firewall continues to apply to non-waived documents.

## What this firewall does NOT do

- It does not opine on whether a document is privileged in the first place. The privilege tag is set by the operator at intake (or pulled from the connector's metadata). If the tag is wrong, the firewall enforces the wrong rule.
- It does not handle joint-defense or common-interest privilege coordination across firms; that is a multi-tenant concern and is out of scope for v1.
- It does not handle document destruction obligations under litigation hold; hold is a separate mechanism layered on top of retention and privilege.

## Provenance

The firewall enforces ABA Model Rule 1.6 (confidentiality), Model Rule 1.18 (prospective clients), and the work-product doctrine codified in Federal Rule of Civil Procedure 26(b)(3). State variations apply; the firm sets jurisdiction at install and the firewall layers state-specific rules where they are stricter.
