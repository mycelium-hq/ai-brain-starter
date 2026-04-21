# Migration: Originals Folder

## What changed
New `💡 Originals/` folder added to the core vault structure. It's explicitly protected for the user's own frameworks, theses, metaphors, and original ideas — captured verbatim in their exact phrasing.

## Why
Most vaults mix the user's own thinking with things they read and learned. Over time, it becomes impossible to distinguish what you actually originated from what you absorbed. The Originals folder solves this with a hard separation: if you would be cited as the source, it lives here.

## How to apply

1. Create `💡 Originals/` at your vault root (if it doesn't exist)
2. Create `⚙️ Meta/Folder Resolvers/💡 Originals.md` with this decision tree (see [2026-04-21 resolver migration](2026-04-21-resolvers-to-meta.md) for why resolvers now live in Meta):

```markdown
# Does this live in Originals/?

1. Is this a framework, metaphor, or thesis you originated? → YES
2. Did you read this somewhere else, even if you agree with it? → NO: Notes/ or Books/
3. Is this a synthesis of other people's ideas? → Borderline — only if the synthesis itself is original
4. Would you be the one cited if someone referenced this? → YES: belongs here
```

3. Think about what you've built that has no explicit home yet — personal frameworks, recurring metaphors, theories you've developed through years of thinking. Create one note per idea. File name = the idea itself.

4. Add this rule to your CLAUDE.md Vault Rules section:

> **Originals folder is protected.** When I express an original framework, metaphor, or thesis — in conversation, in a journal entry, anywhere — capture it verbatim in 💡 Originals/ immediately. Use my exact phrasing. Never paraphrase. File name = the idea itself.
