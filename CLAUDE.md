# ai-brain-starter — Claude Instructions

## Repo structure rules

**Before creating any new file or folder, always check what already exists:**

1. Run `ls` on the root to see top-level structure
2. Grep for the concept in `SKILL.md` — most skills (journal, insights, accountability, etc.) are embedded as **generated templates inside the main SKILL.md**, not standalone files
3. The only standalone skill folder in this repo is `meeting-todos/` — everything else lives inside `SKILL.md`

**The pattern:** `SKILL.md` contains the full setup flow that *generates* skills into the user's `~/.claude/skills/` directory at runtime. Adding a new skill means editing the right Phase inside `SKILL.md`, not creating a new folder.

## Current standalone sub-skills
- `meeting-todos/SKILL.md` — extract action items from meeting notes
- Everything else (journal, insights, onde-weekly, etc.) → embedded in `SKILL.md`
