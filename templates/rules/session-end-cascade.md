---
type: rule
purpose: DEPRECATED — superseded by session-close.md. Kept as a redirect stub so existing references don't break.
---

# Session end cascade — DEPRECATED

This file was the prior session-close protocol. It has been superseded by **`session-close.md`** in this same directory.

The new architecture is layered: a UserPromptSubmit hook detects close signals automatically and injects pre-resolved paths and instructions; the model only does the conversation scan and writes; a Stop hook handles aggregators, git snapshot, retention, and a Haiku fallback if the model bails.

**See `session-close.md` for the full protocol.**

The full 7-phase cascade is preserved — nothing was cut. The deprecation collapses two parallel files into one canonical source.
