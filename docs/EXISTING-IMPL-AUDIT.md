# Existing-implementation audit (Lesson #16)

Audit of prior-art MCP servers and synthesis patterns for the 6 skills shipped in this batch. Per Lesson #16 (MCP Build Runbook), the audit step is mandatory: before coding, search public implementations, identify the most feature-complete candidate, list gaps for our use case, and document what we considered + why we chose our path.

Method: WebSearch + WebFetch on the public web (April 2026). Star counts and last-commit dates are approximate at the time of audit.

Each section ends with the **decision** for that source: fork an existing MCP, extend an existing MCP, build fresh, or wrap an existing remote MCP from inside our skill.

## Scope clarification

The 6 skills here are NOT replacement MCP servers. They are vault-side normalizers that take JSON the LLM has already pulled from a third-party MCP and write a typed, idempotent vault file. The audit therefore answers a narrower question: which existing MCP supplies the input shape, and what gaps remain that the normalizer must fill?

This means the decision tree is usually "wrap existing MCP for the read; ship our normalizer for the write" rather than "fork the MCP itself."

---

## 1. GitHub (skills/ingest-github)

### Top candidates

| Repo | What it covers | Last activity | Gotchas |
|---|---|---|---|
| `github/github-mcp-server` | Official server. Repos, PRs, issues, code search, files, branches. Docker-distributed. | Active | Requires GitHub PAT. Docker image only — no native Python. |
| `anthropics/claude-ai-mcp` | Anthropic-side hub repo for MCP integration; not a GitHub MCP itself. | Active | Discovery channel, not an implementation. |
| Various community Python ports | Wrappers around `github/github-mcp-server`'s endpoints. | Mixed | Most do not expose `linked_issues` from PR bodies. |

### What existing MCPs contribute

The official `github/github-mcp-server` already exposes everything the LLM needs to pull merged PRs, issues, and commits in a date range. Tool list covers `list_pull_requests`, `get_pull_request`, `list_issues`, `list_commits`. We do NOT need to ship a new MCP server for read access.

### Gaps the normalizer fills

- Date-range scoping is loose in the official server. The LLM has to filter post-fetch.
- No vault-side write contract. The official server is read-only by design.
- No idempotency. Re-running a query returns fresh data, not a stable file.
- No frontmatter shape that ties PRs / issues / commits to a single dated file with `entity_ids` for cross-source joins.

### Decision

**Wrap `github/github-mcp-server` for the read; ship our normalizer for the write.** No fork. The skill prompts the LLM to pull merged PRs + linked issues + commits via the existing MCP, then pipes the JSON to our `ingest.py` for the dated vault file.

---

## 2. Notion (skills/ingest-notion)

### Top candidates

| Repo | What it covers | Last activity | Gotchas |
|---|---|---|---|
| `makenotion/notion-mcp-server` (official) | Hosted remote MCP. OAuth. Search, page-by-id, append-blocks, update-properties. Markdown conversion built in. | Active | OAuth-only. Per-page connection model — children inherit. No bearer-token path. |
| Community Notion MCPs (`SAhmadUmass/notion-mcp-server`, etc.) | Mostly wrappers around the v1 REST API. | Mixed | Older API surface; before Notion's MCP-aware optimization. |

### What existing MCPs contribute

The official `makenotion/notion-mcp-server` is built specifically for AI workflows. It converts hierarchical block JSON to markdown server-side, which means we don't have to do block-tree parsing in the normalizer. Page-tree depth is handled by Notion's connection model (parent connection = children inherit).

### Gaps the normalizer fills

- No date-anchored output. Notion returns whatever it returns.
- No `External Inputs/Notion/<root-slug>/<date>.md` shape.
- No flat database-vs-page distinction in the output schema (we want different rendering for each).
- No `entity_ids.notion: [page_ids]` for cross-source joins.
- Per-tree-depth indent levels in the output markdown.

### Decision

**Wrap `makenotion/notion-mcp-server` for the read; ship our normalizer for the write.** No fork. Skill prompts the LLM to walk the page-tree or query the database via the official MCP, then pipes the items to our `ingest.py`. The normalizer renders the indent levels and writes the dated vault file.

---

## 3. Linear (skills/ingest-linear)

### Top candidates

| Repo | What it covers | Last activity | Gotchas |
|---|---|---|---|
| `linear.app/docs/mcp` (official remote) | Hosted by Linear. Issues, comments, projects, teams, status updates. Fully authenticated. | Active | Remote MCP — depends on Linear's uptime. |
| `jerhadf/linear-mcp-server` | Community Python. Issues, comments, projects, teams. | Mixed maintenance | Older; missing some recent endpoints. |
| `cosmix/linear-mcp` | Community fork. Adds `linear_get_issue_with_comments` (full issue + comments + history in one call). | Active | Useful one-shot endpoint for our scope. |
| `emmett-deen/Linear-MCP-Server` | Another community alternative. | Active | Similar tool surface to jerhadf's. |

### What existing MCPs contribute

`cosmix/linear-mcp` exposes `linear_get_issue_with_comments` which returns issue + comments + history in a single call — exactly the input shape our normalizer expects. Linear's official remote MCP is available too and is the most reliable for production.

### Gaps the normalizer fills

- No timeline-shaped output. The MCP returns issues in arbitrary order.
- No `External Inputs/Linear/<scope>/<date>.md` write contract.
- No `comment_count` / `history_count` rollups in frontmatter.
- No timezone-converted display strings (`YYYY-MM-DD HH:MM` local) — MCP returns ISO 8601 UTC.
- No deterministic state-transition rendering in the body.

### Decision

**Wrap `cosmix/linear-mcp` (or Linear's official remote MCP) for the read; ship our normalizer for the write.** No fork. The skill instructs the LLM to fetch issues + comments + history for the scope, then pipes to our `ingest.py`. The normalizer sorts chronologically, formats local time, and writes the dated vault file.

---

## 4. Gmail (skills/ingest-gmail)

### Top candidates

| Repo | What it covers | Last activity | Gotchas |
|---|---|---|---|
| Google's official remote Gmail MCP (`developers.google.com/workspace/gmail/api/guides/configure-mcp-server`) | Official. OAuth via Google. Read, search, list labels, draft, send, label management. 19+ tools. | Active | OAuth scopes must be approved; some scopes restricted. |
| `GongRzhe/Gmail-MCP-Server` | Community Python. Auto-auth via local OAuth flow. Batch label operations. | Active, popular | Local-only; no remote hosted version. |
| `ihiteshgupta/gmail-mcp-server` | Community alternative. Search, send, manage. | Active | Smaller scope than GongRzhe's. |
| `bastienchabal/gmail-mcp` | Community alternative. | Mixed | Similar scope to ihiteshgupta's. |

### What existing MCPs contribute

The official Google remote MCP and GongRzhe's local MCP both supply the read endpoints we need: `search` by label or query, retrieve message body + headers + labels. GongRzhe's batch-label tooling is useful for adjacent workflows but not for ingestion.

### Gaps the normalizer fills

- No PII volume cap. The MCP returns full bodies; our normalizer truncates to 500 chars per message to limit accidental PII bulk in the vault.
- No `External Inputs/Gmail/<scope-slug>/<date>.md` write contract.
- No scope-slug resolution for label-vs-query inputs (we hash queries to `query-<sha8>` directories).
- No `entity_ids.gmail: [message_ids]` for cross-source joins.
- No personal-data-scrub safety net at the vault layer.

### Decision

**Wrap an existing Gmail MCP (Google's official remote, or GongRzhe's local for offline) for the read; ship our normalizer for the write.** No fork. The skill instructs the LLM to search by label or query and pull message metadata + bodies, then pipes to our `ingest.py`. The normalizer truncates bodies, slugs the scope, and writes the dated vault file. The PII guardrail is the load-bearing differentiator vs raw MCP output.

---

## 5. PR-to-SOP (skills/synth-pr-to-sop)

### Top candidates

| Pattern | What exists | Last activity | Gotchas |
|---|---|---|---|
| `anthropics/claude-code-action` | GitHub Action that runs Claude Code on PRs. Reviews, summarizes diffs. | Active | Not a synthesizer to typed memory. Output is a PR comment, not a vault file. |
| Various "Claude PR review" skills | Community MindStudio / Composio skills that review PRs and emit comments. | Mixed | Same pattern: output is a comment, not durable typed memory. |
| Anthropic skills as runbooks (zackproser blog post) | Documentation pattern, not code. | N/A | Conceptual prior art only. |

### What existing patterns contribute

The closest prior art is "review a PR and post a comment." Nothing existing extracts heuristic step lists, applies a workflow schema (steps + owners + topic), and writes to a typed-memory vault folder with sha8-based idempotency.

### Gaps our skill fills

- Heuristic step extraction from PR bodies (numbered lists, dash bullets, "Steps" / "Procedure" / "How" headings).
- Owner extraction via `@username` patterns.
- Topic detection from explicit `Topic:` markers OR keyword heuristics (deploy, release, onboarding, incident).
- Idempotency via `sha8(pr_id)` filename.
- Hand-edit guard via `hand_edited: true` frontmatter.
- Workflow-schema-conforming output (Meta/Workflows/<sha8>.md with `type: workflow`, `steps[]`, `provenance[]`, `confidence`, `freshness_days`, `last_verified`, `source_count`, `entity_ids`).

### Decision

**Build fresh.** No existing implementation produces the typed-memory write our vault expects. The script never calls an external LLM; it is heuristic-first, operator-refined (the operator runs it from a Claude Code session and the model refines in-session if needed). This also keeps it stdlib + PyYAML only — no API keys, no rate limits, no replay cost.

---

## 6. Slack-thread-to-SOP (skills/synth-thread-to-sop)

### Top candidates

| Pattern | What exists | Last activity | Gotchas |
|---|---|---|---|
| Slack's official MCP server | Hosted. Read messages, search threads, post replies, manage follow-ups. | Active | Read-only on the audit side; does not write to a vault. |
| `tomeraitz/claude-slack-bridge` | MCP that lets Claude Code pause and ask via Slack. | Active | Bridge pattern, not synthesis. |
| `mpociot/claude-code-slack-bot` | Connect local Claude Code to Slack. | Active | Bot UX, not synthesizer. |
| Samuel Lawrentz blog post (Slack -> Linear via Claude Code) | Practical example using existing Slack + Linear MCPs together. | N/A | Conceptual prior art, not packaged. |

### What existing patterns contribute

Slack's official MCP gives the LLM thread-read access. The Lawrentz blog confirms the Claude-Code-orchestrates-multiple-MCPs pattern works. No prior art classifies a resolved thread as decision-vs-exception-vs-workflow and writes to a typed-memory schema with sha8 idempotency.

### Gaps our skill fills

- Deterministic classification heuristics (decision hits, exception hits, workflow hits) with score-based fallback to `decision`.
- Thread-URL + root-ts seed extraction for the idempotency key (so the same thread always lands at the same `<sha8>.md`).
- Three different frontmatter shapes (decision, exception, workflow) with the right `memory_class` (episodic for decisions, procedural for exceptions and workflows).
- Numbered-step extraction from thread body for workflow classification.
- Provenance frontmatter (`source_type: slack`, `source_id: <root_ts>`, `source_url: <thread_url>`, `captured_at: <iso>`).
- Hand-edit guard via `hand_edited: true`.

### Decision

**Build fresh.** No existing implementation produces the typed-memory write with classification heuristics + sha8 idempotency + workflow / decision / exception shape selection. Same architecture as PR-to-SOP: heuristic-first, operator-refined, stdlib + PyYAML only.

---

## Summary table

| Source | Existing MCP / pattern | Our path |
|---|---|---|
| GitHub | github/github-mcp-server (official, complete) | Wrap + normalize |
| Notion | makenotion/notion-mcp-server (official, MCP-optimized) | Wrap + normalize |
| Linear | cosmix/linear-mcp + Linear official remote MCP | Wrap + normalize |
| Gmail | Google official remote + GongRzhe/Gmail-MCP-Server | Wrap + normalize (PII truncation is load-bearing) |
| PR-to-SOP | claude-code-action (review-only, no typed memory) | Build fresh (heuristic-first, no LLM call) |
| Slack-thread-to-SOP | Slack official MCP (read-only) | Build fresh (heuristic-first, no LLM call) |

## Why no fork or extend decisions

For the 4 ingestion skills, all existing MCPs are:
- Actively maintained by the source platform or a recent community fork.
- Already produce the JSON input shape our normalizer expects.
- Read-only by design, with no vault concept — so a fork would mean forking a remote MCP just to add a vault writer, which is a worse boundary than keeping the read MCP and the vault writer as separate components.

For the 2 synthesizer skills, no existing implementation does the typed-memory write with sha8 idempotency + hand-edit guards + multi-class classification. Building fresh is the only path that produces the contract our vault depends on.

## Open questions for next iteration

1. Does Linear's official remote MCP support the same one-shot `issue + comments + history` shape as `cosmix/linear-mcp`? If the official remote is sufficient, the skill's recommendation should default there (operational reliability, no community fork drift).
2. The Notion official MCP's per-page connection model means a parent-tree walk only works if the parent is already connected to the integration. Surface this requirement in `skills/ingest-notion/SKILL.md` so operators do not hit an empty-walk silently.
3. For Gmail, evaluate whether the personal-data scrub at the public-repo layer is sufficient OR whether the normalizer should additionally hash known personal tokens (vault-config-driven). Current PII guardrail is volume-only (500 char body cap).
