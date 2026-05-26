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

4. **Per-ADOPT cherry-pick: scan the team's issue tracker (Linear / Jira / GitHub Issues / etc.) for prior or in-flight coverage in the same domain.** The audit may identify a candidate the team already has an issue for — in-flight, recently shipped, or backlogged. Declaring it "new work" when it already exists in the tracker burns engineering hours on duplicate scope. The cherry-pick output table carries an explicit `Tracker coverage` column per ADOPT showing `<issue-id>` / `<issue-id>:done-recent` / `<issue-id>:backlog` / `NONE`. See Phase 5.4 below for the check protocol.

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

## Phase 0 scope tier — count files before reading content

Count tracked + non-vendored source files in the target repo before reading content. Apply tier:

- **Small (<1,000 files):** read every content file the discipline names (SKILL.md / AGENTS.md / learnings.md / agent files / spec docs).
- **Medium (1,000-10,000 files):** prioritize the content file at known locations (`SKILL.md`, `references/`, `docs/adr/`, `AGENTS.md`, `CLAUDE.md`). Then sample 2-3 source files referenced from the content.
- **Large (10,000+ files):** critical-path only — content files + architecture-doc + first-screen of `src/` index. Audit memo MUST report coverage % (files read / total) so future re-audits know the scan boundary.

Command:

```bash
find <repo> -type f -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/vendor/*' -not -path '*/__pycache__/*' -not -path '*/dist/*' -not -path '*/build/*' -not -path '*/.next/*' -not -path '*/target/*' | wc -l
```

Bug class: **AUDIT-SILENT-TRUNCATION** (parent: ARTIFACT-WITHOUT-MEASUREMENT). Prevents "I read what I had time for" failure mode where a 50K-file monorepo gets a 5-file audit and the gap is invisible.

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

| Candidate | Source quote (verbatim) | Score | Reason | Tracker coverage | Dissent voice (for DROP only) |
|---|---|---|---|---|---|
| <name 1> | "..." | ADOPT \| DROP \| DEFER | <one sentence> | `<issue-id>` \| `<issue-id>:done-recent` \| `<issue-id>:backlog` \| `NONE` | <voice arguing FOR adopt> |
| <name 2> | "..." | ... | ... | ... | ... |
| <name 3> | "..." | ... | ... | ... | ... |

## Phase 5 — decision
[verdict + one-sentence reason]

## Phase 5.4 — issue-tracker coverage check (per ADOPT cherry-pick, before any new tracker issue gets filed)

For each ADOPT cherry-pick that translates into trackable dev work, search the team's issue tracker BEFORE declaring it new work. Three signals matter:

1. **Active in-flight issue covering the same domain.** Cherry-pick becomes "comment on existing issue reinforcing the priority" or "add as a sibling refinement under the existing issue" — not a new tracker entry.
2. **Recently shipped (Done within ~30 days) issue covering the domain.** Cherry-pick may already be partially landed; verify what shipped before specifying new scope. The audit may collapse into "this is a follow-up refinement, file as next-iteration, not a parallel scope."
3. **Backlog issue named but not yet in flight.** Cherry-pick can either prompt promotion of the existing issue or extend its description with the new spec details from the audit.

Search protocol:

1. Use the team's issue tracker's full-text search across both the title + description (Linear: `search_issues` with the candidate keywords; Jira: JQL `text ~ "<keywords>"`; GitHub Issues: `is:issue <keywords>`).
2. Scope to the relevant team / project / workspace; do NOT search globally unless the candidate could legitimately land in any team.
3. Capture matches with state (Backlog / In Progress / In Review / Done / Canceled) and updated date.
4. Decide per match: link / refine / promote / file-fresh.

Output: the Phase 4.5 candidate table's `Tracker coverage` column carries one of:
- `<issue-id>` (verbatim, e.g. `TEAM-94`) — existing in-flight issue covers this; cherry-pick links / refines / closes-as-dup.
- `<issue-id>:done-recent` — recently shipped; cherry-pick is a refinement or follow-up; file a new issue ONLY IF the audit surfaced genuinely new scope beyond what shipped.
- `<issue-id>:backlog` — exists in backlog; cherry-pick prompts promotion + adds the audit's spec details to the existing issue.
- `NONE` — no prior coverage; cherry-pick becomes a new tracker issue per the Wiring Checklist + Phase 5.5 foundation verification.

Bug class this prevents: **CHERRY-PICK-DUPLICATES-EXISTING-TRACKER-WORK** (family with `CONCURRENT-SESSION-SAME-SCOPE`). Failure pattern: the audit identifies a candidate, declares it new work, fails to notice the team's existing in-flight issue (which may be in a sibling session or a sibling worktree as we speak), and burns engineering time on duplicate scope. The check turns the audit into a first-class consumer of the team's coordination layer instead of a parallel pipeline.

Sibling discipline already in flight: if the team has a concurrent-session safeguard at issue-creation time (a hookify rule, a MCP guard, or a project-level lint), this Phase 5.4 fires earlier — at audit-output time, before the issue body even gets drafted. Both are needed; this is the upstream half.

## Shipped cherry-picks (if any landed same-session)
[explicit list of what got adopted + where it landed in the stack]

## Wiring Checklist (MANDATORY per ADOPT cherry-pick — file BEFORE declaring done)

For each ADOPT cherry-pick, fill out THREE columns same-session. Empty cells mean unshipped wiring — fix in this session, do NOT defer.

| ADOPT # | Artifact created | Discoverability wires (where it's found) | Automation surface (what fires it) | Verification path (how we know it works) |
|---|---|---|---|---|
| 1 | <e.g., new rule file `⚙️ Meta/rules/X.md`> | <e.g., CLAUDE.md `# Rules` section + MCP Build Runbook + Build Standards + sibling umbrella SKILL.md (named umbrellas)> | <e.g., new hookify rule `.claude/hookify.warn-X.local.md` (file event) + PostToolUse hook registered in settings.json + cron job> | <e.g., smoke test command + expected output + Stop hook coverage> |
| 2 | ... | ... | ... | ... |
| 3 | ... | ... | ... | ... |

**Cells that may legitimately read "N/A":**

- Discoverability "N/A" — only when the artifact IS the umbrella / runbook / index entry itself (it doesn't need to be wired INTO another surface, it IS the wiring surface).
- Automation "N/A" — only when the artifact is rule-content read at decision-time (e.g., a band-cap inside a rule file Claude reads when running the audit). Most rule edits propagate via the surfaces that already reference the rule — list those surfaces, not "N/A".
- Verification "N/A" — never. If you can't write a verification step, the cherry-pick isn't done.

**Bug class this checklist prevents: ARTIFACT-WITHOUT-AUTOMATION-WIRING** (parent class of ARTIFACT-WITHOUT-DISCOVERABILITY + ARTIFACT-WITHOUT-UMBRELLA-WIRING). Failure pattern: auditor adopts a cherry-pick, writes the artifact file, and DOES NOT enumerate the wiring layers, so the user has to ask "did it go in the right umbrella? are we auto-triggering it? all upgrades shipped?" The checklist is the structural fix — the auditor cannot declare done without filling the cells.

**Discipline check:** if filling this table is uncomfortable, the artifact is probably underspecified. Re-read the ADOPT cherry-pick reasoning and identify the surfaces it touches.

### Domain matrix for new or extended rules (vault rules / team conventions / SKILL.md edits)

When the cherry-pick lands as a NEW or EXTENDED team rule (vault rule file / team convention / SKILL.md), the "Discoverability wires" column MUST enumerate each surface this matrix marks as mandatory. A close-time verifier should enforce this — gaps surface as `rule-domain wiring: ... unwired: ...` at session close.

| Rule body signal | Mandatory surface (MUST reference the rule) | Bypass |
|---|---|---|
| **Universal (every new rule):** any | Top-level agent instructions (`CLAUDE.md` / `AGENTS.md` / `GEMINI.md`) `# Rules` section bullet | none — every rule MUST be listed |
| **Universal (every new rule):** any | If rule declares `Bug class:` → team's incident catalog (Critical Failure Inventory or equivalent) MUST have an entry | none — every named bug class needs an incident anchor |
| **CI/CD domain:** `CI[-\s]?CD` / `github actions` / `\.github/workflows` / `workflow (file\|inject\|yaml\|yml)` / `(deploy\|build\|release) pipeline` / `cron job` / `launchd` | Team's CI/CD umbrella SKILL.md routing table (e.g. shipping-code / dev-ops) | team-defined bypass env var |
| **MCP domain:** `mcp` / `fastmcp` / `tool semantics` / `stdio transport` / `model context protocol` | Team's MCP build runbook PRE-FLIGHT CHECKLIST | team-defined bypass env var |
| **Build-discipline domain:** `three-layer wiring` / `build artifact` / `BUILD-WITHOUT-WIRING` / `BUILD RULES` / `optimization pass` | Team's Build Standards runbook GENERAL BUILD RULES | team-defined bypass env var |
| **Agent/subagent domain:** `subagent` / `sub-agent` / `agent briefing` / `Task tool` / `Agent (Task` | Global agent instructions `# Agent (Task tool) briefings` section | team-defined bypass env var |
| **Security domain:** `security` / `vuln` / `vulnerability` / `CWE-\d+` / `OWASP` / `injection` / `SAST` / `CVE` / `exploit` / `threat model` | Team's code-security umbrella SKILL.md routing table | team-defined bypass env var |

**How to apply per cherry-pick:**

1. Read the rule body the cherry-pick is shipping.
2. Walk the matrix top to bottom; for each row, ask: does the rule body match this signal regex?
3. Every YES row produces a wiring obligation. Fill the "Discoverability wires" cell with the union.
4. Ship the cross-references SAME SESSION. Banned framings: "wired into umbrella TBD," "future cross-link," "v2 candidate."
5. Universal gates (top-level instructions `# Rules` + incident catalog on `Bug class:`) are NOT skippable.

**Multiple domains common.** A single rule frequently matches 2-4 domains (e.g., an LLM-guardrails rule matches MCP + Security; a CI/CD-injection rule matches CI/CD + Security). Cross-reference into EVERY matched surface, not just the strongest match.

Bug class: **ARTIFACT-WITHOUT-DOMAIN-WIRING** (subclass of ARTIFACT-WITHOUT-AUTOMATION-WIRING). Failure pattern: a new rule ships with hookify + scanner + 1-2 SKILL.md edits but skips the universal gates plus several mandatory domain surfaces from this matrix. The user surfaces the gap with "did it go in the right umbrella?" — that question IS the bug.
```

The table format is one option. A numbered list with each candidate as a section also works. What matters: ≥3 named candidates, verbatim quotes, scored, dissented, AND wiring-checklist filled per ADOPT.

## Phase 5.5 — verify foundation primitives in the target repo before issue creation

When an ADOPT cherry-pick translates into a build issue (Linear / GitHub / internal tracker), verify that the target repo actually has the foundational primitives the cherry-pick assumes BEFORE writing the issue body.

Failure mode this prevents: **CHERRY-PICK-WITHOUT-TARGET-REPO-VERIFICATION.** The audit reads the upstream's elegant primitive (model presets, tier-aware caps, message-chain guards, GET-side audit middleware) and writes a confident issue body — "Ship X primitive in repo Y, wire into Y's existing tier / middleware / chain." The build session opens repo Y, finds the assumed foundations don't exist, and the issue's Work + Done = criteria evaporate. The build session then spends time re-scoping issues that should have been re-scoped at audit time.

Verification checklist (apply once per cherry-pick before issue body is written):

1. **List the foundations the cherry-pick assumes.** What primitives does this build sit on? Examples: a tier / plan field on a tenant or account schema, an HTTP middleware layer, a message-chain primitive in the agent runtime, an RBAC role library, a settings store, an audit log, a feature flag system.
2. **`rg` or equivalent grep against the target repo for each.** Cite the file + line if present; mark "MISSING" if absent.
3. **For each MISSING foundation, the cherry-pick is NOT yet shippable as written.** Pick one path:
   - (a) **Split** into foundation-issue + feature-issue. Foundation issue ships first; feature issue inherits.
   - (b) **Re-scope** the feature issue to include the foundation work (becomes a bigger ship, but coherent).
   - (c) **Defer** the cherry-pick to a different target repo where the foundation exists, or to a future phase after the foundation lands.
4. **The issue body MUST cite the verification.** Either "Foundation primitives verified at `<file>:<line>`" OR "Foundation primitive `<name>` MISSING — depends on issue `<other-issue-id>` shipping first."

When the audit is producing pattern files / spec amendments / runbooks (not yet issues), the verification can be deferred to the build session — but the Pattern file MUST flag the assumed foundations so the build session catches the gap on first read, not on first attempt to wire.

Bug class: **CHERRY-PICK-WITHOUT-TARGET-REPO-VERIFICATION**. Family with `ARTIFACT-WITHOUT-DEPENDENCY-WIRING`, `ARTIFACT-WITHOUT-UMBRELLA-WIRING`, `ARTIFACT-WITHOUT-MEASUREMENT` — all instances of a thing created without one of its structural connections verified in the same beat.

## Family

This skill exists because the failure mode it prevents recurred 7 times across one team's audit history before getting codified at the principle level. Each prior fix closed a surface (skipped landscape scan / read 2 of 11 source files / README-only audit / deferred sibling audit / keyword-tunneled the landscape search / 8 memory blocks treated as capability equivalence / 7 confident cherry-picks shipped without target-repo verification). The principle — *default-open extraction* — names the discipline directly so the next audit can't fail under yet-another surface.

If you find yourself rationalizing "this is just a quick check" or "the surface is already covered, no need to read deeper" — that exact thought is the trigger to run the extraction pass, not to skip it. The same instinct applies at Phase 5.5: if you find yourself thinking "the issue body is detailed enough, the build session will figure it out" — that is the trigger to verify the target repo first.
