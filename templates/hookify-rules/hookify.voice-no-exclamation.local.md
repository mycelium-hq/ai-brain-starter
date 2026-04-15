---
name: warn-exclamation-marks
enabled: true
event: file
action: warn
conditions:
  - field: new_text
    operator: regex_match
    pattern: "[A-Z][a-z].*!\\s"
---

**Exclamation mark detected.** Your voice style avoids exclamation marks. Rewrite with a period or convey energy through word choice, not punctuation.
