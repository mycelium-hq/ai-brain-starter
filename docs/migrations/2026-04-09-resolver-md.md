# Migration: RESOLVER.md files

## What changed
Key directories now get a `RESOLVER.md` — a short decision tree that answers "does X live here?" before you create anything.

## Why
Vaults decay into ambiguity. The same type of content ends up in multiple folders because there was never a written rule for where it belongs. RESOLVER.md files make the decision tree explicit and permanent — Claude reads it before creating any file in that folder.

## How to apply

Create a `RESOLVER.md` in each key folder. Minimum: `👤 CRM/`, `📝 Notes/`, `💡 Originals/`.

**👤 CRM/RESOLVER.md:**
```markdown
# Does this live in CRM/?

1. Is this a real person you've interacted with or plan to? → YES: create [Name].md here
2. Is it a company, org, or brand (not a specific person)? → NO: Business/ or Notes/
3. Is it a public figure you've never met? → NO: Notes/ or Books/
4. Is it a group you have a relationship with as a whole? → YES, if you interact with them as a unit
```

**📝 Notes/RESOLVER.md:**
```markdown
# Does this live in Notes/?

1. Is this your own original idea, framework, or thesis? → NO: 💡 Originals/
2. Is this from a book you read? → NO: 📚 Books/
3. Is this a psychology/behavioral concept? → Maybe: 🧠 Psychology/ if that folder exists
4. Is this an article, course, or how-to you learned from? → YES: create here
5. Is this a concept that belongs to a specific project? → NO: that project's folder
```

**💡 Originals/RESOLVER.md:**
```markdown
# Does this live in Originals/?

1. Is this a framework, metaphor, or thesis you originated? → YES
2. Did you read this somewhere else, even if you agree with it? → NO: Notes/ or Books/
3. Is this a synthesis of other people's ideas? → Borderline — only if the synthesis itself is original
4. Would you be the one cited if someone referenced this? → YES: belongs here
```

Add more RESOLVER.md files to any folder where you find yourself unsure what belongs there.
