---
name: block-dangerous-rm
enabled: true
event: bash
pattern: rm\s+-rf
action: block
---

**Dangerous rm command detected.** This could delete important files. Verify the path is correct, consider a safer approach, and make sure you have backups before proceeding.
