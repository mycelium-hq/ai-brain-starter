# data/ — durable project memory

This directory is where your agentic OS remembers things across sessions. The
kernel reads it at the start of non-trivial work and writes decisions here so the
next session inherits them instead of rediscovering them.

Suggested layout (create as you need them):

- `decisions/` — one file per hard-to-reverse decision: what, why, the trade-off,
  and the date. The next session reads these before re-litigating a settled call.
- `context.md` — the project's ubiquitous language: the terms your team uses and
  exactly what they mean, so the model never paraphrases a canonical name.
- `glossary.md` — domain terms an outsider would not know.

Keep entries short and factual. This is a log the agents trust, so never write a
claim here you have not verified.

`.gitkeep` keeps the directory tracked while it is empty — delete it once you add
real content.
