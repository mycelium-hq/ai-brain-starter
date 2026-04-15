---
name: block-wrong-fact-example
enabled: false
event: file
action: block
conditions:
  - field: new_text
    operator: regex_match
    pattern: WRONG_PATTERN_HERE
---

**Fact check failed.** [Describe the correct fact here]. Fix the text and try again.

To use this template:
1. Replace WRONG_PATTERN_HERE with a regex that catches the misattribution
2. Update the message with the correct fact
3. Set enabled: true
4. Rename the file to describe your specific rule
