# Typed memory schemas

This folder holds the JSON Schema (draft-07) definitions for every typed memory primitive the vault uses. Each schema describes the YAML frontmatter shape of a class of files, so downstream consumers (aggregators, agents, MCP tools, HTTP APIs) can read them as structured data instead of guessing.

The schemas are deliberately permissive: every schema sets `additionalProperties: true`, only the fields strictly required for the consumer to function are listed under `required`, and most fields accept `null` so legacy entries continue to validate. The point is to lock the contract just tight enough that the consumer scripts cannot drop entries on parse, while leaving room for the vault to grow.

## The 8 typed memory primitives

### decision

A logged choice point: what was decided, when, at what stakes, at what speed. Lives in `⚙️ Meta/Decisions/`. Each decision file is a small, append-only record. The decision retrospective and `/patterns` skill both query this set. Outcome is left blank at write time and filled in later, which is what makes the decision-outcome trail (manifesto pillar 4) work.

**Field-specific note: `floor`.** The `floor` field is `oneOf [int 1-34, string]` per the schema. `null` is NOT allowed; downstream linters will reject Edit operations on files that have `floor: null`. If a decision is architectural, strategic, or otherwise not tied to the emotional High-Rise framework, OMIT the `floor` field entirely rather than setting it to null. The same rule applies to `journal` and `session` schemas where they reference floor. Codified 2026-05-02 after three 2026-05-01 decision files used `floor: null` and blocked subsequent Edits behind the vault linter until manually stripped.

### journal

A daily entry. Lives in `📓 Journals/`. Carries floor, energy, mood, and tags. Consumed by `journal-index.json`, the `insights` skill (weekly and monthly digests), and the graph builder.

### session

A worktree-scoped record of one Claude Code session. Lives in `⚙️ Meta/Sessions/`. Carries date, label, and worktree slug. Consumed by `aggregate-sessions.py`, which rebuilds `Last Session.md` from the most recent N session files.

### fact

A verifiable claim about the world: a person's role, a metric, a policy, a market number. Required fields: `type`, `claim`. Optional `domain` field groups facts by topic. Facts are the atoms a future fact-rebuild aggregator can re-check against canonical sources, and the unit an agent should cite when asserting "the company knows X."

### workflow

A named, repeatable process: ordered steps, owners, approvals, handoffs, failure modes, edge cases. Required fields: `type`, `name`. Workflows are the substrate runbook generators and agent task planners read before executing multi-step work. The `failure_modes` and `edge_cases` arrays are the explicit place to record what historically went wrong and how to branch around it, instead of letting the model rediscover those edge cases on every run.

### exception

A documented deviation from a workflow, fact, or rule, plus the conditions under which the deviation applies. Required fields: `type`, `exception_summary`. Pointers to the rule it deviates from go in `rule_id`. Exceptions exist because a one-size-fits-all workflow is brittle; recording the deviation as a first-class entry is what stops the underlying defect from re-firing the next time the workflow runs.

### outcome

The observed result of a previously logged decision. Required fields: `type`, `decision_id`. The `vs_expected` enum (`better`, `worse`, `as-expected`, `unclear`) is the join key the decision retrospective uses to surface drift. `lessons_learned` is the array form so downstream consumers can index lessons separately from the prose body.

## The cross-type frontmatter contract

Every schema in this folder also carries five shared optional fields. None are required at the schema level (existing entries pre-date the contract and would invalidate if these were forced). They get populated over time as entries are re-extracted, re-verified, and joined to their sources.

| Field | Type | What it means | When to populate |
|---|---|---|---|
| `provenance` | array of objects | List of independent sources that back this entry. Each entry has `source_type` (one of `slack`, `email`, `notion`, `gdoc`, `whatsapp`, `calendar`, `claude-session`, `manual`), `source_id`, `source_url`, `captured_at` (ISO 8601). | At capture time when the source is known. Add another entry whenever a new source corroborates the same claim. |
| `confidence` | number, 0.0 to 1.0 | How sure the system is the entry is accurate. | At capture time. Re-grade during the verification pass. |
| `freshness_days` | integer | How many days the entry stays fresh before re-verification is recommended. | At capture time, based on the volatility of the underlying claim (a person's role rotates faster than a market segment definition). |
| `last_verified` | string, ISO 8601 date | When the entry was last confirmed by a human or a re-extraction pass. | Each time a verification pass runs and confirms the entry. |
| `source_count` | integer | How many independent sources back this entry. Trivially derivable from `provenance.length`, but stored for fast querying. | Updated whenever `provenance` changes. |

Together these five fields let any consumer ask three questions cheaply: "is this still fresh", "how sure are we", and "where did this come from." That is the substrate for trust-graded retrieval (the agent prefers high-confidence, recently-verified, multi-source entries) and for stale-entry surfacing (a scheduled scan can flag entries whose `last_verified + freshness_days < today`).

## Memory class typology

Every schema also accepts an optional `memory_class` field, with two valid values: `episodic` and `procedural`. The typology is borrowed from cognitive science and applied to the typed-memory substrate so consumers can route reads correctly.

`episodic` memory captures one-time events with a timestamp and a witness. A journal entry is episodic. A session log is episodic. A decision logged at a moment in time is episodic. An observed outcome is episodic. The defining property is that the entry pins down what happened on a specific day; replaying the entry later does not generate a new instance, it only retrieves the one that already exists.

`procedural` memory captures repeatable, time-stable knowledge. A fact about the world is procedural. A workflow with steps is procedural. An exception with branching conditions is procedural. A relationship between two entities is procedural. The defining property is that the entry stays valid across many runs; the agent can pull it once and apply it many times.

| Schema | Default `memory_class` | Why |
|---|---|---|
| `journal` | `episodic` | One day, one entry, one floor. Pinned to a date. |
| `session` | `episodic` | One worktree-scoped session. Pinned to an end timestamp. |
| `decision` | `episodic` | One choice point. Pinned to a decision date. |
| `outcome` | `episodic` | One observation. Pinned to an observed-at timestamp. |
| `fact` | `procedural` | A claim about the world that the agent can re-cite many times. |
| `workflow` | `procedural` | A repeatable named process with ordered steps. |
| `exception` | `procedural` | A documented deviation that re-applies whenever the condition fires. |
| `relationship` | `procedural` | A typed edge that holds across many lookups. |

The default mapping is documented but **not enforced** by the schema. The field is optional, and a writer can override the default when an entry breaks the pattern (for example, a one-off fact that only held for a single quarter is closer to episodic than procedural). When the field is absent, downstream consumers should treat the default as the implicit value.

The point of the typology is to enable the closed-loop learning architecture: agents capture episodic events during execution (a Bash failure, a tool error, an unexpected response shape), and a background consolidation pass scans for recurring episodic patterns and promotes them to procedural memory candidates for human review. See `templates/CLOSED-LOOP-README.md` for the full architecture.

## Entity IDs cross-source linking

Every schema also accepts an optional `entity_ids` field: an object mapping source-system names to IDs in those systems. The field exists so a single typed-memory entry can be joined to its representations in other tools without a separate join table.

The shape is `{"slack": "C0123ABCD", "github_pr": "owner/repo#42", "linear": "TEAM-123"}`. Keys are short canonical names; values are the source-system IDs. Recommended keys (use these where they apply, and add new keys with the same naming convention when a new source needs first-class support):

| Key | Meaning | Example value |
|---|---|---|
| `slack` | Slack channel ID, message timestamp, or thread reference | `C0123ABCD` or `C0123ABCD/1709123456.123456` |
| `github_pr` | GitHub pull request, in `owner/repo#number` form | `acme/api#42` |
| `github_issue` | GitHub issue, in `owner/repo#number` form | `acme/api#101` |
| `jira` | Jira issue key | `PROJ-123` |
| `notion` | Notion page ID | `8a4e2c1f4b8c4...` |
| `gmail` | Gmail message ID or thread ID | `18f8e1...` |
| `linear` | Linear issue identifier | `TEAM-123` |

Naming conventions: lowercase, snake_case, source-system noun first. When a system has multiple ID surfaces (issue vs PR), name them separately. When a source has a single canonical ID surface, use the bare source name.

How downstream systems use it:

- A graph builder can join a `decision` to its underlying `github_pr` discussion thread by reading both entries' `entity_ids.github_pr` and emitting an edge.
- A retrieval-side reranker can boost an entry whose `entity_ids` overlap with the active context (the user is in a PR review session; entries linked to the same PR rank higher).
- A consolidation pass (episodic to procedural) can group recurring episodic events that share the same `entity_ids.github_pr` because they are likely about the same workstream.
- A future deduper can detect that two `fact` entries with overlapping claims and identical `entity_ids.notion` are the same fact captured twice, and merge their provenance arrays.

The field is optional; consumers must handle entries with no `entity_ids` gracefully.

## Skill schema

Skills are themselves typed memory: a skill is procedural memory the agent can call by name. The skill schema is documented separately at `templates/SKILL-SCHEMA-README.md` so the skill contract can evolve independently of the eight typed primitives in this folder.

## Why these schemas matter

These schemas are the vault-side enforcement of pillar 1 of the [Reliability Manifesto](../../RELIABILITY_MANIFESTO.md): vault as ground truth, not LLM memory. The system never trusts what the model remembers between sessions. Every claim an agent makes must trace to a file the company controls. The schemas pin down the shape of that file, so the agent can compile context deterministically instead of pattern-matching on free-form markdown.

The corollary is that schema drift breaks the substrate. If a writer ships an entry whose YAML frontmatter does not match the schema (missing required field, malformed date, wrong type on an enum), the consumer either silently drops the entry or, worse, picks up partial data and emits a corrupt artifact. That is why each schema's `_comment` names the exact consumer script that breaks if YAML is malformed: it makes the failure mode legible at write time.

## How aggregators consume the schemas

`aggregate-decisions.py` and `aggregate-sessions.py` are the two reference consumers shipped today. Both follow the same pattern:

1. Walk the source folder (`⚙️ Meta/Decisions/` or `⚙️ Meta/Sessions/`).
2. Read each file, parse the YAML frontmatter.
3. Skip files whose frontmatter does not parse (silent failure mode below).
4. Sort the surviving files in reverse chronological order using the schema-defined date field.
5. Concatenate them into the rebuild target (`Decision Log.md`, `Last Session.md`).

The silent failure mode matters: if YAML is malformed, the parse raises, the script catches the exception, the file is dropped from the rebuild, and no error surfaces in the rendered log. The entry vanishes. This is why hooks at write time should be the primary defense against malformed frontmatter, and why each schema's `_comment` names the consumer that would lose data.

The five new primitives (`fact`, `workflow`, `exception`, `relationship`, `outcome`) do not yet have aggregator scripts in the public starter; the schemas are landing first so the substrate exists when the aggregators land. A future `aggregate-facts.py` would follow the same pattern: walk a `Facts/` folder, parse frontmatter, group by `domain`, emit a `Fact Sheet.md` rebuild.

## How a downstream consumer should query these primitives

A downstream consumer (an HTTP API, an MCP tool, an agent) should treat the schema as the contract and the file as the row.

For a single-entry lookup:

1. Read the file.
2. Parse the YAML frontmatter.
3. Validate against the corresponding schema in this folder using a draft-07 validator.
4. If validation passes, return the parsed object.
5. If validation fails, return a structured error naming the offending field, do not return partial data.

For a typed query (e.g., "give me every workflow whose `owner` is X"):

1. Glob the source folder.
2. For each file, parse frontmatter and validate.
3. Filter on the typed field.
4. Sort by `last_verified` descending, then by `confidence` descending, so the freshest, most-trusted entries surface first.

For a graph build (e.g., the `relationship` primitive):

1. Walk every file with `type: relationship`.
2. For each, emit one directed edge from `source_entity` to `target_entity`, weighted by `strength`, labeled by `relationship_kind`.
3. Drop edges whose `confidence` is below the consumer's threshold.

The pattern that holds across all queries: the schema is the index, the file is the row, the cross-type contract fields (`provenance`, `confidence`, `freshness_days`, `last_verified`, `source_count`) are the signals you sort and filter on. That is the difference between an LLM that remembers and a vault that knows.
