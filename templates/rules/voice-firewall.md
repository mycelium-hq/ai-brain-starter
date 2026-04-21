---
type: rules
tags: [voice, quality-control, outreach, writing]
---

# Voice firewall

Run every check before any outreach or public writing leaves the vault. Binary pass/fail. One failure = rewrite before sending.

These rules catch AI-flavored prose and template thinking. They're about *removing* signals that make writing read as generated or generic, not about enforcing a personal voice.

---

**Rule 1: No em dashes**
Check: Does the copy contain any `--` or `—` character?
Reason: Known AI writing signal. Strong tell across all outreach surfaces.
Fix: Replace with comma, colon, period, or parentheses.

---

**Rule 2: No exclamation marks**
Check: Does the copy contain `!`?
Reason: Flattens warmth into performance. Reads as LinkedIn-influencer tone.
Fix: Remove entirely. Carry energy through word choice.
Exception: Permitted only inside directly quoted third-party dialogue that originally used one.

---

**Rule 3: No "I hope this finds you well"**
Check: Does the opener contain any variant of "hope this finds you" or "hope you're well"?
Reason: Most-filtered opener in B2B email. Signals nothing to say.
Fix: Open with a specific observation, proof point, or shared context.

---

**Rule 4: No "I wanted to reach out because"**
Check: Does the copy contain "I wanted to reach out" or "I'm reaching out because"?
Reason: Passive hedging, buries value in sentence two.
Fix: Start with the value, observation, or ask directly.

---

**Rule 5: No banned corporate vocabulary**
Check: Does the copy use any of: "synergies," "leverage" (verb), "circle back," "at the end of the day," "take this offline," "move the needle"?
Reason: Template thinking signals. Erode trust with sophisticated readers.
Fix: Plain-language equivalent. "Use" not "leverage." "Talk later" not "circle back."

---

**Rule 6: No duplicate H1 heading after frontmatter**
Check: Does the file begin with `# ` immediately after the frontmatter block?
Reason: In Obsidian, filename is the title. `# Title` after frontmatter creates duplicate H1 and breaks graph rendering.
Fix: Delete the `# Title` line. Start with body content or a `##` section heading.

---

**Rule 7: No bare wikilink without checking canonical form first**
Check: Does the file contain a `[[Link]]` that may resolve to a non-canonical or ambiguous node in the vault?
Reason: Bare wikilinks to common terms can resolve to the wrong note, create false graph edges, break backlink accuracy.
Fix: Check vault for canonical filename before writing the wikilink. Add an alias in frontmatter if needed.

---

## Extending this file

This is the generic base. Add project-specific rules below (e.g., "never misattribute X award," "never frame our product as cheaper than Y"). Keep them numbered and test each against actual drafts before shipping.
