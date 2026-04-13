---
name: insights
description: Weekly and monthly journal insights -- pattern recognition, floor trends, life coach pushback, therapist observations, and advisory panel thoughts. Use /weekly for the current calendar week, /monthly for the current calendar month. Do NOT use for daily journal entries (use daily-journal), cross-session pattern extraction (use patterns), or operational reviews.
argument-hint: "[week or month -- e.g. 'this week', 'last month', or leave blank for default]"
---

When the user types /weekly or /monthly, generate an insight report from their recent journal entries.

## For /weekly -- read all journal entries from the current calendar week (Monday-Sunday). If today is Monday or Tuesday, default to the previous week (since there's barely any data yet). The user can specify "this week" to override.
## For /monthly -- read all journal entries from the current calendar month (1st-last day). If today is the 1st-3rd, default to the previous month. The user can specify "this month" to override.

Journal entries are in: `[VAULT_PATH]/Journals/`

## CRITICAL: How to find entries by date

**DO NOT grep thousands of files.** Use the journal index instead.

### Step 0: Load the journal index
Read `[VAULT_PATH]/Meta/journal-index.json`. This is a JSON file mapping every journal entry to its `creationDate`, `floor`, and `floor_level`. It's fast, one file read instead of scanning the whole vault.

If the index doesn't exist or is more than 7 days old, rebuild it first:
```bash
/usr/bin/python3 "[VAULT_PATH]/Meta/scripts/build-journal-index.py"
```

### Step 1: Filter entries by date range
From the index, filter entries where `date` falls within the target week or month. This gives you the exact list of filenames to read.

### Step 2: Read ONLY the matching files
Read the full content of each matching file. Do NOT read files outside the date range. With the index, you're reading 5-15 files instead of searching the entire vault.

## Report Structure

### 1. The week/month at a glance
- How many entries (and any gaps, gaps often mean good stretches)
- Floor distribution: how many entries on each floor, primary floor for the period
- Floor trend: up, down, or stable vs. previous period
- Habit tracking summary: gym count, average bedtime, scroll incidents

### 2. What stood out
- 2-3 most significant moments, themes, or shifts
- Recurring people, topics, or triggers
- What they said they'd do vs. what actually happened

### 3. Patterns a life coach would flag
Be direct. Coach energy. Specific references to entries:
- "You mentioned [person] three times and each time your floor dropped. That's data."
- "You set a gym goal of 4x. You hit 2. Two weeks in a row. What's actually in the way?"
- "You had three great days then stopped journaling. The good streak disappeared because you didn't document it."
- "You're spending mental energy on [thing] that isn't in your current priorities. Add it or let it go."

### 4. Patterns a therapist would explore
Gentler. Curious. Not prescriptive:
- "There's a thread of [emotion] running through several entries you haven't named directly."
- "You mentioned [person/situation] casually but it appeared in 4 out of 7 entries. More space than you realize."
- "The gap between what you say you want and what you're doing about it showed up again. Not failure, information."
- "Your highest-floor entry was [entry]. What was different about that day?"

### 5. Panel thoughts on the week/month
Select 3-5 advisors most relevant to what came up. 1-2 sentences each, in character. Challenge assumptions, don't just validate.

Use the full advisory panel. Each advisor has a distinct voice, match it when they speak.

**Wealth & Strategy** -- for money, business models, leverage, risk, and building wealth:
- Naval Ravikant -- leverage through code and media, wealth vs. status games, specific knowledge. Speaks in compressed, philosophical one-liners.
- Warren Buffett -- patience, compounding, circle of competence, margin of safety. Folksy midwestern wisdom, says "no" to almost everything.
- Ray Dalio -- radical transparency, principles-based decisions, pain + reflection = progress. Systematic, almost clinical.
- Alex Hormozi -- offers, value equations, volume over perfection, "do the boring work." Blunt, high-energy, zero fluff.
- Steven Wheelwright -- operations strategy, focused factories, process-product alignment. Academic but practical.
- Luis Carlos Velez -- Colombian media/business perspective, directness, entrepreneurship in LatAm. Provocative, no sugarcoating.
- Kim Borrero -- Colombian venture/startup ecosystem, founder-investor dynamics in emerging markets. Strategic and connected.
- David Moreno -- Colombian tech entrepreneurship, Rappi-era thinking, scaling in LatAm. Builder mindset.
- Marc Andreessen -- software eating the world, techno-optimism, building in uncertain markets. Bold, contrarian.
- Stephen Schwarzman -- scale, deal-making, "go big or go home," institutional relationship-building. Corporate gravitas.
- Howard Marks -- second-level thinking, risk vs. uncertainty, market cycles. Thoughtful, memo-style reasoning.
- Sam Zell -- contrarian real estate, finding value where others see risk, "dance on the grave." Irreverent, street-smart.
- Robert Kiyosaki -- cash flow over salary, assets vs. liabilities, financial literacy gaps. Repetitive but motivating.
- Ken Griffin -- high-performance culture, precision, competing at the highest level. Intense, data-driven.
- Luis Carlos Sarmiento -- Colombian business dynasty, long-term positioning, banking and infrastructure. Old-school power, quiet strategy.

**Leadership** -- for managing people, making decisions, and growing as a leader:
- Sheryl Sandberg -- leaning in, resilience after loss, navigating power as a woman. Polished, direct, empathetic.
- Keith Rabois -- operator mentality, barrels vs. ammunition, editing not writing. Sharp, impatient with mediocrity.
- Patrick Collison -- craft, speed, taste, building for decades. Quietly intense, bookish, precise.
- Reid Hoffman -- blitzscaling, alliance-building, permanent beta. Strategic networker, thinks in systems.
- Adam Grant -- givers vs. takers, originals, rethinking. Evidence-based, generous, occasionally contrarian.
- Tony Robbins -- state management, peak performance, massive action. Big energy, sometimes too much, but moves people.
- Richard Branson -- adventure, brand-as-personality, "screw it let's do it." Dyslexic entrepreneur who proved them wrong.

**Gatherings** -- for how people come together, events, and creating belonging:
- Priya Parker -- purposeful gathering, generous authority, "who not how many." Reframes every event as a choice about what matters.

**Psychology** -- for inner work, patterns, emotional processing, and growth:
- Brene Brown -- vulnerability as courage, shame resilience, wholehearted living. Warm, research-backed, Texan-direct.
- Robert Greene -- power dynamics, mastery through patience, human nature. Strategic, historical, slightly dark.
- Debbie Ford -- shadow work, owning every part of yourself, "the dark side of the light chasers." Compassionate but unflinching.
- Gabor Mate -- trauma-informed everything, addiction as coping, the body keeps the score. Gentle, wise, occasionally devastating.
- Martin Seligman -- learned optimism, character strengths, positive psychology. Academic but practical.
- Jungian analyst voice -- archetypes, individuation, shadow integration, the unconscious speaking through patterns. Symbolic, deep.
- CBT voice -- cognitive distortions, thought records, behavioral activation. Structured, here's-what-to-do practical.
- Existential therapist voice -- meaning-making, freedom and responsibility, confronting mortality. Sits with the big questions.
- Inner child voice -- the wounded young self that drives adult reactions. Tender, protective, needs to be heard.
- Esther Perel (as therapist) -- dual-trained: relationships AND internal identity. Sees the erotic and the domestic, the self and the other.
- Lori Gottlieb -- "maybe you should talk to someone," blind spots, the stories we tell ourselves. Warm, witty, doesn't let you off the hook.

**Relationships** -- for love, dating, attachment, conflict, and connection:
- Esther Perel -- desire vs. security, erotic intelligence, the space between. European sophistication, accent and all.
- Stan Tatkin -- attachment science, PACT method, "your partner is not your enemy." Neuroscience-grounded, practical for couples.
- John & Julie Gottman -- the four horsemen, bids for connection, repair attempts. Decades of research, warmly clinical.
- Terry Real -- relational life therapy, "us consciousness," confronting grandiosity and shame. Direct, breaks the therapy rules.
- Sue Johnson -- emotionally focused therapy, attachment bonds, "hold me tight." Tender, sees the panic beneath the anger.
- Andrew Solomon -- far from the tree, radical acceptance of difference, love as expansion. Literary, deeply humane.
- Alain de Botton -- philosophy of everyday love, why we choose who we choose, romantic realism. Elegant, melancholy, wise.
- Matthew Hussey -- dating strategy, high-value behavior, confidence in pursuit. Practical, action-oriented, especially for women.
- William Ury -- getting to yes with yourself, negotiation as self-awareness, the "balcony." Calm, principled, sees the third way.
- Jay & Radhi Shetty -- purpose-driven relationships, monk mindset meets modern love. Spiritual but grounded.

**Health** -- for body, sleep, hormones, movement, and longevity:
- Peter Attia -- longevity, zone 2 cardio, metabolic health, "live longer and better." Medical precision, engineer's mind.
- Stacy Sims -- women's exercise physiology, "women are not small men," hormone-aware training. Evidence-based, fierce advocate.
- Lara Briden -- women's hormonal health, period repair, post-pill recovery. Naturopathic but scientifically rigorous.
- Chris Winter -- sleep science, circadian rhythms, "the sleep solution." Practical, demystifies insomnia.
- Alyssa Braddock -- sports nutrition, fueling performance, body composition without obsession. Balanced, athlete-focused.
- Rhonda Patrick -- micronutrients, sauna science, genetic optimization. Deep-dives that change behavior.
- Peter Levine -- somatic experiencing, trauma lives in the body, completing the stress cycle. Gentle, body-first.
- Bessel van der Kolk -- "the body keeps the score," trauma rewires the brain, movement and EMDR. Foundational, paradigm-shifting.

**Wisdom** -- for meaning, perspective, and the bigger picture:
- Thich Nhat Hanh -- mindfulness, interbeing, washing dishes to wash dishes. Gentle, present, profoundly simple.
- Marcus Aurelius -- stoic emperor, memento mori, control what you can. Journaled his own struggles two thousand years ago.
- Yuval Noah Harari -- sapiens-level perspective, stories that bind societies, what makes us human. Zooms way out.
- Mo Gawdat -- happiness as an equation, grief as teacher (lost his son), engineering joy. Optimistic despite everything.
- Jane Goodall -- patience, observation, hope as action, respecting other beings. Quiet moral authority.
- Charles Eisenstein -- the more beautiful world our hearts know is possible, gift economy, interbeing. Radical tenderness.
- Robin Wall Kimmerer -- braiding sweetgrass, indigenous wisdom meets science, reciprocity with the earth. Poetic, grounding.
- Maya Angelou -- "when people show you who they are, believe them," rising, courage, dignity. Voice of earned wisdom.
- Oprah Winfrey -- "what I know for sure," turning pain into purpose, living your best life. Earned every word of it.

**Creativity** -- for making things, creative blocks, and artistic practice:
- Rick Rubin -- the creative act, removing yourself from the work, nature as source. Zen-like, minimal, listens more than speaks.
- Elizabeth Gilbert -- big magic, creative courage, curiosity over passion. Warm, funny, demystifies the creative life.
- Twyla Tharp -- the creative habit, showing up is the work, scratch and routine. Disciplined, no-nonsense choreographer energy.

### 5b. First-principles audit

Scan `[VAULT_PATH]/Meta/Decisions/` for any decisions logged this period with `stakes: high`. Check whether they have `deconstruct: true` in their YAML frontmatter.

- If any high-stakes decisions were made WITHOUT a deconstruct pass, flag them:
  > "You made [X] high-stakes decision(s) this week without running a first-principles check: [decision name(s)]. Not every decision needs one, but if any of these feel like you followed a playbook instead of thinking it through, it's not too late to run `/deconstruct` on them."
- If ALL high-stakes decisions were deconstructed, note it as a win.
- If there were no high-stakes decisions this period, skip this section silently.

This is the accountability loop for first-principles thinking. The deconstruct skill catches decisions in real time. This catches the ones that slipped through.

### 5b2. Decision retrospective

Scan `[VAULT_PATH]/Meta/Decisions/` for active decision files (those NOT in the `Archive/` subfolder). For each one:

1. **Check if enough time has passed** to evaluate the outcome. Use the `speed` field as a guide: if `speed: Instant` or `speed: Hours`, it's ready for retrospective within a week. If `speed: Days`, wait 2-4 weeks. If `speed: Weeks`, wait 1-3 months.
2. **If ready:** prompt the user to fill in `Outcome` (what actually happened) and `Pattern` (what this reveals about how they decide). Don't fill these in yourself; ask the user. The learning only works if they articulate it.
3. **If Outcome AND Pattern are both filled in:** move the file to `[VAULT_PATH]/Meta/Decisions/Archive/`. The decision is complete; it has taught what it can teach.
4. **Surface any patterns across decisions:** "You've made 3 decisions from a tired/anxious state this month, and 2 of them had worse outcomes than expected." Or: "Every time you decided quickly on hiring, the outcome was positive. Your instinct here is reliable."

If there are no active decisions to review, skip this section silently.

### 5c. Skill usage snapshot (if data exists)

Check if `[VAULT_PATH]/Meta/skill-usage-log.jsonl` exists and has entries for the period. If it does, include a brief summary:
- Which skills were used most this week/month
- Any skills that haven't been used at all (might indicate forgotten capabilities)
- Any usage spikes (e.g. "you ran /graphify 8 times this week, up from 2 last week")

Keep this to 2-3 sentences. If the log file doesn't exist or is empty, skip this section silently.

### 5d. Obsidian ecosystem check (monthly only, skip for /weekly)

Once a month, scan the Obsidian community plugin registry (github.com/obsidianmd/obsidian-releases, specifically community-plugins.json) for:
- New AI, knowledge-graph, or automation plugins relevant to your setup
- Updates to plugins you use (Smart Connections, Local REST API, Juggl)
- Community patterns or architecture ideas worth adopting

Keep to 2-3 sentences: what's new, whether any of it is worth installing or investigating. If nothing relevant, skip silently.

### 6. Wins to celebrate
Things that went well that might get overlooked. Good days matter MORE to document than bad ones.

### 7. One question to sit with
End with ONE question. Not homework. Not an action item. A question worth thinking about based on what the data showed. Make it specific to THEIR week, not a fortune cookie.

## Save the Report

- Weekly: `[VAULT_PATH]/Journals/Weekly Insights/Mon. D-D, YYYY Weekly.md` (e.g., `Apr. 7-13, 2026 Weekly.md`). Use 3-letter month abbreviation with period. Cross-month example: `Mar. 31-Apr. 6, 2026 Weekly.md`
- Monthly: `[VAULT_PATH]/Journals/Monthly Insights/Mon. YYYY Monthly.md` (e.g., `Apr. 2026 Monthly.md`)

Create folders if they don't exist.

Format:
```markdown
---
creationDate: [today]
type: insight
period: weekly OR monthly
date_range: [start] to [end]
entries_analyzed: [X]
primary_floor: [Floor]
floor_trend: [up/down/stable]
gym_total: [X]
avg_bedtime: [time]
---

[Full report]

*Primary floor: [[Floor]] · [[Level Floors]]*
```

## After Saving: Update Floor Notes with Personal Insights

After saving the insight report, check whether any floor that appeared this period has a new personal pattern worth capturing. Floor concept notes live in the vault's concept folder (e.g., `Notes/` or `Writing/The High-Rise/Floors/`).

**For each floor that appeared 2+ times this period:**
1. Read the floor note (e.g., `[[Fear]]`, `[[Courage]]`, `[[Joy]]`)
2. Check if it has a `## Personal Patterns` section. If not, create one.
3. Ask: Is there a NEW trigger, pattern, or movement insight from this period that isn't already captured?
   - New trigger: "Fear spikes around investor meetings and when [person] calls about money."
   - New pattern: "Joy tends to follow 3+ gym days and flow states on writing."
   - New movement: "Moving from Anger to Acceptance happened same-day twice, both times after journaling the frustration out loud."
   - New person-floor link: "Conversations with [person] consistently land on [floor]."
4. If yes, append it under `## Personal Patterns` with the date range: `- *(Week of Apr 7-13, 2026)* Joy tends to show up after back-to-back gym days and uninterrupted writing mornings.`
5. If nothing new, skip silently, don't add filler.

**What makes a pattern worth adding:**
- A trigger that's appeared 2+ times across different entries (not a one-off)
- A movement strategy that actually worked (not theoretical)
- A person or situation that consistently correlates with a specific floor
- A surprise, something the user wouldn't expect to see in their data

**What to skip:**
- Generic observations ("Fear feels scary"), that's already in the static description
- One-time events that won't recur
- Anything already captured in a previous update

Over time, clicking `[[Fear]]` won't show a textbook definition. It'll show YOUR fear: what triggers it, who brings it, what moves you out of it, and how it's changed over the months.

**For monthly insights:** Do a deeper review. Read ALL personal patterns accumulated so far and see if any need updating, merging, or retiring. A pattern from January might not hold in April.

## After Floor Notes: Auto-Wikilink Check

After updating floor notes, scan this week's journal entries for missing wikilinks:

1. Read the Wikilink Reference at `[VAULT_PATH]/Meta/Wikilink Reference.md`
2. For each journal entry from this period, check if key concepts mentioned in plain text have matching entries in the Wikilink Reference that aren't wikilinked
3. Add `[[wikilinks]]` where they're missing (first occurrence per file only, use alias syntax)
4. Don't over-link, only link concepts that are actual vault notes, not random words

**Graphify integration:** If `graphify-out/graph.json` exists, also check:
- Are there new high-degree nodes from the graph that should be concept notes but don't exist yet? If a concept appears 10+ times across entries but has no vault note, flag it: "The graph shows [concept] appears frequently, want me to create a note for it?"
- Are there graph edges that suggest connections not yet captured in wikilinks? E.g., if the graph knows [person] is connected to Fear but a journal entry mentions [person] without linking to [[Fear]], that's a missed connection worth adding as context.

### 8. System health audit (monthly only, skip for /weekly)

Run `python3 "[VAULT_PATH]/Meta/scripts/context-audit.py"` and include the results. Then pull 3 panel voices to comment on the overall setup:

- **Patrick Collison** (Stripe co-founder, speed + quality) on whether the system is enabling fast, high-quality work or adding overhead
- **Keith Rabois** (PayPal/Square exec, operational clarity) on whether there's unnecessary complexity that should be cut
- **One rotating panelist relevant to the month's themes** on whether the vault structure is actually serving the work that matters most right now

The panel should answer: *"What's one thing about this setup that's slowing you down that you haven't noticed?"*

If the audit script flags warnings, include specific fix recommendations. If everything passes, say so briefly and move on.

## Rules
- Read EVERY entry in the period. Don't skip or skim.
- Be specific, use their words, reference entries by name, name people and situations.
- Life coach = direct. Therapist = gentle. Both = honest.
- Compare to previous weeks/months if data exists. Trends > snapshots.
- The panel should react to what actually happened, not give generic advice.
- If fewer than 3 entries, say so: "You only journaled [X] times. Here's what I can see, but the data is thin."
- The closing question should land. Make them think.
- **NEVER fail silently.** After saving any file, verify it exists. If the save fails, TELL THE USER IMMEDIATELY. Never let an insight report be lost.
