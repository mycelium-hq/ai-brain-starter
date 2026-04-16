---
name: compress-claude-docs
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: "(/memory/|/\\.claude/hookify\\.|⚙️ Meta/rules/|CLAUDE\\.md$)"
---

You are writing to a Claude-facing doc (memory file, hookify rule, vault rule, or CLAUDE.md).

Compression rules apply. Enforce them BEFORE submitting this write:
- Dense caveman prose. No filler. 100% info, 0% fluff.
- No "This means...", "For example...", "In other words...", "It's important to note..."
- No re-explaining what a code block already shows.
- `**Why:**` and `**How to apply:**` only if each is under 25 words.
- Frontmatter description under 80 chars.
- Bullets only for 3+ items. Otherwise one-liners.
- Preserve ALL facts/dates/paths/code, strip ALL narrative padding.

If your pending content has multi-sentence explanations, filler transitions, or "As mentioned above..." style prose, rewrite it before proceeding.

Scope: memory files, hookify rules, vault rule files, and CLAUDE.md. Human-facing docs (READMEs, CHANGELOGs, journal entries, meeting notes) are not affected.
