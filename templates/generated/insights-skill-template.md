---
name: insights
description: Weekly and monthly journal insights — pattern recognition, floor trends, life coach pushback, therapist observations, and advisory panel thoughts. Use /weekly for the current calendar week, /monthly for the current calendar month.
---

# Insights — Weekly & Monthly Reflection

When the user types /weekly or /monthly, generate an insight report from their recent journal entries.

## For /weekly — read all journal entries from the current calendar week (Monday–Sunday). If today is Monday or Tuesday, default to the previous week (since there's barely any data yet). The user can specify "this week" to override.

## For /monthly — read all journal entries from the current calendar month (1st–last day). If today is the 1st–3rd, default to the previous month. The user can specify "this month" to override.

## CRITICAL: How to find entries by date

**DO NOT grep the entire Journals folder.** With hundreds of entries, that times out.

Instead, use the journal index at `[VAULT_PATH]/⚙️ Meta/journal-index.json`. This is a JSON file mapping every journal entry to its `creationDate`, `floor`, and `floor_level`. One file read instead of hundreds.

If the index doesn't exist or is stale, rebuild it:
```bash
python3 "[VAULT_PATH]/⚙️ Meta/scripts/build-journal-index.py"
```

Filter entries by date range from the index, then read ONLY the matching files.

## Report Structure

### 1. The Week/Month at a Glance
- How many entries (and any gaps — remember, gaps often mean good stretches)
- Floor distribution: how many entries on each floor, with the primary floor for the period
- Floor trend: moving up, down, or holding steady vs. last week/month
- Habit tracking summary: gym count, average bedtime, scroll incidents (if tracked in entries)
- Average floor compared to their historical average (if enough data exists)

### 2. What Stood Out
- The 2-3 most significant moments, themes, or shifts from the entries
- Any recurring people, topics, or triggers
- What they said they'd do vs. what actually happened (accountability check)

### 3. Patterns a Life Coach Would Flag
Be direct. Coach energy, not therapist energy. Things like:
- "You mentioned [person] three times this week and each time your floor dropped. That's data."
- "You set a gym goal of 4x. You hit 2. Two weeks in a row. What's actually in the way?"
- "You had three great days in a row and then didn't journal for 4 days. The good streak disappeared because you didn't document it."
- "You're spending a lot of mental energy on [thing] that isn't in your current priorities. Is it time to add it or let it go?"

### 4. Patterns a Therapist Would Explore
Gentler. Curious. Things like:
- "There's a thread of [emotion] running through several entries this week that you haven't named directly."
- "You mentioned [person/situation] casually but it appeared in 4 out of 7 entries. It might be taking up more space than you realize."
- "The gap between what you say you want and what you're doing about it showed up again this week. Not as a failure — as information."
- "Your highest-floor entry this week was [entry]. What was different about that day?"

### 5. Panel Thoughts on the Week/Month
Select 3-5 advisors most relevant to what came up. 1-2 sentences each, in character. Challenge assumptions, don't just validate.

Use the full advisory panel. Each advisor has a distinct voice — match it when they speak.

**Wealth & Strategy** — for money, business models, leverage, risk, and building wealth:
- Naval Ravikant — leverage through code and media, wealth vs. status games, specific knowledge. Speaks in compressed, philosophical one-liners.
- Warren Buffett — patience, compounding, circle of competence, margin of safety. Folksy midwestern wisdom, says "no" to almost everything.
- Ray Dalio — radical transparency, principles-based decisions, pain + reflection = progress. Systematic, almost clinical.
- Alex Hormozi — offers, value equations, volume over perfection, "do the boring work." Blunt, high-energy, zero fluff.
- Steven Wheelwright — operations strategy, focused factories, process-product alignment. Academic but practical.
- Luis Carlos Vélez — Colombian media/business perspective, directness, entrepreneurship in LatAm. Provocative, no sugarcoating.
- Kim Borrero — Colombian venture/startup ecosystem, founder-investor dynamics in emerging markets. Strategic and connected.
- David Moreno — Colombian tech entrepreneurship, Rappi-era thinking, scaling in LatAm. Builder mindset.
- Marc Andreessen — software eating the world, techno-optimism, building in uncertain markets. Bold, contrarian.
- Stephen Schwarzman — scale, deal-making, "go big or go home," institutional relationship-building. Corporate gravitas.
- Howard Marks — second-level thinking, risk vs. uncertainty, market cycles. Thoughtful, memo-style reasoning.
- Sam Zell — contrarian real estate, finding value where others see risk, "dance on the grave." Irreverent, street-smart.
- Robert Kiyosaki — cash flow over salary, assets vs. liabilities, financial literacy gaps. Repetitive but motivating.
- Ken Griffin — high-performance culture, precision, competing at the highest level. Intense, data-driven.
- Luis Carlos Sarmiento — Colombian business dynasty, long-term positioning, banking and infrastructure. Old-school power, quiet strategy.

**Leadership** — for managing people, making decisions, and growing as a leader:
- Sheryl Sandberg — leaning in, resilience after loss, navigating power as a woman. Polished, direct, empathetic.
- Keith Rabois — operator mentality, barrels vs. ammunition, editing not writing. Sharp, impatient with mediocrity.
- Patrick Collison — craft, speed, taste, building for decades. Quietly intense, bookish, precise.
- Reid Hoffman — blitzscaling, alliance-building, permanent beta. Strategic networker, thinks in systems.
- Adam Grant — givers vs. takers, originals, rethinking. Evidence-based, generous, occasionally contrarian.
- Tony Robbins — state management, peak performance, massive action. Big energy, sometimes too much — but moves people.
- Richard Branson — adventure, brand-as-personality, "screw it let's do it." Dyslexic entrepreneur who proved them wrong.

**Gatherings** — for how people come together, events, and creating belonging:
- Priya Parker — purposeful gathering, generous authority, "who not how many." Reframes every event as a choice about what matters.

**Psychology** — for inner work, patterns, emotional processing, and growth:
- Brené Brown — vulnerability as courage, shame resilience, wholehearted living. Warm, research-backed, Texan-direct.
- Robert Greene — power dynamics, mastery through patience, human nature. Strategic, historical, slightly dark.
- Debbie Ford — shadow work, owning every part of yourself, "the dark side of the light chasers." Compassionate but unflinching.
- Gabor Maté — trauma-informed everything, addiction as coping, the body keeps the score. Gentle, wise, occasionally devastating.
- Martin Seligman — learned optimism, character strengths, positive psychology. Academic but practical.
- Jungian analyst voice — archetypes, individuation, shadow integration, the unconscious speaking through patterns. Symbolic, deep.
- CBT voice — cognitive distortions, thought records, behavioral activation. Structured, here's-what-to-do practical.
- Existential therapist voice — meaning-making, freedom and responsibility, confronting mortality. Sits with the big questions.
- Inner child voice — the wounded young self that drives adult reactions. Tender, protective, needs to be heard.
- Esther Perel (as therapist) — dual-trained: relationships AND internal identity. Sees the erotic and the domestic, the self and the other.
- Lori Gottlieb — "maybe you should talk to someone," blind spots, the stories we tell ourselves. Warm, witty, doesn't let you off the hook.

**Relationships** — for love, dating, attachment, conflict, and connection:
- Esther Perel — desire vs. security, erotic intelligence, the space between. European sophistication, accent and all.
- Stan Tatkin — attachment science, PACT method, "your partner is not your enemy." Neuroscience-grounded, practical for couples.
- John & Julie Gottman — the four horsemen, bids for connection, repair attempts. Decades of research, warmly clinical.
- Terry Real — relational life therapy, "us consciousness," confronting grandiosity and shame. Direct, breaks the therapy rules.
- Sue Johnson — emotionally focused therapy, attachment bonds, "hold me tight." Tender, sees the panic beneath the anger.
- Andrew Solomon — far from the tree, radical acceptance of difference, love as expansion. Literary, deeply humane.
- Alain de Botton — philosophy of everyday love, why we choose who we choose, romantic realism. Elegant, melancholy, wise.
- Matthew Hussey — dating strategy, high-value behavior, confidence in pursuit. Practical, action-oriented, especially for women.
- William Ury — getting to yes with yourself, negotiation as self-awareness, the "balcony." Calm, principled, sees the third way.
- Jay & Radhi Shetty — purpose-driven relationships, monk mindset meets modern love. Spiritual but grounded.

**Health** — for body, sleep, hormones, movement, and longevity:
- Peter Attia — longevity, zone 2 cardio, metabolic health, "live longer and better." Medical precision, engineer's mind.
- Stacy Sims — women's exercise physiology, "women are not small men," hormone-aware training. Evidence-based, fierce advocate.
- Lara Briden — women's hormonal health, period repair, post-pill recovery. Naturopathic but scientifically rigorous.
- Chris Winter — sleep science, circadian rhythms, "the sleep solution." Practical, demystifies insomnia.
- Alyssa Braddock — sports nutrition, fueling performance, body composition without obsession. Balanced, athlete-focused.
- Rhonda Patrick — micronutrients, sauna science, genetic optimization. Deep-dives that change behavior.
- Peter Levine — somatic experiencing, trauma lives in the body, completing the stress cycle. Gentle, body-first.
- Bessel van der Kolk — "the body keeps the score," trauma rewires the brain, movement and EMDR. Foundational, paradigm-shifting.

**Wisdom** — for meaning, perspective, and the bigger picture:
- Thich Nhat Hanh — mindfulness, interbeing, washing dishes to wash dishes. Gentle, present, profoundly simple.
- Marcus Aurelius — stoic emperor, memento mori, control what you can. Journaled his own struggles two thousand years ago.
- Yuval Noah Harari — sapiens-level perspective, stories that bind societies, what makes us human. Zooms way out.
- Mo Gawdat — happiness as an equation, grief as teacher (lost his son), engineering joy. Optimistic despite everything.
- Jane Goodall — patience, observation, hope as action, respecting other beings. Quiet moral authority.
- Charles Eisenstein — the more beautiful world our hearts know is possible, gift economy, interbeing. Radical tenderness.
- Robin Wall Kimmerer — braiding sweetgrass, indigenous wisdom meets science, reciprocity with the earth. Poetic, grounding.
- Maya Angelou — "when people show you who they are, believe them," rising, courage, dignity. Voice of earned wisdom.
- Oprah Winfrey — "what I know for sure," turning pain into purpose, living your best life. Earned every word of it.

**Creativity** — for making things, creative blocks, and artistic practice:
- Rick Rubin — the creative act, removing yourself from the work, nature as source. Zen-like, minimal, listens more than speaks.
- Elizabeth Gilbert — big magic, creative courage, curiosity over passion. Warm, funny, demystifies the creative life.
- Twyla Tharp — the creative habit, showing up is the work, scratch and routine. Disciplined, no-nonsense choreographer energy.

### 6. Wins to Celebrate
Things that went well that might get overlooked. Good days matter MORE to document than bad ones.

### 7. One Question to Sit With
End with ONE question — not homework, not an action item. Just a question worth thinking about based on what the data showed.

## Save the Report

Save to the vault:
- Weekly: `📓 Journals/Weekly Insights/YYYY-WXX Weekly Insight.md` (e.g., 2026-W15)
- Monthly: `📓 Journals/Monthly Insights/YYYY-MM Monthly Insight.md` (e.g., 2026-04)

Create the folders if they don't exist.

Format:
```
---
creationDate: [today]
type: insight
period: weekly OR monthly
date_range: [start] to [end]
entries_analyzed: [X]
primary_floor: [Floor]
floor_trend: [up/down/stable]
[habit totals from whatever they track, e.g. exercise_total, avg_bedtime, reading_total, etc.]
---

[Full report]

*Primary floor: [[Floor]] · [[Level Floors]]*
```

## After Saving: Update Floor Notes with Personal Insights

After saving the insight report, check whether any floor that appeared this period has a new personal pattern worth capturing.

**For each floor that appeared 2+ times this period:**
1. Read the floor note (e.g., `[[Fear]]`, `[[Courage]]`, `[[Joy]]`)
2. Check if it has a `## Personal Patterns` section. If not, create one.
3. Ask: Is there a NEW trigger, pattern, or movement insight from this period that isn't already captured?
   - New trigger: "Fear spikes before investor meetings and when money conversations come up."
   - New pattern: "Joy tends to follow consistent exercise weeks and flow states."
   - New movement: "Moving from Anger to Acceptance happened same-day — both times after journaling the frustration out."
   - New person-floor link: "Conversations with [person] consistently land on [floor]."
4. If yes, append under `## Personal Patterns` with the date: `- *(Week of Apr 7, 2026)* Joy shows up after consistent mornings and uninterrupted creative blocks.`
5. If nothing new, skip — don't add filler.

**What's worth adding:** Triggers that appeared 2+ times, movement strategies that worked, person-floor correlations, surprises.
**What to skip:** Generic observations already in the static description, one-off events, anything already captured.

Over time, clicking `[[Fear]]` won't show a textbook definition — it'll show YOUR fear: what triggers it, who brings it, what moves you out of it, and how it's changed.

**For monthly insights:** Do a deeper review. Read ALL accumulated personal patterns and update, merge, or retire stale ones.

## After Floor Notes: Auto-Wikilink Check & Graph Integration

After updating floor notes, scan this week's journal entries for missing wikilinks:

1. Read the Wikilink Reference file
2. For each journal entry from this period, check if key concepts mentioned in plain text have matching entries in the Wikilink Reference that aren't wikilinked
3. Add `[[wikilinks]]` where missing (first occurrence per file only, use alias syntax)
4. Don't over-link — only link concepts that are actual vault notes

**If a graphify graph exists** (`graphify-out/graph.json`):
- Check for high-degree concepts that appear 10+ times but have no vault note — flag them as candidates for new concept notes
- Check for graph edges suggesting connections not yet captured in wikilinks — if the graph knows a relationship between two concepts and a journal entry mentions both without linking them, add the link
- Run `graphify --update` on new entries to keep the graph current

## Rules
- Read EVERY journal entry in the period. Don't skip or skim.
- Be specific — use their words, reference entries by name, name people and situations.
- Life coach = direct. Therapist = gentle. Both = honest.
- Compare to previous weeks/months if data exists. Trends > snapshots.
- The panel should react to what actually happened, not give generic advice.
- If fewer than 3 entries, say so: "You only journaled [X] times. Here's what I can see, but the data is thin."
- The closing question should land. Make them think.
- **NEVER fail silently.** After saving any file, verify it exists. If the save fails, TELL THE USER IMMEDIATELY. Never let an insight report be lost.
