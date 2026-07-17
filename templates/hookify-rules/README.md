# Hookify Rule Templates

These are example rules for the [hookify plugin](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/hookify) from Anthropic's official claude-code repo. They enforce behavioral rules at the tool level, catching mistakes before they happen.

## Setup

1. Install hookify: In Claude Code, run `/plugin install hookify` or clone from the [claude-code repo](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/hookify)
2. Copy any rules you want to your vault's `.claude/` directory:
   ```bash
   cp templates/hookify-rules/hookify.*.local.md .claude/
   ```
3. Customize the patterns and messages for your context
4. Rules are active immediately, no restart needed

## Rule types

- **block**: Prevents the operation entirely. Use for hard rules (wrong facts, personal data leaks)
- **warn**: Shows a message but lets the operation proceed. Use for style guidance

## Creating your own rules

File naming: `.claude/hookify.{rule-name}.local.md`

```yaml
---
name: my-rule-name
enabled: true
event: file          # file, bash, stop, prompt, all
action: warn         # warn or block
conditions:
  - field: new_text  # new_text, file_path, command, content
    operator: contains  # contains, regex_match, equals, not_contains, starts_with, ends_with
    pattern: bad thing
---

Your message when this rule triggers.
```

## Available templates

| Rule | Type | What it catches |
|------|------|----------------|
| `voice-no-exclamation` | warn | Exclamation marks in writing (for direct/minimal voice styles) |
| `fact-check-template` | block | Template for catching specific misattributions or wrong facts |
| `public-repo-firewall` | block | Personal names/data leaking into public repos |
| `dangerous-rm` | block | `rm -rf` commands without confirmation |
| `warn-filesystem-walk-without-bounded-read` | warn | Recursive Python content walkers missing the shared bounded read |
| `warn-delegated-task-needs-source` | warn | Delegated to-do (`[owner:: …]`) with no `[[link]]` or URL to its brief/source |

## Authoring guide and regression harness

- **Authoring cheatsheet:** `templates/rules/hookify-authoring.md` covers operators, supported fields, the negative-lookahead pattern (no `regex_not_match` operator exists), YAML quoting gotchas (`[` and `\` patterns must be single-quoted), companion PreToolUse hooks for logic that goes beyond regex, and how to test a rule manually.
- **Regression harness:** `templates/scripts/hookify-rule-tests.py` is a copy-then-edit script for running a list of `(rule_name, tool_type, path, content, expect_fire, label)` tuples through the hookify subprocess. Catches three classes of bug: (1) non-existent operators that silently never fire, (2) YAML parse errors that drop a rule at load time, (3) pattern logic regressions after a rule edit. Run it after any rule change OR after upgrading the hookify plugin. Exit 0 means all pass.
