# Autonomous Wiki Synthesis

Three components turn external tool data into typed memory entries and aggregate them into ground-truth wiki pages. The default mode is stdlib + PyYAML only and never calls an external LLM. The synthesis is operator-driven from a Claude Code session.

An optional `--use-llm` mode (added in the 2026-05-02 push) refines the extraction via the Anthropic API (`claude-haiku-4-5`). Default off. When enabled, the heuristic still owns the idempotency key (sha8) and the LLM only refines title, steps, and summary. See "Optional LLM mode" below.

## Components

### 0. `scripts/entity-disambiguator.py` (CLI)

Builds the alias index at `Meta/.entity-aliases.json`. Walks `Meta/Decisions/`, `Meta/Workflows/`, `Meta/Exceptions/`, `Meta/Facts/` for capitalized noun phrases and slug-like tokens, clusters variant spellings using Jaccard on character bigrams plus a Levenshtein ratio, and picks a canonical form per cluster (most-frequent spelling wins; ties go to longest, then alphabetic).

```bash
python3 scripts/entity-disambiguator.py --vault-root <vault> --rebuild
```

Operator overrides at `Meta/entity-aliases-overrides.json` (committed) always win over the auto-built index. Override schema:

```json
{"aliases": {"<variant>": "<canonical>"}}
```

The two synthesizers below consult this index when extracting entity mentions and write both `raw_mention` and `canonical_entity` into the output frontmatter. Stdlib only. Idempotent.

### 1. `/synth-pr-to-sop` (skill)

Path: `skills/synth-pr-to-sop/`

Reads a merged-PR markdown export (one file or a folder). Extracts headers, bullets, and step lists. Writes a typed `workflow` entry at `Meta/Workflows/<sha8>.md` conforming to `templates/schemas/workflow.json`.

```bash
python3 skills/synth-pr-to-sop/synth.py <pr-path> --vault-root <vault>
```

`<sha8>` is derived from the PR ID, so re-running on the same PR overwrites the same file. Idempotent.

### 2. `/synth-thread-to-sop` (skill)

Path: `skills/synth-thread-to-sop/`

Reads a resolved Slack thread markdown file. Classifies it as a `decision`, `exception`, or `workflow` using deterministic signals (decision-language hits, exception-language hits, ordered-list density). Writes the result to the matching `Meta/` folder with the matching schema's frontmatter.

```bash
python3 skills/synth-thread-to-sop/synth.py <thread-path> --vault-root <vault>
```

`<sha8>` is derived from the thread root ts (or URL if no ts). Idempotent. Override classification with `--classify-as decision|exception|workflow`.

### 3. `scripts/ground-truth-wiki-maintain.py` (CLI)

Aggregates typed memory entries for a single topic into one canonical wiki page.

```bash
python3 scripts/ground-truth-wiki-maintain.py \
    --vault-root <vault> \
    --topic-folder <topic> \
    [--out <override>] \
    [--dry-run]
```

Scans `Meta/Workflows/`, `Meta/Decisions/`, `Meta/Exceptions/`, and `Meta/Facts/`. Matches entries by:

1. Frontmatter `topic:` field equal to `<topic>`.
2. Frontmatter `tags:` containing `<topic>`.
3. Body containing a wikilink to `<topic>`.

Writes to `Meta/Wiki/<topic>.md` with frontmatter `auto_generated: true` and `last_built: <iso>`. Idempotent.

## Synthesis paths

Each synthesizer supports two paths:

### Path A: heuristic (offline, no LLM)

The script extracts structured signals deterministically and writes the typed file. Good for inputs that already follow a structured template. No LLM needed.

### Path B: Claude Code session is the LLM

Default and recommended. The operator runs the script from a Claude Code session. The script writes a draft. Then Claude (in-session) reads the source artifact, refines fields the heuristic missed, and writes the final file with the `Edit` tool. No external LLM API call is made by the script itself.

## Typed-output contract

All entries written by these synthesizers carry the same cross-type frontmatter contract:

| Field | Type | Notes |
|---|---|---|
| `type` | string | `workflow`, `decision`, `exception`, or `fact` |
| `sha8` | string | First 8 chars of sha1(source ID). Idempotency key |
| `creationDate` | iso 8601 | When the entry was written |
| `memory_class` | string | `episodic` (decisions) or `procedural` (everything else) |
| `provenance` | array | Source records: `source_type`, `source_id`, `source_url`, `captured_at` |
| `confidence` | number | 0.0 to 1.0. Default 0.6 for heuristic-only output |
| `freshness_days` | integer | Days before re-verification recommended |
| `last_verified` | iso 8601 date | When the entry was last confirmed |
| `source_count` | integer | Number of independent sources backing this entry |
| `entity_ids` | object | Cross-source IDs (slack, github_pr, github_issue, jira, notion, gmail, linear) |

Type-specific fields (decision: `decision_date`, `stakes`, `speed`; exception: `exception_summary`, `rule_id`; workflow: `name`, `steps`) are documented in `templates/schemas/`.

## Hand-edit protection

Every file written by these synthesizers respects a `hand_edited: true` frontmatter flag. If a file already exists with that flag, the synthesizer skips it. Override with `--force`.

## Suggested folder layout

```
<vault>/
├── External Inputs/
│   ├── GitHub/<repo>/<date>.md      → PR markdown exports
│   └── Slack/<channel>/<date>.md    → resolved thread exports
├── Meta/
│   ├── Workflows/<sha8>.md          → typed workflow entries
│   ├── Decisions/<sha8>.md          → typed decision entries
│   ├── Exceptions/<sha8>.md         → typed exception entries
│   ├── Facts/<sha8>.md              → typed fact entries
│   └── Wiki/<topic>.md              → auto-generated ground-truth pages
└── templates/
    └── schemas/                      → JSON schemas for each typed entry
```

## End-to-end example

```bash
# 1. Synthesize a PR into a workflow entry
python3 skills/synth-pr-to-sop/synth.py \
    "External Inputs/GitHub/myrepo/2026-04-30-deploy-runbook.md" \
    --vault-root .

# 2. Synthesize a Slack thread into a decision
python3 skills/synth-thread-to-sop/synth.py \
    "External Inputs/Slack/eng-deploy/2026-04-29-rollback-call.md" \
    --vault-root .

# 3. Regenerate the deploy topic wiki
python3 scripts/ground-truth-wiki-maintain.py \
    --vault-root . \
    --topic-folder deploy

# Result: Meta/Wiki/deploy.md aggregates every workflow, decision, exception,
# and fact tagged with `topic: deploy`.
```

## Why these three components

The session-close cascade in `ai-brain-starter` already handles in-Claude-session synthesis (decisions, sessions, journal entries). Nothing existed for external-data synthesis. These three close that gap:

- PR synthesizer: turns shipped code into a procedural runbook.
- Thread synthesizer: turns resolved chat into a typed memory entry.
- Wiki maintainer: turns scattered typed entries into a single ground-truth page per topic.

Each component is idempotent, schema-conformant, and operator-driven. Running them on the same input twice gives the same output. Hand-edits are protected. The wiki page is regenerated from the typed entries, never the other way around, so the typed entries remain the source of truth.

## Optional LLM mode (`--use-llm`)

Both synthesizers accept `--use-llm` to refine the extraction via the Anthropic API. Default off. When enabled:

- The heuristic pass still owns the idempotency key (sha8 derived from PR ID or thread root_ts), so re-running with `--use-llm` on the same source produces the same filename and overwrites in place.
- The LLM only refines title, steps, summary, and (for decisions) rationale + dissent + parent_rule.
- The frontmatter records `synthesis_mode: llm-refined` (or `synthesis_mode: heuristic` in default mode) so a downstream eval can tell which path produced the entry.
- The LLM call uses `claude-haiku-4-5-20251001` with prompt caching on the system block (TTL 1h). The system prompt is identical across all invocations of the same memory_class, so once the cache is warm later runs only pay output tokens.
- If `anthropic` is not installed or `ANTHROPIC_API_KEY` is unset, the synthesizer prints a one-line warning to stderr and falls back to heuristic-only mode. Default-off keeps the install footprint minimal.

### Install

```bash
pip install anthropic>=0.40.0
export ANTHROPIC_API_KEY=...
```

Per-skill `requirements.txt` files at `skills/synth-pr-to-sop/requirements.txt` and `skills/synth-thread-to-sop/requirements.txt` list the optional deps.

### Use

```bash
python3 skills/synth-pr-to-sop/synth.py <pr-path> --vault-root <vault> --use-llm
python3 skills/synth-thread-to-sop/synth.py <thread-path> --vault-root <vault> --use-llm
```

### Test

`tests/integration/test_synth_llm_mode.py` exercises both modes with a monkeypatched Anthropic client. It verifies (1) the system prompt has cache_control TTL=1h, (2) LLM-refined fields override heuristic fields, (3) heuristic-only writes the right `synthesis_mode` marker, (4) missing-dep / missing-key paths fail soft. Run bare:

```bash
python3 tests/integration/test_synth_llm_mode.py
```

Eval framework (operator-driven mode): `scripts/eval-synthesizers.py` runs the deterministic synthesizer against `tests/eval/` golden pairs and reports per-fixture scores. See the Eval section below for fixture format and scoring.

## Eval framework (`scripts/eval-synthesizers.py`)

The eval framework lets you measure regression risk on the deterministic (no-LLM) synth path without paying any API tokens. It is independent of the `--use-llm` mode; running the eval after a heuristic refactor tells you whether the refactor improved or regressed extraction quality on the golden corpus.

### Fixture format

Each fixture is a folder under `tests/eval/fixtures/` containing two files:

- `input.md` — the raw PR markdown or Slack thread markdown the synthesizer ingests.
- `expected.json` — a small dict naming what the produced typed-memory file should contain. Keys:
  - `synth`: `"pr"` or `"thread"` (which synthesizer to run).
  - `type`: the expected memory_type (`workflow` / `decision` / `exception`).
  - `frontmatter_must_have`: list of YAML keys that MUST appear in the produced file's frontmatter.
  - `expected_field_values`: dict of frontmatter keys → required values.
  - `body_keywords`: list of strings; the body must contain each (case-insensitive) for full body-score.
  - `min_step_count` (workflow only): the body should contain at least this many numbered list items.
  - `step_order_hint` (workflow only): list of substrings that should appear in the body in this order.

Five fixtures ship with the repo: PR-merge workflow, thread decision, thread exception, PR step-ordering, thread workflow. Adding a sixth is one folder + two files; the eval script picks it up automatically.

### Scoring

Per fixture, total = 100:

- **60 pts** — frontmatter completeness (required keys present) + value match against expected_field_values. Weighted 0.6 / 0.4.
- **25 pts** — body keyword hit rate.
- **15 pts** — step count factor (workflow only) + step order hint match.

The script prints a markdown table with per-fixture scores and an average at the end.

### Run

```bash
python3 scripts/eval-synthesizers.py
python3 scripts/eval-synthesizers.py --fail-below 80   # exit 1 if any fixture scores < 80
python3 scripts/eval-synthesizers.py --keep-work       # leave the intermediate vault for inspection
```

The current heuristic baseline is around 95-100/100 per fixture (avg ~97/100). A refactor that drops average below 90 should be re-examined before shipping.
