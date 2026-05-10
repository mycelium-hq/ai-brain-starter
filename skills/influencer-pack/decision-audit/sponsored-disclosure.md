# Decision-audit pattern: sponsored-content disclosure

Sponsored content carries legal disclosure requirements that vary by jurisdiction. This pattern enforces disclosure at the typed-memory layer so creator workflows cannot accidentally publish a sponsored piece without the required tags.

## Why this exists

The FTC (US), the ASA (UK), the ASCI (India), the ACCC (Australia), and equivalent bodies in EU member states all require visible, clear disclosure when a creator is paid (cash, free product, or other consideration) to feature a brand. The disclosure must be visible at the start of the content; "buried in the description" does not count.

Repeat violations result in fines for the creator and platform-level enforcement actions (post takedowns, account restrictions). This pattern reduces the chance of a missed disclosure to near-zero by gating publish on the disclosure check.

## How the pattern enforces

When the substrate detects that a `content-piece` is linked to a `collab-deal` with `cash_component_usd > 0` or `product_component_usd > 0`, it requires the following before publish:

1. The `content-piece.disclosure_required` field is `true` (auto-set when the collab link is made).
2. The `content-piece.disclosure_present` field is `true` (operator confirms via approval gate).
3. The body of the post contains at least one of the canonical disclosure tokens for the relevant jurisdiction.

Canonical disclosure tokens by jurisdiction:

| Jurisdiction | Canonical tokens |
|---|---|
| US (FTC) | `#ad`, `#sponsored`, `#paidpartnership`, `Paid partnership with`, `Sponsored by` |
| UK (ASA) | `#ad`, `#advertisement`, `Sponsored` |
| India (ASCI) | `#ad`, `#sponsored`, `#collab`, `#partnership` (must appear in the first three lines of the caption) |
| Australia (ACCC) | `#ad`, `#sponsored`, `Sponsored content` |
| EU (per-state, e.g. AGCOM Italy, Bundeskartellamt Germany) | `#Werbung` (DE), `#pubblicità` (IT), `#publicidad` (ES), `#publicidade` (PT), `#publicité` (FR), plus `#ad` as a universal fallback |
| Brazil (CONAR) | `#publi`, `#publicidade`, `#parceriapaga` |
| Mexico (PROFECO) | `#publicidad`, `#colaboracionpagada` |

## Init flow

The pack init step asks the creator for their primary publishing jurisdiction(s). Most creators publish from one country but reach audiences in many; the substrate uses the publishing-jurisdiction rule (where the creator is based) plus an audience-jurisdiction overlay (where the platform's primary delivery is).

If the creator publishes in the US but has a major Brazilian audience subset, the substrate enforces both the US and Brazilian token sets.

## Pre-publish gate

The pack's content-publish skills (any skill that posts on behalf of the creator) call this pattern before any platform write:

```
def assert_disclosure_present(content_piece, collab_deal):
    if collab_deal.cash_component_usd > 0 or collab_deal.product_component_usd > 0:
        if not content_piece.disclosure_required:
            raise DisclosureGapError("collab-deal requires disclosure but content-piece does not have disclosure_required=true")
        if not content_piece.disclosure_present:
            raise DisclosureGapError("disclosure_present=false; creator must approve disclosure inclusion")
        for jurisdiction in operator_jurisdictions:
            if not any(token in content_piece.body for token in canonical_tokens[jurisdiction]):
                raise DisclosureGapError(f"no canonical disclosure token found for {jurisdiction}")
```

The pre-publish gate raises a hard error; the publish path cannot proceed. The error surface includes the missing token list so the creator can fix and re-run.

## Per-platform format wrinkles

Disclosure placement matters per platform:

- **Instagram Reels**: must be in the first line of the caption AND tagged via the "Paid partnership with [@brand]" feature in the caption editor. The substrate cannot set the platform-side tag (no API for it on creator accounts); it surfaces a manual-step reminder during publish.
- **Instagram Stories**: must be on-screen as an overlay (the platform's "Paid partnership" sticker is the canonical answer). The substrate flags Stories with `format: story` and `disclosure_required: true` and refuses to render-and-post without the sticker confirmation.
- **TikTok**: must use the platform's Branded Content toggle in the post editor. Same pattern as IG Stories for the substrate gate.
- **YouTube**: must check the "Includes paid promotion" box in the upload UI. The substrate surfaces the reminder.
- **X / LinkedIn**: must include the disclosure token in the post body. The substrate enforces token-presence directly.
- **Substack**: must include "This post is sponsored by [brand]" in the first paragraph. The substrate enforces token-presence and rejects publish if the first paragraph is missing it.

## Audit trail

Every disclosure check (pass or fail) writes a hash-chained entry to the audit log with timestamp, content_piece ID, collab_deal ID, jurisdictions checked, tokens detected, and operator-approval timestamp. The audit log is append-only; no edits, no deletes.

If a disclosure-gap error is later proven to be a false positive (e.g. the creator's caption did include disclosure that the substrate's regex did not catch), the operator marks the audit-log entry as `revoked: true` with reason; the entry stays.

## When the pattern intentionally lets through

The pattern does NOT enforce disclosure on:

- Affiliate links without active brand-deal linkage (these have softer disclosure rules, jurisdiction-dependent; some require disclosure, some do not)
- Product gifts the creator receives unsolicited and chooses to post about (US: only requires disclosure if the brand expected coverage; many creators disclose anyway as best practice)
- Self-owned product launches (no brand counterparty; the disclosure rule does not apply)

The init step asks the creator for their default policy on each of these gray areas and stores the answer. The pattern can be tightened to "always disclose" if the creator prefers maximum caution.

## Related patterns

- `decision-audit/brand-deal-acceptance.md` (counterpart pattern: pre-deal vetting before signing, separate from pre-publish disclosure)
- `decision-audit/medical-financial-claim-guardrails.md` (covers a different class of pre-publish gates: regulated-content claims)
- `decision-audit/contractual-deliverable-tracking.md` (post-publish: did the creator deliver what the contract specified)
