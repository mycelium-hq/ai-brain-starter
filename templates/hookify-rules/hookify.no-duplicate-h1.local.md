---
name: no-duplicate-h1
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.md$
  - field: new_text
    operator: regex_match
    pattern: "^# .+"
---

Filename = title in Obsidian. No `# Title` after frontmatter. Use H2 or start with content. Remove the H1.

Scope: all .md files. In Obsidian, the filename renders as the note title. Adding `# Title` after frontmatter creates a visible duplicate. Templates, scripts, and note writes all must avoid the H1-after-frontmatter pattern.
