# Migration: Personalized journal accountability + optional gratitude check

## What changed

The journal setup (Phase 10) and the generated journal skill no longer assume specific habits. Previously, the setup examples and skill templates were gym-heavy — gym was always the first example, the first detailed template, and the default in entry format. This made the journal feel prescriptive for users who don't care about the gym.

### Changes

1. **Setup question 3** (habit tracking): Reordered examples — sleep, mood, reading, exercise instead of leading with "gym days"
2. **Setup question 5** (accountability): Rewritten to emphasize "whatever YOU tend to let slide" with diverse examples — sleep, reading, exercise, screen time, meditation, spending
3. **New setup question 6** (gratitude/abundance check-in): Now opt-in instead of default. "Do you want a gratitude or abundance check-in each session?" Previously this was hardcoded into every journal.
4. **Step 3 (accountability check)**: Preamble now says "build from whatever the user asked for, don't assume gym." Added reading and meditation templates. Added: "The user defines what matters, not the skill."
5. **Step 2.5 (abundance/gratitude)**: Now conditional — only runs if user opted in via question 6
6. **Entry format template**: Habit fields use generic examples (`exercise_count`, `reading_mins`) instead of `gym_count`. Accountability tracking line is dynamic. Gratitude line conditional.
7. **Insights frontmatter**: Replaced hardcoded `gym_total` / `avg_bedtime` with a dynamic placeholder that adapts to whatever the user tracks.

## How to apply (existing users)

On next pull, Claude should detect this migration and ask two questions:

### Question 1 — Accountability personalization

> "Quick update to your journal: I used to default to gym tracking for accountability, but that's not everyone's thing. What do YOU want me to hold you accountable on? Some examples: sleep consistency, reading, exercise, meditation, screen time, spending — or anything else you tend to let slide. I'll update your journal skill to track exactly what you pick."

Take their answer and update their `~/.claude/skills/daily-journal/SKILL.md`:
- Update Step 3 (accountability check) to use their specific items
- Update the entry format template with their habit fields in YAML frontmatter and the accountability tracking line

### Question 2 — Gratitude opt-in

> "Also — your journal currently includes a gratitude check-in ('what's one thing you're grateful for right now?'). Some people love it, some find it corny. Want to keep it, or skip it?"

- If they want it: no change needed (Step 2.5 stays)
- If they don't: update their `~/.claude/skills/daily-journal/SKILL.md` to remove or skip Step 2.5

### Auto-detection

The auto-update hook should trigger this on pull. To detect whether this migration has already been applied, check for the string `"question 6 from setup"` in `~/.claude/skills/daily-journal/SKILL.md`. If present, the migration was already applied. If not, ask the two questions above.

## Rollback

No destructive changes. The old gym-heavy defaults still work — this just makes them personalized. To revert, re-run `/setup-brain` and answer the journal questions again.

## Why

The journal should feel like YOUR journal, not a template. Gym tracking is perfect for some people and irrelevant for others. Same with gratitude check-ins. The skill should adapt to the user, not the other way around.
