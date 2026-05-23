---
name: repo-evaluation
description: Default-open extraction pass for AI coding agents auditing third-party repositories. Use when a user shares a GitHub URL, asks "is this better than what we have", asks "what can we learn from this repo", or otherwise prompts an evaluation of an external project. Prevents the "Cherry-pick: None" failure mode where surface-name overlap is mistaken for capability equivalence.
---

# Repo evaluation — default-open extraction pass

Use this skill every time the user shares a GitHub URL or asks whether an external project beats the current stack. Goal: an honest answer, not adoption theater. The shiny repo may lose. The current stack may lose. Either outcome is fine. What is NOT fine is skipping the extraction because the repo "looks reasonable" or the surface "is already covered."

## The principle

**Every audit defaults to *there IS something to learn*.** "Cherry-pick: None" is a claim — earn it, never assume it.

The failure mode this skill prevents: block-name overlap mistaken for capability equivalence. "Their `self_improvement` block exists, my `Drift Audit` exists, same surface, covered." That reasoning matches surface names; it does NOT prove the IMPLEMENTATIONS are equivalent. The IMPLEMENTATIONS are where the leverage lives.

## The discipline

Every audit memo body MUST contain:

1. **≥3 named cherry-pick candidates with verbatim quotes from the actual content file** (SKILL.md / agent file / AGENTS.md / learnings.md — NOT the README). Reading the README is necessary; extracting from the content file is sufficient. README is marketing; content file is implementation.

2. **For each candidate, an explicit `ADOPT / DROP / DEFER` score with the one-sentence reason.** Silent omission is disallowed. "Considered and dropped + reason" beats "not mentioned." A candidate the audit didn't think about can't be honestly dropped.

3. **At least one panel dissent voice arguing FOR adopt on each DROP.** Proves the candidate was tested by adversarial framing, not pre-filtered by closed-minded surface mapping. If you can't summon a dissent voice that takes the candidate seriously, the candidate wasn't really considered.

If all 3 candidates score DROP after dissent, "Cherry-pick: None" is earned and the audit is complete.

## When this skill applies

Trigger conditions:

- User pastes a GitHub URL with no other framing
- User asks "is this better than what we have"
- User asks "what can we learn from this repo"
- User asks "should we adopt this"
- User asks "anything worth borrowing"
- An audit memo is being authored for a repo evaluation

The trigger is NOT limited to "should we install this." A learnings question produces build recommendations; build recommendations need the same discipline. The moment the response becomes "we should build X / I'll draft X / let's add X based on this repo" — the extraction discipline applies.

## When this skill does NOT apply

Phase 0 short-circuit (deal-breaker reject) skips the extraction discipline:

- License incompatibility with the use case (e.g. AGPL on a closed-source plugin path)
- Repo archived more than 18 months ago
- Active security incident with no remediation
- Repo metadata reveals abandonment (no commits, no maintainer response, dead links)

In a Phase 0 short-circuit, reading further is malpractice. File the deal-breaker line-cited, skip the extraction.

NOTE: a Phase 3 security gate failure (privacy / data-handling / dangerous defaults) is NOT a Phase 0 shortcut. By Phase 3 the content has been engaged with; the extraction discipline applies. Document the security failure AND the cherry-picks separately.

## Axis B — score against the full operating-company surface

Every audit scores TWO axes for the operator:

- **Axis A** — Can this repo become a paid offering or product upgrade the operator charges clients for? (`charge-direct` / `charge-upgrade` / `lead-magnet` / `none`)
- **Axis B** — Can this repo remove human-hours, raise quality, or unblock async execution inside the operator's OWN companies?

**Axis B spans the FULL operating-company surface, NOT just dev tooling.** Bug class to prevent: **AXIS-B-DEV-TOOLING-TUNNEL** (family with `LANDSCAPE-KEYWORD-TUNNEL`). Both are the auditor inheriting the repo's vocabulary instead of scoring the actual surface.

When the linked repo is a coding-agent / subagent / dev-tooling catalog, the auditor's default instinct is "score the dev axes." That instinct misses everything else the operator does. An operator running a real business has at least:

- **Sales** (pipeline, outreach, proposals, RFPs, follow-up)
- **Marketing** (content, social, brand, lead generation, site upkeep)
- **Operations** (delivery, ops runbooks, contractor coordination, workflow automation)
- **Finance** (billing, P&L, invoicing, cash-flow)
- **Content + writing** (blog, newsletter, social posts, bilingual publishing)
- **People-matching** (network coordination, partner/vendor matching, talent matching) — if applicable to the operator
- **Events** (event ops, attendee management) — if applicable to the operator
- **Investor / fundraising** (passive maintenance, deck upkeep) — if applicable to the operator
- **Site upkeep** (marketing pages, product surfaces, blog hosting)
- **Agent fleet** (custom assistants, MCPs, cron jobs, overnight QA, scheduled tasks)
- **Personal ops** (journal, planning, weekly/monthly review)

**Operational rule:** an audit memo that touches "Axis B" MUST enumerate the per-surface scoring — not collapse the whole operating-company surface into a single "internal growth" sentence. Per-surface "None" is a legitimate verdict; overall "None" without per-surface enumeration is the bug pattern this rule blocks.

**For the operator's specific surface, read the operator's `repo-evaluation.md` rule file** (or wherever the operator codified their company list). The public skill teaches the discipline; the private rule names the surfaces. The discipline is *enumerate the surface before declaring None.*

## The dissent test

A useful internal check before declaring "Cherry-pick: None":

> *"If a smart, hostile reviewer audited my audit, what would they find I missed?"*

The kinds of cherry-picks closed-minded audits miss:

- **Operational caps + thresholds the upstream codified as numbers** (file count limits, character limits, time-since-last-use cutoffs). Numbers are leverage that schema-mapping doesn't surface.
- **Taxonomies + classifications the upstream uses as first-class concepts** (preference-strength tiers, verdict labels, severity classes). Naming the levels is leverage.
- **Anti-patterns the upstream explicitly bans** ("don't manufacture content," "no praise no philosophical tangents"). What they ban is often what you should also ban.
- **The session-end / observability discipline** (when does memory get pruned, when does state get reconciled, when does the agent admit it doesn't know). Usually buried in agent-instruction text, not in the README.
- **Composition primitives** (how do multiple agents communicate, how does memory cross sessions, how does state get serialized for handoff). Often the most-reusable layer.

## Output template

When the audit lands as a memory file, structure the body so the cherry-pick discipline is visible:

```markdown
## Repo: owner/repo
**Why now:** <one sentence>
**Verdict:** <Adopt-feature | Replace | Cherry-pick + build | Build ours | Watch | Pass | Reject>

## Phase 0 — ground the ask
[license / maintenance / archive status / etc.]

## Phase 1 — what we already have
[inventory of current stack capability in this space]

## Phase 2 — landscape
[top 3-5 competitors named by category leader name, not by keyword rank]

## Phase 3 — security + maintenance gate
[pass/fail per criterion with line-citations]

## Phase 4.5 — capability surface + cherry-pick candidates

| Candidate | Source quote (verbatim) | Score | Reason | Dissent voice (for DROP only) |
|---|---|---|---|---|
| <name 1> | "..." | ADOPT \| DROP \| DEFER | <one sentence> | <voice arguing FOR adopt> |
| <name 2> | "..." | ... | ... | ... |
| <name 3> | "..." | ... | ... | ... |

## Phase 5 — decision
[verdict + one-sentence reason]

## Shipped cherry-picks (if any landed same-session)
[explicit list of what got adopted + where it landed in the stack]
```

The table format is one option. A numbered list with each candidate as a section also works. What matters: ≥3 named candidates, verbatim quotes, scored, dissented.

## Family

This skill exists because the failure mode it prevents recurred 7 times across one team's audit history before getting codified at the principle level. Each prior fix closed a surface (skipped landscape scan / read 2 of 11 source files / README-only audit / deferred sibling audit / keyword-tunneled the landscape search / 8 memory blocks treated as capability equivalence). The principle — *default-open extraction* — names the discipline directly so the next audit can't fail under yet-another surface.

If you find yourself rationalizing "this is just a quick check" or "the surface is already covered, no need to read deeper" — that exact thought is the trigger to run the extraction pass, not to skip it.
