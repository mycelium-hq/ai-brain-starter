# Decision-audit pattern: evidence grounding

The idea engine proposes content based on what a creator's audience actually said. This pattern enforces that every proposed idea traces to real audience evidence, so the engine cannot invent demand that does not exist.

## Why this exists

A content-idea generator that hallucinates is worse than useless — it is actively harmful. If the engine proposes "your audience keeps asking about X" and the audience never asked about X, the creator makes content for demand that is not there, and they stop trusting every other idea the engine proposes.

The failure is quiet. A fabricated idea reads exactly like a grounded one. The only defense is to make grounding a hard, checked invariant rather than a hope.

This pattern reduces fabricated ideas to near-zero by gating `content-idea` writes on real evidence.

## The rule

Every `content-idea` record must satisfy both conditions:

1. `evidence_quotes` is a non-empty list of verbatim quotes.
2. At least one of `basis_content_ids`, `basis_conversation_ids`, `basis_question_ids` is non-empty, and every FK in those lists resolves to a real record in the typed-memory layer.

An idea that cannot cite real evidence is not softened, not flagged, not proposed with a caveat. It is dropped.

## How the pattern enforces

Two gates, at two stages:

**Write-time (schema).** The substrate rejects a `content-idea` document that has an empty `evidence_quotes` list or no resolvable `basis_*` FK. This is the same write-time schema rejection every typed-memory category gets; for `content-idea` the evidence fields are part of the contract.

**Generation-time (pre-write gate).** Before the engine writes a batch, it runs each candidate through the gate:

```
def assert_idea_grounded(idea, typed_memory):
    if not idea.evidence_quotes:
        raise EvidenceGapError(f"{idea.idea_id}: no evidence_quotes")
    basis = idea.basis_content_ids + idea.basis_conversation_ids + idea.basis_question_ids
    if not basis:
        raise EvidenceGapError(f"{idea.idea_id}: no basis FK")
    for fk in basis:
        if not typed_memory.exists(fk):
            raise EvidenceGapError(f"{idea.idea_id}: basis FK {fk} does not resolve")
    for quote in idea.evidence_quotes:
        if not typed_memory.quote_traces_to_basis(quote, basis):
            raise EvidenceGapError(f"{idea.idea_id}: evidence quote not found in any basis record")
```

A candidate that raises `EvidenceGapError` is dropped from the batch; the batch proceeds with the ideas that pass. A run that drops every candidate returns an empty batch — a correct result, not a failure.

## ID-strip backstop

The generation model is instructed to keep raw record IDs and hashes out of human-facing text fields (`angle`, `why_good`, `suggested_angle`). Models leak IDs anyway. A defensive ID-strip pass runs over every emitted `content-idea` and removes any raw ID or hash that reached a text field; IDs belong only in the `basis_*` FK lists, where the substrate resolves them into links at render time.

The backstop is belt-and-suspenders: the prompt instruction is the belt, the strip pass is the suspenders. Neither is trusted alone.

## Audit trail

Every grounding check writes a hash-chained entry to the audit log: timestamp, `idea_id`, batch ID, pass or fail, and on fail the specific gap. The audit log is append-only.

If a drop is later found to be a false positive — the evidence was real but the FK resolution missed it — the operator marks the audit entry `revoked: true` with a reason. The entry stays; the log is never edited.

## What this pattern does not do

This pattern checks that an idea is *grounded*. It does not check that an idea is *good* — that is the creator's judgment, expressed through the discard loop (`idea-engine/mechanism.md`). A well-grounded idea the creator does not like is a valid output of the engine and a valid `idea-discard`. Grounding is the floor, not the ceiling.

## Related patterns

- `idea-engine/mechanism.md` — the engine this pattern gates.
- `decision-audit/sponsored-disclosure.md` — the other pre-publish gate in the pack.
