# Skill schema (Structured Agentic Execution)

A skill is no longer just SKILL.md prose. It is a structured executable object with declared tool access, hard policy constraints, required inputs, and a documented output shape. Callers (and validators) read the frontmatter to know what the skill is permitted to do, what it needs, and what it returns.

## Two-layer enforcement

`hooks/validate-skill-frontmatter.py` runs two independent passes per tool call.

1. Write-time schema validation. Fires on Write|Edit|MultiEdit to `skills/**/SKILL.md`. Validates the projected post-edit frontmatter against `templates/schemas/skill.json`. Blocks malformed files at the write boundary so the catalog never goes structurally broken. Bypass: `SKILL_VALIDATION_BYPASS=1`.
2. Invocation-time capability sandboxing. Fires on every tool call when an active skill context is detected. Reads the active skill's `tool_access` whitelist and BLOCKS tool calls that are not on the list. Lifts skills from "documented contract" to "enforced sandbox". Bypass: `SKILL_SANDBOX_BYPASS=1`.

The two bypass flags are independent. Setting one does not disable the other.

## Active-skill detection

The sandbox pass needs to know which skill is currently driving. Detection order:

1. `CLAUDE_ACTIVE_SKILL_PATH` env var. Absolute path to a SKILL.md file.
2. `CLAUDE_ACTIVE_SKILL` env var. Skill name (slug). Resolved against `skills/<name>/SKILL.md` first, then `~/.claude/skills/<name>/SKILL.md`, then `~/.claude/skills/ai-brain-starter/skills/<name>/SKILL.md`.
3. Fall through. No active skill, sandboxing pass is skipped.

A harness that wants per-skill capability scoping should set `CLAUDE_ACTIVE_SKILL` (or the path variant) on the subprocess that invokes the skill, and unset it on exit. Without one of these signals the hook stays out of the way.

## Where the schema lives

`templates/schemas/skill.json`. JSON Schema draft-07. Validated by `hooks/validate-skill-frontmatter.py` on every Write or Edit to a path matching `skills/**/SKILL.md`. Bypass with `SKILL_VALIDATION_BYPASS=1` if you need to commit a partial file.

## Required fields

- `type`: const `"skill"`. Identifies the primitive.
- `name`: slug-style name, matching the skill folder.

## Recommended fields

- `description`: human-readable summary used for skill discovery in the catalog.
- `trigger`: slash command or invocation hint (e.g. `/diagnose`).
- `argument-hint`: free-form hint about expected arguments.

## Structured execution fields

These four fields lift skills from "prose Claude reads" to "structured executable object the harness can reason about."

- `tool_access`: array of strings. Whitelist of tool names this skill is permitted to call. Empty array means the skill takes no tool actions (pure prose or analysis). Names match canonical tool ids (`Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`) or MCP tool ids (`mcp__server__tool`).
- `policy_constraints`: array of `{rule, exception_handling}` objects. Each entry expresses a single hard constraint as an imperative ("Never write to public repos without scrub") plus the documented failure path ("abort and surface to user"). Reviewers and callers know what happens at the edge.
- `required_inputs`: array of `{name, type, required, description}` objects. Documents the inputs the caller must (or may) supply. A skill with no inputs uses an empty array.
- `output_shape`: object describing what the skill returns. Free-form for now: callers benefit from any structure, and different skills return different shapes (a markdown report, a JSON record, a terminal report). Tighten in a future revision.

## Cross-type contract fields

Shared with the other 6 typed memory primitives (`decision`, `journal`, `outcome`, `relationship`, `session`, `workflow`).

- `provenance`: array of source objects (`source_type`, `source_id`, `source_url`, `captured_at`).
- `confidence`: 0.0 to 1.0.
- `freshness_days`: integer, days before re-verification is recommended.
- `last_verified`: ISO 8601 date.
- `source_count`: integer.

## Validator hook

`hooks/validate-skill-frontmatter.py` is a PreToolUse hook with two passes.

Pass 1 (write-time schema validation):
- Fires only on `skills/**/SKILL.md`.
- Projects the post-edit file content (current file plus the Edit substitution) before validation.
- Parses frontmatter, runs `jsonschema.Draft7Validator` against `templates/schemas/skill.json`.
- Blocks malformed writes with a deny decision plus a stderr message naming the schema violation. Exit code is non-zero.
- Bypass with `SKILL_VALIDATION_BYPASS=1`.

Pass 2 (invocation-time capability sandboxing):
- Fires on every tool call when `CLAUDE_ACTIVE_SKILL` (or `CLAUDE_ACTIVE_SKILL_PATH`) is set.
- Reads the active skill's SKILL.md frontmatter and resolves its `tool_access` whitelist.
- Blocks tool calls whose `tool_name` is not on the list with the message `SKILL SANDBOX: skill X declares tool_access=[...]; attempted to call tool Y. Blocked. Bypass: SKILL_SANDBOX_BYPASS=1.`.
- A skill that does not declare `tool_access`, or declares it as a non-list, gets a no-op (sandbox not enforced).
- Bypass with `SKILL_SANDBOX_BYPASS=1`.

Both passes are fail-open: any internal error (PyYAML missing, schema file missing, unexpected exception) returns allow rather than spuriously blocking the user. Performance budget is <200ms total.

To wire the hook into your harness, add an entry to `settings.json` under `hooks.PreToolUse` matching tool names `Write|Edit|MultiEdit` AND a second entry matching the broader set of tool names you want sandboxed (or use `*`). Both entries can point at the same script. Pass 1 is a no-op when the file path does not match `skills/**/SKILL.md`; pass 2 is a no-op when no active skill is set.

## Migration path for existing SKILL.md files

Existing skills shipped with descriptive frontmatter only (`name`, `description`, `trigger`, `argument-hint`). To bring a skill up to the structured contract:

1. Add `type: skill` as the first frontmatter line. The validator requires it.
2. Add `tool_access`. Be conservative: list only the tools the skill actually calls. If the skill is pure analysis, use `[]`.
3. Add `policy_constraints`. Transcribe the rules from the SKILL.md body that read like "never," "always," "do not." Pair each with the failure path the skill takes when the rule would be violated.
4. Add `required_inputs`. Walk the skill's argument-hint and any input the body asks the user to provide.
5. Add `output_shape`. Document what the caller gets back: format (markdown, JSON, terminal-report) plus the fields or sections.
6. Leave the body unchanged. Frontmatter is the contract; the body is the implementation guide.

The three skills shipped in this repo as worked examples are `diagnose`, `security-snapshot`, and `setup-vault-types`. Read their frontmatter for the canonical pattern.

## Validator smoke test

Schema validation pass:

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/test-skill/SKILL.md","content":"---\ntype: skill\nname: test\n---\n"}}' | python3 hooks/validate-skill-frontmatter.py
```

A valid skill returns `permissionDecision: allow`. A malformed one returns `permissionDecision: deny` with the schema violation in `permissionDecisionReason`.

Capability sandbox pass:

```bash
# Block a Write when the active skill only declares tool_access=[Read]:
echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/x.md","content":"x"}}' \
  | CLAUDE_ACTIVE_SKILL_PATH=/path/to/skills/read-only-skill/SKILL.md \
    python3 hooks/validate-skill-frontmatter.py

# Bypass:
echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/x.md","content":"x"}}' \
  | CLAUDE_ACTIVE_SKILL_PATH=/path/to/skills/read-only-skill/SKILL.md \
    SKILL_SANDBOX_BYPASS=1 \
    python3 hooks/validate-skill-frontmatter.py
```

The first call returns `permissionDecision: deny` with the SKILL SANDBOX message. The second returns `allow`.
