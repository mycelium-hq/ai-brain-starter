---
name: block-em-dash
enabled: true
event: file
action: block
conditions:
  - field: file_path
    operator: regex_match
    pattern: Substack|LinkedIn|pitch|investor|Sales|Marketing|Press|newsletter|deck
  - field: new_text
    operator: regex_match
    pattern: \u2014
---

**Em dash detected in external-facing content.** Never use em dashes in publishable output. Use commas, colons, periods, or parentheses instead. Rewrite without the em dash and try again.

Scope: Substack, LinkedIn, pitch decks, investor materials, Sales/Marketing paths. Internal notes, journals, scripts, and memory files are not affected.
