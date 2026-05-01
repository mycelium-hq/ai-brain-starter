---
type: skill
name: synth-pr-to-sop
description: Read a merged-PR markdown export and synthesize a typed workflow SOP into Meta/Workflows/. Trigger /synth-pr-to-sop <pr-markdown-file-or-folder>. Use when a closed PR captures a repeatable process worth filing as a procedural memory entry. Do NOT use for in-session synthesis (that runs through session-close cascade) or for non-PR sources (use /synth-thread-to-sop for Slack threads).
argument-hint: "<pr-markdown-file-or-folder> [--vault-root PATH] [--dry-run]"
tool_access:
  - Bash
  - Read
  - Write
required_inputs:
  - name: pr_path
    type: string
    required: true
    description: Path to a single PR markdown file (e.g. External Inputs/GitHub/<repo>/<date>.md) or a folder of them.
  - name: vault_root
    type: string
    required: false
    description: Vault root. Defaults to current working directory.
output_shape:
  format: markdown-file
  fields:
    workflow_path: absolute path to Meta/Workflows/<sha8>.md
    name: extracted workflow name
    steps: array of step objects
    source_pr_id: PR identifier
---

# /synth-pr-to-sop

Turn a merged PR into a typed workflow entry. The PR's title becomes the workflow name. The PR description, commits, and review notes become ordered steps. The result is a single markdown file with `type: workflow` frontmatter that the wiki-maintainer aggregates into a topic page.

## When to run

After a PR ships that captures a process worth filing. Examples:

- A PR that updates a deploy runbook
- A PR that documents a new onboarding step
- A PR that codifies a fix-and-followup pattern

## Two synthesis paths

The script supports two modes. Pick one before running:

### Path A: heuristic (offline, no LLM)

The script extracts headers, bullets, and commit subjects deterministically. Good for PRs that already follow a structured template. Run:

```bash
python3 skills/synth-pr-to-sop/synth.py <pr-path> --vault-root <vault>
```

### Path B: Claude Code session is the LLM

You (the operator) run this skill from a Claude Code session. The script first runs the heuristic pass and writes a draft. Then Claude reads the PR markdown directly, refines the steps, owners, and edge cases, and writes the final file. No external LLM API call is made by the script. Claude is the LLM, your hands on the keyboard are the operator. This is the default and recommended path.

## Step 1: Locate the PR markdown

Argument can be:

- A single file (e.g. `External Inputs/GitHub/myrepo/2026-04-30.md`)
- A folder of PR exports (e.g. `External Inputs/GitHub/myrepo/`)

If a folder, the script walks every `.md` file and processes each one. Idempotent: re-running on the same PR overwrites the same `Meta/Workflows/<sha8>.md`.

## Step 2: Run the heuristic pass

```bash
python3 skills/synth-pr-to-sop/synth.py <pr-path> --vault-root <vault>
```

Output:

- `Meta/Workflows/<sha8>.md` (typed workflow file)
- stdout (workflow name + path)

The `<sha8>` is the first 8 chars of a sha1 of the PR ID. This makes the file deterministic and re-runnable.

## Step 3: Refine in-session (optional)

Read the workflow file Claude just wrote. Compare against the source PR. Improve:

- `name`: make it action-oriented
- `steps`: split combined steps, name owners
- `failure_modes`: add what could go wrong
- `edge_cases`: add atypical inputs

Write back with the Edit tool. Do not change the `source_pr_id`, `sha8`, or `creationDate` fields.

## Step 4: Verify

```bash
python3 -c "import yaml; yaml.safe_load(open('<vault>/Meta/Workflows/<sha8>.md').read().split('---')[1])"
```

If the YAML parses, the file is valid.

## Frontmatter contract

Every workflow file written by this skill has:

```yaml
type: workflow
name: <extracted>
steps: [...]
source_pr_id: <pr-id>
sha8: <8-char hash>
memory_class: procedural
creationDate: <iso>
provenance:
  - source_type: github
    source_id: <pr-id>
```

Optional fields the operator can add: `owner`, `topic`, `failure_modes`, `edge_cases`, `approvals`, `handoffs`.

## Rules

- Never overwrite a workflow file that has been hand-edited unless `--force`.
- Never call an external LLM API from the script. The synthesis is operator-driven.
- Keep step descriptions imperative and short.
- The PR markdown is read-only; this skill never writes back to it.
- If the PR has no parseable structure, write a stub with a single step and flag it for refinement.
