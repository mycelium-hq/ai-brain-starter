## Hookify rule authoring cheatsheet

Source of truth for writing `.claude/hookify.*.local.md` rules. Check here before adding a new rule.

### File format

```yaml
---
name: kebab-case-rule-name      # must be unique; shows in system messages
enabled: true
event: file                      # file | bash | prompt | stop
action: warn                     # warn | block (block exits non-zero)
conditions:
  - field: <field>
    operator: <op>
    pattern: <pattern>
---

Warn/block message body (markdown).
```

All conditions are ANDed. To OR conditions, write two rules with the same message.

### Supported operators (core/rule_engine.py _check_condition)

- `regex_match`: Python `re.search`
- `contains`: literal substring (no regex)
- `equals`: exact string match
- `not_contains`: literal substring, negated
- `starts_with`, `ends_with`

**There is NO `regex_not_match`, `regex_not`, or negated-regex operator.** Using one makes the condition always return False, so the rule never fires. To express "regex should NOT match", invert the pattern with a negative lookahead (tempered greedy token) inside a single `regex_match`. Example:

```yaml
# WRONG: rule silently never fires
- field: content
  operator: regex_not_match
  pattern: '- \[ \][^\n]*\[\[[^\]]+\]\]'

# RIGHT: matches tasks WITHOUT a wikilink
- field: content
  operator: regex_match
  pattern: '- \[ \](?:(?!\[\[|\n).){0,300}$'
```

The `(?:(?!X).)*` pattern is a tempered greedy token: "any char as long as the next chars aren't X". Here X is `\[\[` (wikilink start) or `\n` (keep match on one line).

### Negative lookahead with `re.search`: anchor with `^`

`re.search()` tries every position in the string. A pattern like `(?!.*/Archive/).*foo` does NOT actually exclude `/Archive/` paths, because the engine can skip past the negative lookahead and match later. Anchor with `^` so the lookahead evaluates from position 0:

```yaml
# WRONG: Archive paths still match
pattern: '(?!.*/Archive/).*Sensitive/.+\.md$'

# RIGHT: anchored, Archive correctly excluded
pattern: '^(?!.*/Archive/).*Sensitive/.+\.md$'
```

### Supported fields by event/tool

- `file` event (Write, Edit, MultiEdit): `file_path`, `content`, `new_text`/`new_string`, `old_text`/`old_string`
  - `content` on Write returns `tool_input.content`; on Edit returns `tool_input.new_string`. Use `content` if you want both in one field.
  - `new_text` is now equivalent to `content` on Write (falls back to `tool_input.content` when `new_string` is absent). Older hookify versions returned empty for `new_text` on Write. If your rule was authored against that bug, swap to `content` for clarity.
- `bash` event: `command`
- `prompt` event (UserPromptSubmit): `user_prompt`
- `stop` event: `reason`, `transcript` (full transcript file contents)

### YAML gotchas

- **Always single-quote regex patterns.** Single-quoted YAML strings store characters verbatim: backslashes, brackets, dollar signs, all literal. This is the only quoting style that's safe for regex.
- **Unquoted patterns starting with `[` break YAML.** `pattern: [A-Z].*` makes YAML read `[A-Z]` as a flow sequence (a list with one item), not a string. Result: parser error, rule skipped at load time. Always single-quote when the pattern contains `[`.
- **Unquoted patterns starting with `\` break YAML.** `pattern: \[owner\]` produces a YAML error on the bare backslash. Single-quote it.
- **Unquoted patterns with `:` or `#` break YAML.** Both are reserved characters. When in doubt, single-quote.
- **Double-quoted strings process escape sequences.** `"\d{8}"` becomes `\d{8}` (correct for regex), but it's confusing because the source file shows `\d` while the loader stores `\d`. Single quotes are easier to reason about.
- `$` inside single-quoted strings is literal (correct for regex end-of-line).

If your rule isn't firing and the test harness says it's missing from the loaded rule list, check stderr for a YAML parse warning. That's almost always an unquoted pattern.

### Loading behavior

- `load_rules()` in `core/config_loader.py` uses relative glob `.claude/hookify.*.local.md`. **Rules only load when CWD = vault root.** Worktrees under `.claude/worktrees/*/` have CWD = worktree root, which has its own `.claude/`. Rules in the vault-root `.claude/` do NOT apply to worktrees unless duplicated or symlinked.
- `event` filter is strict. A rule with `event: file` never fires on `bash` events and vice-versa.

### Companion PreToolUse hooks

Sometimes a rule needs more than regex matching. For example, "warn when writing to a sensitive folder, but only if the file isn't already protected by frontmatter." A hookify rule can detect the path; the protection check needs to read the file or another config.

For these cases, write a companion PreToolUse Python hook in `~/.claude/hooks/` and register it in `settings.json`. The hook reads `tool_input` from stdin, runs whatever logic it needs (file reads, config lookups, regex matching), and outputs either:

- `{}`: silent passthrough
- `{"systemMessage": "..."}`: warn (no block)
- `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`: block

**MCP tools cannot be called from a hook subprocess.** MCP servers run in the parent Claude process, not in hook children. If you need MCP-equivalent logic, replicate it by reading the underlying config files directly. Pattern: a hook that reads `agents/some-mcp/config.yaml` and emits a warning is more reliable than one that tries to invoke `mcp__some-mcp__some_tool` from the subprocess (which will silently fail).

### Testing a rule before committing

Single-rule probe:

```bash
cd "${VAULT_ROOT}"
echo '{"tool_name":"Write","tool_input":{"file_path":"<path>","content":"<content>"}}' \
  | python3 ~/.claude/plugins/local/hookify-plugin/hooks/pretooluse.py
```

Expected output:
- Rule fires: `{"systemMessage": "**[rule-name]**\n..."}`
- Rule does not fire: `{}`
- Python errors: `{"systemMessage": "Hookify error: ..."}`

Test at least: positive case, negative case, wrong-file-path case, wrong-tool case. If you added a negative lookahead, also test a mixed-content input (one line matches, one line doesn't) to confirm per-line behavior.

**Full regression harness:** `python3 templates/scripts/hookify-rule-tests.py` (after copying it to a location where it can find your rules). The harness defines a list of `(rule_name, tool_type, path, content, expect_fire, label)` tuples and pipes each into the hookify subprocess, asserting that fire-expectation matches reality. Run after any rule change OR any hookify engine update. See the script header for usage.

---

Codified after a rule was written with a non-existent `regex_not_match` operator and silently never fired. Fix: single `regex_match` with negative lookahead. This cheatsheet exists so the same class of bug is caught at authoring time, not at runtime when content slips past the gate.
