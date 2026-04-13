---
type: meta
description: Track your decisions over time so you can learn patterns about how you decide
---

# Decision Log

*Track decisions to learn patterns over time. What you chose, why, what you were feeling, and what actually happened.*

This is a journal for the **how** of your decisions, not just the what. The point is that after 6 months you can look back and see: "I keep choosing speed over thoroughness when I'm tired" or "every time I decided from Fear, the outcome was worse than I expected." Patterns are invisible in the moment and obvious in aggregate.

## What to capture per decision

- **What:** The decision in one sentence
- **Why:** The reasoning — what tipped it
- **Floor / State:** What emotional state you were in (use your floor framework, or just `tired / focused / anxious / clear-headed / etc.`)
- **Stakes:** Low / Medium / High
- **Speed:** Instant / Hours / Days / Weeks
- **Outcome:** (fill in later, weeks or months later) What actually happened
- **Pattern:** (fill in later) What this reveals about how you decide

You don't need to log every decision — only the ones where you'd want to look back and ask *"why did I do that?"* The threshold is "decisions worth a 5-minute write-up." For most people that's 1–3 a week.

## Why fill in Outcome and Pattern later

The point of leaving these blank at decision-time is that you can't grade your own decision from inside the moment. You need distance. Set a calendar reminder for 30 days later (or 90, or 6 months — depends on the decision's time horizon) and come back. The retrospective is where the learning lives.

## Archive lifecycle

Decisions live in `Meta/Decisions/` as "active" until both **Outcome** and **Pattern** are filled in. The weekly/monthly insights skill (section 5b2) reviews active decisions and prompts you to complete them when enough time has passed. Once both fields are filled, the file moves to `Meta/Decisions/Archive/`. The aggregator rebuilds this Decision Log view from both active and archived files, so nothing is lost. The archive keeps the active folder focused on decisions that still need follow-up.

---

## How to read this log

Once you have ~20 entries, run:

```dataview
TABLE floor AS "Floor", stakes AS "Stakes", outcome AS "Outcome"
FROM "Meta/Decisions"
GROUP BY floor
```

(Or whatever folder you keep them in.) The patterns by emotional state are usually the most revealing.

---

## Template for a new entry

Copy this block, paste it under the current month heading, fill in.

```markdown
### YYYY-MM-DD — Short title of the decision
- **What:** One sentence
- **Why:** What tipped it. Specific facts, not vibes.
- **Floor / State:** Your emotional/cognitive state at decision time
- **Stakes:** Low / Medium / High
- **Speed:** Instant / Hours / Days / Weeks
- **Outcome:** *(fill in later)*
- **Pattern:** *(fill in later)*
```

---

## 2026

### 2026-01-15 — Example: Hire a contract designer instead of a full-time UX hire (FICTIONAL)
- **What:** Hire a contract designer for 3 months instead of opening a full-time UX role.
- **Why:** Cash runway tight, full-time hire would commit ~$120k/year fully loaded. Contract gets the same quality output for ~$30k for the period when we actually need the design work. If it works out, hire later from a position of strength.
- **Floor / State:** Reason — felt clear-headed, no time pressure on the call
- **Stakes:** Medium (affects burn rate but reversible)
- **Speed:** Days (slept on it for 3 nights, talked to two advisors)
- **Outcome:** *(fill in 90 days from now)*
- **Pattern:** *(fill in 90 days from now)*

---

*This is a template file. Delete the example entry when you start using it for real, or leave it as a reference.*
