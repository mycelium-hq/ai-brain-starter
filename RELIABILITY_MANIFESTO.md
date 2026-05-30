# The Reliability Manifesto

Every company has critical know-how scattered everywhere. Some of it lives in people's heads. Some of it is buried in old email, Slack threads, support tickets, and databases. The company works because humans vaguely remember where that knowledge is and how to apply it.

AI agents cannot operate like that.

The leap from *"AI summarizes our docs"* to *"AI runs the process"* is not a feature gap. It is a reliability problem. The executable skills file must not drift, must not hallucinate, must not break when the company process changes.

This system addresses those failure modes by writing the substrate before writing the features. Five architectural pillars. Each prevents a specific way AI agents fail inside a real operating company.

---

## 1. Vault as ground truth, not LLM memory

The system never trusts what the model remembers between sessions. Every skill compiles from markdown the company already controls. Process change is a file edit. The git history is the audit log. When the model wants to assert a fact, the claim must trace to a file path, or it surfaces as a gap.

**Failure mode prevented: hallucination.** The model cannot invent a procedure that does not exist in the vault, because procedures only enter the agent's context by being read, and reads are deterministic.

## 2. Hooks as deterministic guardrails

Every write the agent makes runs through pre- and post-tool hooks that block on rule violation. Secrets in a public path: blocked. A contractor task missing required fields: blocked. A timezone-naive calendar event: blocked. The hooks are not LLM-judged. They are Python checks against the actual write payload.

**Failure mode prevented: silent failure.** An agent cannot ship a violation that the system has a rule for, because the rule fires at write time, not at audit time.

## 3. Rule extraction from existing artifacts

A new install does not start blank. The system reads the company's Slack export, Notion export, GDocs, or markdown corpus, and emits drafts: candidate guardrail rules from recurring decision phrases, candidate skills from recurring rituals, candidate authority entries from owner-of-process patterns. The founder reviews and accepts.

**Failure mode prevented: cold start.** A freshly installed agent does not need three weeks of corrections to reach a competent baseline, because the company's existing tribal knowledge is encoded as guardrails on day one.

## 4. Decision-outcome trail

Every decision logged in the system has an outcome field that defaults to blank. A scheduled scan surfaces decisions older than threshold whose outcome is still empty. The founder fills them in, and the trail compounds. Over months, the system learns which decisions worked and which did not.

**Failure mode prevented: drift.** When the company's process actually changed, the divergence between expected and recorded outcomes surfaces as a signal, and the rules layer is updated before the agent operates on stale guidance.

## 5. Session-close cascade

Every session ends with a deterministic three-layer pipeline that scans the conversation, files decisions to the decision log, captures journal seeds verbatim, drafts notes from quotable moments, and routes action items to canonical task lists. Nothing stays trapped in chat transcripts.

**Failure mode prevented: knowledge loss.** The lessons that surface inside a session always end up in permanent storage, so the next session inherits the new context without anyone copying anything by hand.

## 6. Verify external state before asserting or acting on it

Pillar 1 stops the model inventing facts from its own memory. This pillar stops a subtler failure: the model asserting the state of an *external system* without a confirming read in the same turn. The state of a ticket, whether a file was deleted on purpose, whether a commit shipped, whether a step is "already done": the fact may be real, but the model has not looked. It is recalling, or inferring from a stale signal, or reasoning over the result of a tool call that never actually returned.

The rule is mechanical: before the agent names an external fact or acts on it, a tool result confirming that fact must exist *in the current turn*. A health check that reports something missing is a question, not an instruction. The agent reads the source's own history before "fixing" it, because an intentional removal and an accidental loss look identical from the outside and demand opposite responses. A cancelled or failed tool call produces no result to reason over, so the agent re-runs it rather than proceeding on what it assumed the answer would be.

**Failure mode prevented: confident wrong action.** The agent cannot restore what was deliberately deleted, close the wrong ticket, or report a phantom success, because every claim about an external system is gated on a fresh observation rather than on memory, inference, or an unconfirmed result.

---

## Why this matters

The six pillars are not features. They are the substrate. Features that violate them are bugs.

Most AI tools optimize for the demo: a model that answers cleverly inside a five-minute conversation. Real operating companies do not run on demos. They run on processes that drift, knowledge that decays, and exceptions that surface at the worst possible moment.

The reliability story for AI inside companies starts with the architecture, not the model. Drift, hallucination, silent failure, cold start, knowledge loss, confident wrong action: name the failure modes first, then build the substrate that prevents each one. Everything else is downstream.
