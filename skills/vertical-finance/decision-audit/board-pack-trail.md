# Decision audit: board-pack version trail

Every board pack draft is versioned. Every quote in the pack traces back to a decision in the typed-memory graph. The audit committee, internal audit, and external audit can replay the version history and verify that the figures and statements in the published pack came from documented decisions, not from late-stage edits.

## Rule

Every `board-pack-decision` record links to at least one `audit-evidence` record, and the entire board pack is committed to a Git history (or a content-addressable store with equivalent guarantees) before it is distributed.

## What the trail captures

For each board pack:

- `board_pack_version` (semver, build identifier, or commit hash)
- `board_meeting_date`
- `committed_by` (the person finalizing the pack)
- `committed_at` (UTC)
- `decisions_referenced` (list of `decision_id`)
- `evidence_referenced` (list of `evidence_id`, each with `hash_sha256`)
- `quote_map` (a per-quote provenance: file or section in the pack, source decision_id, source evidence_id, source date, source author)

The pack itself is stored as the rendered output (PDF, deck, or document) plus the source files used to generate it. Both rendered and source are committed; the source is the auditor's primary surface.

## Implementation

The trail lives in three places:

1. **Pre-commit hook on the board-pack source.** Every claim in the pack source is annotated with a `<!-- src: decision_id, evidence_id, date -->` marker (or equivalent in the source format). The pre-commit hook scans for unlinked claims; an unlinked claim blocks commit.
2. **Build pipeline.** The render step takes the source, resolves every marker against the typed-memory graph, and produces a side-by-side artifact: the pack plus a provenance manifest (`provenance.json`) listing every claim and its source decision and evidence.
3. **Distribution checkpoint.** The pack cannot be distributed (sent to the audit committee, posted to the board portal) without the provenance manifest. Distribution is gated behind a substrate command that verifies the manifest matches the rendered output.

## Replay

The auditor can run:

- "For board pack v3.2.1, show me the source decision behind the revenue figure on slide 7."
- "Show me every claim in the Q3 pack that lacks an evidence link." (Should be empty post-hook; the query exists for assurance.)
- "Show me every late edit (post-commit, pre-distribution) on this pack."

Late edits between commit and distribution are themselves committed; the trail preserves the full history.

## Late corrections

If a published pack contains an error, the correction creates a new version. The substrate does not allow rewriting history (no rebase, no force-push). Errata records link from the corrected version back to the prior version with the correction note and the audit-committee disposition (usually filed with the next meeting's minutes).

## What this trail does NOT do

- It does not opine on whether the decision was correct. The auditor and audit committee judge the substance; the trail guarantees the substance was supported when published.
- It does not enforce style or pack-template rules (those live in the pack's render pipeline).
- It does not handle confidential-only board materials (unredacted versions for the chair, redacted for committee members) without an additional access-control layer; the v1 pack assumes a single materiality tier.

## Provenance

The version-trail pattern aligns with PCAOB Auditing Standard 2110 (identifying and assessing risks of material misstatement) and exchange listing rules requiring audit committee oversight of significant financial reporting matters (NYSE Listed Company Manual 303A.07; Nasdaq Rule 5605(c)). The pack does not replace audit committee charter requirements; it supports them with a verifiable record.
