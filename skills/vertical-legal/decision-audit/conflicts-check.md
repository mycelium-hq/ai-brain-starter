# Decision audit: conflicts check

A conflict of interest, missed at intake, is a malpractice claim, a disqualification motion, and a bar referral. This document specs the conflicts check that runs at every new client and every new matter.

## Rule

Every new client adds to the conflicts graph. Every new matter checks the conflicts graph at intake and blocks if a conflict is detected. The block is recoverable: the firm can clear, waive (with documented client consent and ethics review), or decline.

## What "the conflicts graph" means

A directed graph with:

- **Nodes:** clients, opposing counsel, opposing parties, witnesses, related parties (parents, subsidiaries, affiliates), former clients within the conflicts retention window.
- **Edges:** matter relationships (`opposed_in`, `co-counsel_with`, `subsidiary_of`, `affiliate_of`, `married_to`, `former_client_with_residual_duty`), each tagged with the matter and the date.

The graph is built incrementally from the typed-memory categories (`client`, `matter`, `opposing-counsel`) and from connector-pulled relationships (corporate hierarchies via Clio, party lists via court dockets when the docket connector is available).

## What runs at intake

When the firm adds a new client (`type: client`) or a new matter (`type: matter`), the substrate runs:

1. **Direct match.** Does the prospective client appear as a node already? If yes, what was the prior role (former client, opposing party, witness)?
2. **Affiliate match.** Does any node related to the prospective client (parent, subsidiary, affiliate, controlling individual) appear as a node?
3. **Adversity match.** Does the prospective client's matter (parties, opposing counsel, witnesses) include any node currently or formerly representing an active client?
4. **Issue match.** Does the prospective client's matter type and adverse positions overlap with a current matter where the firm represents the adverse party?
5. **Personal-conflicts match.** Do the firm's attorneys have personal interests (board seats, equity, family ties) in any node?

Each match returns a severity:

- **Block:** direct adverse representation in an active matter (clear conflict).
- **Block-pending-review:** former client within the residual-duty window where the new matter is substantially related.
- **Review:** affiliate or issue overlap that requires partner review and possibly client consent.
- **Notice:** distant overlap surfaced for awareness; intake proceeds.

## Implementation

The conflicts check is a hook on the write of any `client` or `matter` document. The hook:

1. Reads the prospective client and matter intake forms.
2. Queries the conflicts graph for the five matches above.
3. Returns a structured result: `{matches: [...], severity: ..., recommended_action: ...}`.
4. Blocks the write if severity is `block` or `block-pending-review`. The operator can either:
   - Resolve the conflict (decline the matter).
   - Initiate the waiver process (consent, ethics review, written record).
   - Override with cause (rare; logged in the audit trail with the partner-in-charge approval).

## Audit log

Every conflicts-check run logs:

- `timestamp`
- `intake_actor`
- `prospective_client_id`
- `prospective_matter_id`
- `matches` (full structured result)
- `severity`
- `disposition` (cleared, waived, declined, blocked, overridden)
- `disposition_actor` (partner approving disposition)
- `waiver_doc_id` (when applicable)

The conflicts audit log is retained indefinitely per the `retention-policy` table; the firm's institutional memory of declined matters and cleared conflicts is itself a compliance asset.

## Residual-duty window

A former client retains residual duties under Model Rule 1.9 indefinitely for substantially related matters and 7 years (default) for the broader confidentiality duty. The window is configurable at install; the default is 7 years from the close of the last matter for that client.

After the residual-duty window expires, the former-client node remains in the graph for institutional memory but does not raise the `block-pending-review` severity automatically. It still raises a `notice` so the firm can decide.

## What this check does NOT do

- It does not replace partner judgment. The firm's conflicts officer, ethics committee, or general counsel still makes the call; the substrate raises the question.
- It does not handle multi-firm joint representations (one matter, two firms representing the same client) without extra configuration; the firm sets up co-counsel relationships explicitly.
- It does not handle informational-conflict situations (a former employee of the firm now at opposing counsel) without an HR-feed connector that surfaces the lateral move.

## Provenance

The check enforces ABA Model Rules 1.7 (current-client conflicts), 1.8 (specific-conflict rules), 1.9 (former-client conflicts), 1.10 (imputed disqualification), 1.11 (former government employees), and 1.18 (prospective clients). State variations apply; the firm sets jurisdiction and the check layers state-specific rules where they are stricter.
