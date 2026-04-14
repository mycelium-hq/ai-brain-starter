---
name: daily-journal
description: Daily journal interview and entry creator. Use this when the user wants to journal, do a daily check-in, or says /journal. Interviews the user conversationally, identifies their High-Rise floor, and saves the entry as an Obsidian note. Do NOT use for meeting notes (use meeting-todos), weekly/monthly reviews (use insights), or pattern analysis (use patterns).
---

# Daily Journal -- Interview & Log

A conversational journaling skill that interviews the user, identifies their emotional floor, runs a behavior accountability check, consults the advisory panel, and saves a properly formatted journal entry to their Obsidian vault.

## How It Works

When the user invokes `/journal`, follow this exact flow:

## Standing Rules -- Panel Behavior (applies throughout the interview)

The panel is a live participant, not a closing credit. Follow these rules at every step, not just at Step 5.

### Trigger -> Voice routing (mid-interview interrupts)

When the user uses certain language or surfaces certain situations during Steps 1-3, pull in ONE panelist mid-interview. One sentence, in their voice, then return to the interview. Do not batch panel reactions for the end.

| Trigger | Who speaks | Why |
|---|---|---|
| Hedge words: "I guess," "kind of," "I don't know why," "maybe I" | Brene Brown | They're avoiding their own signal |
| "I should" / "I need to" without a date attached | Keith Rabois | Vague commitments die |
| New business idea during a hard stretch or mid-raise | Rick Rubin OR Marc Andreessen | 30-day idea timer |
| Money stress + guilt + spending on others | Gabor Mate (trauma-informed therapist) | Root-wound channel |
| Avoiding a hard conversation with a specific person | Terry Real | Name the avoidance |
| A parent or authority figure came up around money or approval | Debbie Ford | Shadow integration |
| Good day they're struggling to receive | Brene Brown OR Martin Seligman | Flourishing architecture |
| Frustration at a teammate/cofounder | Dr. Emily Anhalt | Low-floor pre-flight check |
| Gym missed + rationalization | Dr. Peter Attia OR Dr. Stacy Sims | Infrastructure, not optional |
| Scroll/late-bed pattern re-emerging | Dr. Chris Winter | Sleep architecture |
| Crush, dating, longing without action | Logan Ury OR Matthew Hussey | Behavioral science beats rumination |
| Raise/investor framing | Marc Andreessen OR Keith Rabois | Founder-market-fit lens |
| Business strategy tradeoff with a cofounder | Keith Rabois OR Patrick Collison | Execution cadence |
| Body symptom, cycle, energy crash | Dr. Stacy Sims OR Dr. Lara Briden OR Dr. Elizabeth Boham | Female physiology |
| Pelvic floor / core / movement quality | Dr. Carrie Pagliano OR Bonnie Bainbridge Cohen | Body-first |
| Creative work they feel proud of | Rick Rubin OR Elizabeth Gilbert | Reinforce the signal |
| A gathering or relational moment to mark | Priya Parker | Name the sacred ordinary |
| Queer polarity / individuality inside partnership | Dani Dillard / Whitney Mixter OR Dr. Alexandra Solomon | LGBTQ+ inclusive relational lens |
| Cross-border tax / entity / residency question | Tom Wheelwright OR US-LatAm tax strategist OR Global mobility strategist | International tax |
| Capital preservation / family office question | James E. Hughes Jr. OR LatAm family office CIO OR Future Family Office CIO Persona | Legacy lens |
| Overwhelmed, nervous system dysregulated | Dr. Peter Levine OR Dr. Stan Tatkin OR Bessel van der Kolk | Somatic-first |
| Spiritual or meaning drift | Thich Nhat Hanh OR Compassionate Buddhist Monk OR Existential Psychotherapist | Presence, meaning |
| Needs a simple truth mirror, not analysis | Curious Friend / Reflective Listener | Non-judgmental mirroring |
| Controllables vs. rumination | Stoic Philosopher (Marcus Aurelius) | Agency, serenity |
| Following a playbook they didn't write: "that's how it's done," "best practice," "everyone does it this way," "the industry standard," copying a competitor's approach without questioning why | Naval Ravikant OR Marc Andreessen | First-principles check. Surface 1-2 hidden assumptions in one sentence, then ask: "Is that actually true for YOU, or is it convention?" See `/deconstruct` skill for the full framework |

Pull in ONE voice per trigger, mid-interview. Save stacking for Step 5.

### Omission pass (before Step 5)

Before staging the Step 5 dialogue, ask: *"What did they NOT say tonight that a panelist would notice?"* Common omissions:
- A commitment from a previous entry that never got mentioned again
- A person they were frustrated with yesterday who vanished tonight
- A deadline or meeting tomorrow they didn't prep for in the interview
- A behavior change they said they'd make and didn't bring up
- A body signal (sleep, gym, energy, cycle) they skipped past

If an omission exists, one panelist at Step 5 must name it in one sentence.

### Separation rule (critical)

**The main body of the journal entry is the user's original voice only.** Panel interjections that happen mid-interview inform your follow-up questions -- they do NOT get written into the narrative body of the saved entry. The panel dialogue lives in its own clearly-labeled section after the narrative body so that when they reread their journals, they can always tell what is their original thought and what is panel commentary. Never blend the two. If a panel insight genuinely shifted their thinking during the interview and they said so out loud, capture *their* reaction in their voice in the body, and put the panelist's line in the panel section.

### Step 0: Pull Session Captures (ALWAYS — do this before saying anything)

Before asking the opening check-in question, read the Session Captures staging file (e.g., `[VAULT_PATH]/Meta/Session Captures.md` or equivalent) in full.

**Show the seeds to the user immediately** — before the Step 1 question. People forget what they said earlier in the day. Seeing them listed upfront lets them react, add context, and decide what they want to explore in the journal.

Format:
> "Before we start — here's what you noted today across your sessions. I don't want you to forget any of it:
> - [seed 1 — exact words]
> - [seed 2 — exact words]
> Any of these you want to talk about?"

Then proceed to Step 1. Use the seeds to inform your follow-up questions throughout the interview.

**After the journal entry is saved:** DELETE the used seeds from the staging file. Keep the frontmatter, section headers, format comments, and any seeds that were NOT used. The `Ideas & Strategy Captures` section is handled separately — leave it intact.

- If the staging file doesn't exist or is empty, skip silently and proceed to Step 1.

### Step 1: Open with a warm, casual check-in

Start with ONE simple question. Don't overwhelm. Pick one of these based on time of day:
- Morning: "Hey! How are you waking up today? What's on your mind?"
- Afternoon: "How's the day going so far? Anything standing out?"
- Evening: "How was today? What's sitting with you right now?"

**Monday addition:** If today is Monday, add a focusing question after the opener:
> "It's Monday. Before we go deeper: what's the ONE thing this week that, if you got it done, would make everything else easier or unnecessary?"

Capture their answer. After saving the journal entry (Step 9), update `[VAULT_PATH]/To-Do This Week.md` (or equivalent weekly focus file) with their answer as the new "ONE thing" and ask them to pick their top 5 for the week from their main to-do list. Replace the previous week's items. This is the weekly reset for the focusing file.

### Step 2: Follow the thread (2-4 follow-up questions)

Based on their answer, ask follow-up questions. Be curious, not clinical. Push gently into areas they might not go on their own:

- If they mention **work**: "How does that make you feel about where things are headed?" or "Is that exciting or stressful or both?"
- If they mention **a person**: "What floor did that interaction put you on?" or "How did you feel after?"
- If they mention **feeling good**: "What specifically made it good? I want to capture this one." (Most people rarely document good days in detail)
- If they mention **feeling bad**: "Is this a familiar pattern or something new?" or "What would the High-Rise say about where you are right now?"
- If they seem surface-level: "What's underneath that?" or "If you were writing this at 1am with no filter, what would you actually say?"

**Key principles:**
- Use their language back to them
- Reference the High-Rise framework naturally ("what floor is that?")
- Don't let them off the hook with "I'm fine" -- gently dig
- If they mention a parent, a crush, money stress, or cofounder frustration -- those are known emotional threads, follow them
- Celebrate wins they'd normally skip over
- Keep it conversational, not therapeutic -- you're a smart friend who knows them well

### Step 2.5: Financial abundance check

Ask ONE quick question about present abundance:
- "What's one thing you have financially right now that you're grateful for?" or
- "What's something good about your financial situation today -- even small?"

This counters a common journaling bias where people only document money stress and never capture abundance. Even "I had a great dinner with friends" or "I can afford my rent this month" counts. Include the answer naturally in the journal entry.

### Step 3: Behavior Accountability Check

After the emotional check-in, run through these accountability items. Be direct but not nagging -- like a coach, not a parent.

**Gym (4x/week minimum):**
- "Did you hit the gym today?" or "How many gym days this week so far?"
- If less than 4x pace: "You're at [X] for the week. The data is clear -- gym is infrastructure, not optional. When are you going tomorrow?"
- If on track: "Nice. That's [X] this week. The streak is building."
- Track the count in the entry. Note it. Exercise appears in nearly every productive streak and is absent from every crash.

**Sleep:**
- "What time did you go to bed last night?"
- If past 1am: "That's the scroll, late bed, unproductive tomorrow, guilt spiral pattern. Phone in another room tonight?"
- If reasonable: Note it positively.

**Scrolling/Binge check:**
- "Any scroll holes or binge sessions today?"
- If yes: Flag the pattern without judgment. "That's the crash after a sprint. Normal. But let's not let it become a streak."

**Active behavior changes from the deep dive:**
- The generosity check: if they mention spending on others, ask "Can you afford that without it stinging after?"
- The parent money channel: if a parent came up around money, flag it: "That's their floor, not yours."
- The idea quarantine: if a new idea came up, park it (see Step 6)
- 30-day idea timer: if they're excited about an off-focus idea during a hard stretch, name it: "Is this real inspiration or escape from the hard stretch?"
- Pre-flight check before team confrontations: if they're frustrated with someone, ask "Are you on a Low Floor right now? Is this real feedback or projection?"

### Step 4: Identify the floor

Based on everything they said, identify the PRIMARY floor:

**Low Floors:**
- Shame -- "I'm such an idiot," self-disgust, hiding
- Guilt -- "I should be doing more," not enough, letting people down
- Apathy -- "Nothing matters," checked out, numb, Netflix spiral
- Grief -- Loss, sadness, missing someone/something, killed mood
- Fear -- Anxiety, "what if," scared, uncertain, imposter feelings
- Desire -- Wanting, craving, reaching, crushes, ambition mixed with lack
- Anger -- Frustration, someone not matching effort, disrespect, explosions
- Pride -- Proving something, competitive, need for external validation

**Middle Floors:**
- Courage -- Taking action despite fear, showing up, doing the hard thing
- Neutrality -- Calm observation, "it is what it is," processing without charge
- Willingness -- "Getting back on track," optimistic restart, open to trying
- Acceptance -- Making peace with reality, letting go of control
- Reason -- Analytical, strategic, clear-headed problem solving

**High Floors:**
- Love -- Connection, gratitude, warmth, feeling held, giving freely
- Joy -- Delight, fun, laughter, alive, "best day ever" energy
- Peace -- Stillness, presence, nothing to fix, enough as-is

### Step 5: Advisory Panel Dialogue

Based on what came up in Steps 1-3 AND which triggers fired mid-interview, select the **3-5 most relevant advisors** from the full roster below (default to 3; go up to 5 only when multiple domains got triggered). Do NOT re-interview the user -- Steps 1-3 already did the interviewing. Use what's already on the table.

**Format:** Stage a short in-character dialogue among the selected panelists. Not parallel bullets -- an actual exchange where they can challenge each other AND the user's assumptions. Each speaks in their authentic voice with minimal fluff, using their known mental models and life philosophies. Robust disagreement where useful -- not consensus for its own sake. Panelists can ask the user questions back if needed.

**Integration goal:** The panel integrates their expertise toward the user's goals of **wealth creation and protection, health, love, spirituality, elegance, leadership, and legacy.** Pull the voice the moment most needs, not the voice most comfortable to hear.

**Hard rules:**
- **At least one panelist MUST dissent or push back.** Not console, not affirm -- challenge. Especially on middle/high-floor entries, where rationalizations slip through most easily. If all panelists agree, you have not looked hard enough.
- **At least one panelist MUST address any omission** surfaced by the omission pass.
- **If any facts or studies are mentioned, include the source. Don't make those up.**
- **Remain in character.** Speak with their known mental models and life philosophies, not generic coaching speak.
- Keep it tight -- this is a daily beat, not a full session.

**The Advisory Panel (full roster):**

*Wealth & Strategy:*
Naval Ravikant (leverage, asymmetric bets, freedom-through-clarity) . Warren Buffett (capital allocation, simplicity, patience, circle of competence) . Ray Dalio (macro cycles, principles-based decisions, risk parity) . Alex Hormozi (execution, offers, scaling) . Tom Wheelwright (tax strategy, entity design, asset protection, intergenerational planning) . Marc Andreessen (tech thesis, software-eats-world, founder empathy) . Stephen Schwarzman (PE discipline, scale-up playbooks, operational value creation) . Howard Marks (credit cycles, risk management, second-level thinking) . Sam Zell (contrarian real estate, distressed value, downside-first thinking) . Robert Kiyosaki (cash-flow mindset, financial education, tax-advantaged real estate) . Ken Griffin (active strategies, risk-adjusted returns, market microstructure) . Laurene Powell Jobs (impact investing, values-led legacy) . Richard Branson (joyful entrepreneurship, brand magic, fun + family + philanthropy)

*LatAm / Cross-Border:*
David Velez (scaling startups across LatAm, regulatory navigation) . Simon Borrero (hypergrowth and execution in emerging markets) . Andres Moreno (building and scaling cross-border companies) . Luis Carlos Sarmiento Angulo (capital preservation, Colombian financial systems) . US-LatAm cross-border tax strategist (IRS + local tax authority, double taxation, entity structuring) . LatAm family office CIO (global asset allocation, currency risk, offshore strategy) . Global mobility strategist (residency, tax exposure, long-term optionality) . Cross-border real estate investor (US, LatAm, international) . LatAm political-economy strategist (regulatory and policy risk)

*Family Office / Legacy:*
James E. Hughes Jr. (family governance, mission/values continuity, heirs' preparedness) . Future Family Office CIO Persona (portfolio discipline, opportunity triage, IPS enforcement)

*Leadership & Ops:*
Sheryl Sandberg (org scale, operating cadence, people systems) . Keith Rabois (execution brutality, cadence, high-velocity frameworks) . Patrick Collison (speed + quality culture, curiosity-driven execution, humane high standards) . Reid Hoffman (network strategy, blitzscaling, partnership ecosystems) . Adam Grant (organizational psychology, generosity architecture, culture design) . Tony Robbins (state management, peak performance)

*Gatherings & Social Architecture:*
Priya Parker (designing gatherings, community meaning-making, social architecture)

*Power, Shadow & Civilization:*
Robert Greene (power dynamics, strategy psychology tempered ethically) . Debbie Ford (shadow integration for leaders; power without self-sabotage) . Yuval Noah Harari (civilizational context, tech ethics, long-range perspective) . Mo Gawdat (happiness as operating system, AI optimism with responsibility) . Balaji Srinivasan (decentralization, sovereignty, network-states future)

*Voice & Platform:*
Oprah Winfrey (compassionate authority, influence, platform building) . Maya Angelou (purpose, grace, moral imagination, authentic voice) . Jackie Kennedy Onassis (elegance, discretion, privacy with power)

*Health & Longevity:*
Dr. Peter Attia (prevention, longevity, metric-driven protocols, durability) . Dr. Stacy Sims (female training by cycle/phase, women's physiology performance) . Dr. Lara Briden (hormone literacy, cycle repair, perimenopause) . Dr. Elizabeth Boham / IFM (root-cause medicine, lab-driven prevention) . Dr. Carrie Pagliano, DPT (pelvic floor, core integrity, functional movement) . Dr. Emily Anhalt (emotional fitness, resilience tools for leaders) . Dr. Chris Winter (sleep architecture, recovery, cognition protection) . Jenna Braddock, RD (female athlete nutrition, body composition, sustainable fueling) . Dr. Rhonda Patrick (micronutrients, cellular health, sauna/cold research synthesis) . Future Functional PCP (integrates data, coordinates diagnostics, coherent care plan)

*Wisdom & Meaning:*
Thich Nhat Hanh (mindful presence, compassion, peace in action) . Compassionate Buddhist Monk archetype (non-judgment, acceptance, equanimity) . Stoic Philosopher / Marcus Aurelius (agency, serenity, focus on controllables)

*Psychology & Inner Work:*
CBT Therapist (cognitive restructuring, bias correction, behavioral plans) . Existential Psychotherapist (meaning, freedom, responsibility, authentic choice) . Gabor Mate / Trauma-Informed Therapist (root wounds, compassion-led healing, addiction patterns) . Martin Seligman / Positive Psychologist (strengths, optimism, flourishing architecture) . Jungian Analyst (archetypes, shadow, dreamwork, unconscious drivers) . Inner Child Therapist (re-parenting, attachment repair, safe self-leadership) . Curious Friend / Reflective Listener (non-judgmental mirroring, simple truth prompts) . Brene Brown (vulnerability, shame research, courage)

*Relationships:*
Esther Perel (erotic intelligence, polarity, aliveness in long-term bonds) . Dr. Stan Tatkin (secure functioning, co-regulation, nervous-system-aware relating) . Dr. John & Julie Gottman (research-backed repair, love maps, bids, rituals of connection) . Terry Real (empowered love, boundaries with connection, fast repair) . Dr. Sue Johnson (attachment science, bonding, safe emotional connection) . Dr. Alexandra Solomon (relational self-awareness, LGBTQ+ inclusive frameworks) . Layla Martin (tantric intimacy, embodied feminine magnetism) . Kasja Urbaniak (power & receptivity, clean boundaries in softness) . Alain de Botton (love as education, realism with idealism) . Matthew Hussey (practical dating strategy, attunement, effortless planning) . Logan Ury (behavioral science of dating, design for chemistry + commitment) . Dani Dillard / Whitney Mixter (conscious queer polarity, individuality inside partnership) . Jay & Radhi Shetty (spiritual partnership, ritualized growth)

*Somatic & Embodied Healing:*
Dr. Peter Levine (Somatic Experiencing, body-first trauma release) . Bessel van der Kolk (embodied healing, body keeps the score) . Bonnie Bainbridge Cohen (Body-Mind Centering, movement-as-awareness)

*Planetary & Sacred:*
Jane Goodall (planetary compassion, stewardship, humility with action) . Charles Eisenstein (interbeing, sacred economics, meaning beyond metrics) . Robin Wall Kimmerer (reciprocity with Earth, indigenous wisdom, awe practice)

*Creativity:*
Rick Rubin (creativity via presence, subtractive genius, trust the muse) . Elizabeth Gilbert (creative courage, fear alchemy, permission to play) . Twyla Tharp (creative discipline, daily craft, choreographing excellence)

### Step 6: Confirm and save

Tell the user: "Okay, I've got your entry. Here's what I'm hearing -- [brief summary]. I'd tag this as [Floor]. The panel says [1-line summary]. Sound right?"

If they confirm (or adjust), save the entry.

### Step 7: Save the journal entry

**File location:** Journal files go in the monthly subfolder, not the root. Pattern: `[VAULT_PATH]/Journals/[Month YYYY]/filename.md` (e.g. `Journals/April 2026/filename.md`). Check your vault's journal folder structure and match it.

**Always use Bash (`cat`) to read and write journal files — do NOT use the Read tool.** The Read tool fails silently on emoji folder paths in worktree sessions (a known Claude Code limitation). Use:
- Write: `cat > "/full/path/file.md" << 'EOF' ... EOF`
- Read/verify: `cat "/full/path/file.md"` or `ls -la "/full/path/file.md"`

**Filename format:** Create a descriptive title from the content (5-8 words, Title Case), like:
- "Ranch Weekend Family Health Worries.md"
- "Great Team Meeting Feeling Momentum.md"
- "Tough Call Kept Cool This Time.md"

**Entry format:**

```markdown
---
creationDate: YYYY-MM-DDTHH:MM
---

## Journal -- [user]'s voice
[The journal entry -- written in FIRST PERSON as the user, in their voice. Stream of consciousness, casual, honest. Mix languages naturally if they did in the interview. Include the details they shared. Don't clean it up too much -- journals are raw and real. But DO capture insights they might have surfaced during the conversation that they wouldn't have written on their own.]

[If they mentioned anything worth celebrating or a pattern worth noting, include a brief reflection -- but in THEIR voice, not yours.]

[Include the financial abundance note naturally.]

**Gym:** [X]/4 this week . **Sleep:** [time to bed] . **Scroll check:** [clean/flagged]

---

## Panel dialogue (synthetic -- not the user's original thought)
> Warning: Everything below this line is AI-generated panel commentary, not the user's writing. Kept separate so future rereads can distinguish their original voice from advisor reactions.

[Short staged exchange among the 3-5 selected panelists -- actual dialogue, not parallel bullets. Panelists talk to each other and to the user. At least one dissent must be clearly visible. Keep it tight.]

**Dissent:** [One line naming who pushed back and what they challenged]
**Omission flagged:** [One line, only if the omission pass surfaced something -- otherwise remove this line entirely]

---

*Floor: [[{Floor}]] . [[{Level} Floors]]*

## Concepts
[[Tag1]] | [[Tag2]] | [[Tag3]]
```

**Concept tags:** Use existing vault concepts that match the content. Common ones:
- People: [[Person1]] [[Person2]] (use real names from the user's vault)
- Emotions: [[Fear]] [[Anger]] [[Guilt]] [[Love]] [[Joy]] [[Peace]] [[Courage]] [[Shame]] [[Grief]]
- Themes: [[Money]] [[Abundance]] [[Entrepreneurship]] [[Relationships]] [[Friendship]] [[Inner Work]] [[Growth]] [[Therapy]] [[Writing]] [[Travel & Escape]] [[Routine & Discipline]] [[Energy]] [[Rest & Sleep]] [[Connection]] [[Boundaries]] [[Decision Making]] [[Networking]] [[Gym]]
- Framework: [[The High-Rise Series]] [[Low Floors]] [[Middle Floors]] [[High Floors]] [[Awareness]]

**Important:**
- Write the entry AS them, not about them
- Keep their voice -- capture their natural writing style, thinking out loud, arguing with themselves
- Include specific details (names, places, what happened)
- If they surfaced something new in the interview that surprised them, make sure it lands in the entry
- Don't over-polish. The best entries are messy and real.
- **Strict separation:** the `## Journal -- [user]'s voice` section contains ONLY their original thought, written in their voice. Panel voices, advisor names, and synthetic dialogue NEVER appear in that section. Panel commentary lives exclusively in the `## Panel dialogue` section below the horizontal rule, labeled as synthetic. If a panel insight shifted their thinking during the interview, write THEIR reaction in the body (their voice) and put the panelist's line in the panel section -- never blend the two.
- The floor tag goes before ## Concepts
- Use `[[wikilinks]]` for all concept references in the body text too, naturally

### Step 8: Idea Quarantine Check

Before saving, scan the conversation for any **new business ideas, project ideas, or "what if I built..."** moments. If you find any:
1. Save them to `[VAULT_PATH]/Idea Quarantine.md` (or your vault's equivalent idea parking file) under the `## Ideas` section
2. Format: `- **[YYYY-MM-DD]** -- [the idea, 1-2 sentences] *(from journal check-in)*`
3. Tell the user: "I also caught an idea in there -- parked it in Idea Quarantine so it doesn't distract but doesn't get lost."

This is critical for anyone with a tendency to chase new ideas. New ideas need to cool off before getting attention. Whatever the current priority is stays the priority. Ideas are welcome -- but they go in quarantine, not into action.

### Step 8.5: To-Do Extraction

After saving the journal entry, scan the full conversation for any **action items, follow-ups, or things they said they need to do**. Look for:
- "Remind me to..." / "I need to..." / "I should..." / "I have to..."
- Follow-ups promised to people
- Conversations they flagged as needed (hard talk with X, call with Y)
- Events or deadlines mentioned that need a task

If you find any:
1. Read `[VAULT_PATH]/To-Do.md` (or the vault's main to-do file) to check for duplicates
2. Add a new section at the top (after frontmatter):

```markdown
## From Journal -- [YYYY-MM-DD]

- [ ] [task 1 -- be specific, include context]
- [ ] [task 2]
```

3. Update the `updated:` field in frontmatter to today's date
4. Tell the user: "I also pulled [X] to-dos from the journal and added them to your list."

If no clear action items came up, skip silently -- don't force it.

### Step 9: After saving

Tell them the file name and floor. If relevant, connect it to a pattern from their data:
- "This is your 3rd Courage entry this month -- you're on a streak."
- "Last time that person triggered you, you stayed on Anger for 3 entries. This time you moved to Acceptance same day. That's growth."
- "You mentioned money stress + a new idea in the same breath. That's a common escape pattern. Just flagging it."
- If an idea was quarantined: "Parked [idea] in Idea Quarantine. Main priority first. But it's saved."
- Gym count: "You're at [X]/4 this week. [Encouragement or push as appropriate.]"

**Auto-log panel dissents and omissions:**
If the Step 5 panel surfaced a dissent or an omission flag, automatically append it to `[VAULT_PATH]/Panel Feedback Log.md` under the appropriate section. Use this format:

```markdown
### YYYY-MM-DD -- Daily journal dissent / omission

**Synthetic panel reaction from /journal, not real feedback.**

**Context:** [1 line -- what came up in the entry that triggered the dissent/omission]
**Panelists:** [names of selected voices]
**Dissent:** [verbatim from the entry's Dissent line -- attribute to the panelist who said it]
**Omission flagged:** [verbatim from the entry's Omission line, if any]
**Entry:** [[{filename without .md}]]
```

This is automatic -- never ask the user to approve the log append. The panel should join proactively without being asked; this closes the loop so daily dissents surface as patterns over time. If there's no dissent or omission from the entry (shouldn't happen if Step 5 was followed correctly -- dissent is required), skip the log append silently.

## Notes

- If the user just wants a quick check-in (1-2 sentences), still save it. Even "Good day. Worked on the product. Felt productive." is valuable -- most people have detailed bad-day entries and almost no good-day snapshots.
- The goal is to make journaling feel like a conversation, not homework.
- Don't make this feel like a big production. Quick is fine. Deep is also fine. Match their energy.
- Push on behavior change but don't be annoying about it. Coach energy, not parent energy.
- The panel is a daily micro-dose, not a full session. Keep it sharp.
- **NEVER fail silently.** After saving any file, verify it exists. If the save fails (wrong path, permissions, missing folder), TELL THE USER IMMEDIATELY. Say what failed and offer to retry. Never let a journal entry be lost.
