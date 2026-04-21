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

- `regex_match` — Python `re.search`
- `contains` — literal substring (no regex)
- `equals` — exact string match
- `not_contains` — literal substring, negated
- `starts_with`, `ends_with`

**There is NO `regex_not_match`, `regex_not`, or negated-regex operator.** Using one makes the condition always return False → rule never fires. To express "regex should NOT match", invert the pattern with a negative lookahead (tempered greedy token) inside a single `regex_match`. Example:

```yaml
# WRONG — rule silently never fires
- field: content
  operator: regex_not_match
  pattern: '- \[ \][^\n]*\[\[[^\]]+\]\]'

# RIGHT — matches tasks WITHOUT a wikilink
- field: content
  operator: regex_match
  pattern: '- \[ \](?:(?!\[\[|\n).){0,300}$'
```

The `(?:(?!X).)*` pattern is a tempered greedy token: "any char as long as the next chars aren't X". Here X is `\[\[` (wikilink start) or `\n` (keep match on one line).

### Supported fields by event/tool

- `file` event (Write, Edit, MultiEdit): `file_path`, `content`, `new_text`/`new_string`, `old_text`/`old_string`
  - `content` on Write returns `tool_input.content`; on Edit returns `tool_input.new_string`. Use `content` if you want both.
  - `new_text` on Write returns empty unless content also matches. Prefer `content`.
- `bash` event: `command`
- `prompt` event (UserPromptSubmit): `user_prompt`
- `stop` event: `reason`, `transcript` (full transcript file contents)

### YAML gotchas

- **Double-quoted strings double-escape regex backslashes.** `"- \\[ \\]"` in YAML gets loaded as `'- \\[ \\]'` (four backslashes in the regex engine's view = literal `\[`, not `[`). **Always single-quote regex patterns** or use unquoted scalars. Single-quoted: `'- \[ \]'` loads as `- \[ \]` verbatim.
- Unquoted patterns with `:` or `#` break YAML. If in doubt, single-quote.
- `$` inside single-quoted strings is literal (good for regex end-of-line).

### Loading behavior

- `load_rules()` in `core/config_loader.py` uses relative glob `.claude/hookify.*.local.md`. **Rules only load when CWD = vault root.** Worktrees under `.claude/worktrees/*/` have CWD = worktree root, which has its own `.claude/`. Rules in the vault-root `.claude/` do NOT apply to worktrees unless duplicated or symlinked.
- `event` filter is strict — a rule with `event: file` never fires on `bash` events and vice-versa.

### Testing a rule before committing

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

---

Codified after a rule was written with a non-existent `regex_not_match` operator and silently never fired. Fix: single `regex_match` with negative lookahead. This cheatsheet exists so the same class of bug is caught at authoring time, not at runtime when content slips past the gate.
