# Existing-implementation audit (Lesson #16)

Per Lesson #16 (MCP Build Runbook), the audit step is mandatory before coding: search public implementations, identify the most feature-complete candidate, list gaps for our use case, and document what we considered + why we chose our path.

Each section ends with the **decision** for that source: fork an existing MCP, extend an existing MCP, build fresh, or wrap an existing remote MCP from inside our skill.

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

## Read-depth discipline: a verdict inherits the read behind it

The audit above scored each source from a deep read of that source. The failure mode to guard against is a verdict that *looks* decisive but stands on a shallow read. Two symmetric versions:

**1. Confident DROP from a shallow read (portfolio / profile audits).** When one pass covers many repos at once (a profile / `?tab=repositories` sweep), each repo's verdict inherits the *shallowest* read applied to that repo. A six-repo pass that only name-checks files gives each repo a name-check, not an audit — even though the memo as a whole may list plenty of candidates.

- A DROP or "pass" from a README-only or filename-only read is **provisional**. Label it as such (e.g. `DROP-provisional (surface read)`), and do not let it claim capability-equivalence ("already in our stack", "1:1 maps to ours", "pattern covered"). Capability-equivalence is a confident claim; it requires reading the actual implementation file, which for many small repos is a root `*.md` / `program.md` / `spec.md`, not the README.
- Worked example: a widely-starred research-loop repo (`karpathy/autoresearch`) was dropped from a profile sweep as "already covered" on a README-only read. A later deep read of its `program.md` — the actual loop spec — overturned the verdict to ADOPT (an objective-gated advance/revert hill-climb plus an append-only keep/discard/crash ledger). The README-only pass had hidden a real adoption for weeks.

**2. Confident ADOPT from a shallow absence check (the mirror).** The DROP failure reads the *external* target too shallowly; the ADOPT failure verifies the *own-stack* absence premise too narrowly. When you adopt something because "we don't have this," verify that absence against the canonical version of your own code — your Git host's API, a Git-host MCP, or `git show origin/main:<path>` across each relevant repo — not a one- or two-location grep, and not a stale local checkout that may lag the canonical branch. A bare "we don't have it" backed only by a local grep is the same thin-read mistake as a confident DROP, pointed inward.

The honest form of an absence claim *shows its evidence* ("grep returned nothing for X across these files"); the dangerous form is a bare premise plus only-local verification. Both directions reduce to one rule: **the strength of a verdict may not exceed the depth of the read behind it.**
