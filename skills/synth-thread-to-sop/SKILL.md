---
type: skill
name: synth-thread-to-sop
description: Read a resolved Slack thread markdown export and synthesize a typed memory entry (decision, exception, or workflow) into Meta/. Trigger /synth-thread-to-sop <slack-thread-markdown-file>. Use when a thread captures a one-time decision, a documented deviation, or a repeatable procedure worth filing. Do NOT use for raw Slack ingestion (use the Slack ingest skill for that) or for PR sources (use /synth-pr-to-sop).
argument-hint: "<slack-thread-markdown-file> [--vault-root PATH] [--dry-run]"
tool_access:
  - Bash
  - Read
  - Write
required_inputs:
  - name: thread_path
    type: string
    required: true
    description: Path to a Slack thread markdown file (e.g. External Inputs/Slack/<channel>/<date>.md).
  - name: vault_root
    type: string
    required: false
    description: Vault root. Defaults to current working directory.
output_shape:
  format: markdown-file
  fields:
    output_path: absolute path to Meta/Decisions/<sha8>.md, Meta/Exceptions/<sha8>.md, or Meta/Workflows/<sha8>.md
    classification: decision, exception, or workflow
    source_thread_url: thread permalink or root ts
---

# /synth-thread-to-sop

Turn a resolved Slack thread into a typed memory entry. The script first classifies the thread (decision, exception, or workflow definition) using deterministic signals, then writes a typed file at the right location with the right schema.

## When to run

After a thread reaches a resolution worth filing. Examples:

- A thread where the team picks one option over another for a one-time call (decision, episodic)
- A thread where someone explains "we don't follow rule X for client Y" (exception, procedural)
- A thread where someone walks the team through a multi-step procedure (workflow, procedural)

## Two synthesis paths

### Path A: heuristic (offline, no LLM)

The script classifies the thread by counting decision-language hits, exception-language hits, and step-language hits. Highest-scoring class wins. Good for clearly structured threads. Run:

```bash
python3 skills/synth-thread-to-sop/synth.py <thread-path> --vault-root <vault>
```

### Path B: Claude Code session is the LLM

Default and recommended. The script writes a draft. Then Claude reads the source thread, refines the classification if wrong, fills in fields the heuristic missed, and writes the final file. No external LLM API call is made by the script.

## Step 1: Locate the thread markdown

The argument is a single Slack thread markdown file. Expected structure (any of these is fine):

- A thread exported by your ingest pipeline at `External Inputs/Slack/<channel>/<date>.md`
- A markdown file with a series of `**user (timestamp):** message` lines
- A markdown file with frontmatter that contains `thread_url`, `root_ts`, or `permalink`

The script extracts the thread URL or root timestamp from frontmatter first, then from the body if absent.

## Step 2: Run the script

```bash
python3 skills/synth-thread-to-sop/synth.py <thread-path> --vault-root <vault>
```

Output (one of):

- `Meta/Decisions/<sha8>.md` if classified as a decision
- `Meta/Exceptions/<sha8>.md` if classified as an exception
- `Meta/Workflows/<sha8>.md` if classified as a workflow

The `<sha8>` is the first 8 chars of a sha1 of the thread root ts (or URL if no ts). Idempotent.

## Step 3: Refine in-session (optional)

If the classification looks wrong, override with `--classify-as decision|exception|workflow`. Then read the file and improve fields with the Edit tool.

## Step 4: Verify

```bash
python3 -c "import yaml; yaml.safe_load(open('<vault>/Meta/Decisions/<sha8>.md').read().split('---')[1])"
```

If the YAML parses, the file is valid.

## Frontmatter contract

All entries share these fields:

```yaml
type: decision | exception | workflow
source_thread_url: <permalink-or-root-ts>
sha8: <8-char hash>
memory_class: episodic (decisions) | procedural (workflows, exceptions)
creationDate: <iso>
entity_ids:
  slack: <root-ts>
provenance:
  - source_type: slack
    source_id: <root-ts>
    source_url: <permalink>
```

Type-specific fields follow the schemas in `templates/schemas/`.

## Classification heuristics

The script counts hits for each class:

- decision: "let's go with", "we picked", "decided to", "going with X", "agreed", "approved"
- exception: "exception", "we don't", "skip", "override", "deviate", "for this client only", "one-off"
- workflow: ordered lists (>=3 numbered items), "step 1", "step 2", "first... then... finally"

Highest score wins. Ties resolve toward decision (the most common shape). Use `--classify-as` to override.

## Entity disambiguation

When `Meta/.entity-aliases.json` exists (built by `scripts/entity-disambiguator.py`), this skill consults it during entity extraction. Each detected mention writes both `raw_mention` and `canonical_entity` into the `entity_mentions` frontmatter list, so downstream queries can group variant spellings under one canonical form. Operator overrides at `Meta/entity-aliases-overrides.json` always win. When the index is missing, `canonical_entity` falls back to the raw mention.

## Rules

- Never overwrite a file that has been hand-edited unless `--force`.
- Never call an external LLM API from the script. The synthesis is operator-driven.
- Keep the body short; the value is in the typed frontmatter.
- The thread markdown is read-only; this skill never writes back to it.
- If a thread has no parseable structure, write a stub entry with `confidence: 0.3` and flag for refinement.
