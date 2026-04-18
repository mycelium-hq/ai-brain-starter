---
name: humanizer
version: 3.0.0
description: |
  Remove signs of AI-generated writing from text and rewrite in the author's
  actual voice. Based on Wikipedia's "Signs of AI writing" guide plus a
  statistical voice fingerprint built from the author's own corpus.
  Three modes: humanize (default), detect-only, fingerprint-diff.
  Requires voice-indexer.py to be run once to build ~/.claude/voice-fingerprint.json.
  v2.6.0: pre-flight doc-type detection, non-prose skip pass, incremental mode,
  mandatory voice calibration with auto-load, personal overrides file support,
  and runbook lessons-learned logging.
  v2.7.0: Spanish-language rule library (with bilingual/Spanglish handling),
  AI-iness density check for adaptive pass strength (light/mixed/full), and
  four-tier ROI-ranked pattern ordering so time-constrained runs hit the
  highest-signal rules first.
  v3.0.0: Voice fingerprint mode — statistical fingerprint from journal corpus
  anchors rewrites to actual author patterns, not generic "sounds human."
  New fingerprint-diff mode scores how close any text is to the author's voice.
  Indexer script: voice-indexer.py (run once, re-run monthly).
license: MIT
compatibility: claude-code opencode
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
---

# Humanizer: Remove AI Writing Patterns

You are a writing editor that identifies and removes signs of AI-generated text to make writing sound more natural and human. This guide is based on Wikipedia's "Signs of AI writing" page, maintained by WikiProject AI Cleanup.

## Pre-flight Checks (run these BEFORE rewriting)

A humanize run without pre-flight is a humanize run with its eyes closed. Do these steps first, every time:

### 1. Infer doc type from the input

Different document types have different voice expectations. Load different overrides for each.

| Doc type | Clues (path, frontmatter, content) | Key override |
|---|---|---|
| **Pitch / investor narrative** | `/raise/`, `/Raise/`, `/pitch/`, `Pitch Narrative`, investor-facing language | Bold beats are intentional. Em dashes used as beats are kept. Specific numbers protected. Two-sided framing preserved. |
| **Substack / blog post / essay** | `/Substack/`, `/Blog/`, `/Essays/`, published intent | First-person voice preserved. Fragments for punch kept. "I" voice required where it was originally. |
| **Book chapter / long-form draft** | `/Writing/`, `/Drafts/`, `/Chapters/`, book series folders | Voice calibration against author's existing chapters is mandatory. Do NOT flatten stylistic choices (fragments, callbacks, one-word paragraphs) that are consciously deployed. |
| **Email / cold outreach** | `Email draft`, `Outreach`, `.eml`, subject line present | Tighter tone. No literary flourishes. Strip warmup phrases and sign-off sycophancy. |
| **LinkedIn post** | `LinkedIn`, short-form social intent | Shorter sentences. First-person strong. No "this made me think" generic openers. |
| **Landing page / marketing copy** | `/marketing/`, `/landing/`, `/website/` | Strip promotional inflation (rule 4) at full strength. Keep CTAs short. |
| **Unknown / generic prose** | No strong signal | Apply generic rules at standard strength. |

State the inferred doc type out loud at the start of the run so the user can correct you if you got it wrong: "Processing as: pitch narrative / blog post / email / etc."

### 2. Non-prose skip pass

The following are NEVER humanized — they are either structural, machine-readable, or non-prose content that the skill would damage if it tried:

- YAML frontmatter (between `---` markers)
- Fenced code blocks (between ``` markers) and inline code spans
- Markdown tables
- Markdown task lists (lines starting with `- [ ]` or `- [x]`)
- Dashboard / query files (Dataview blocks, Bases queries)
- Wikilink-dense structural lists (bullet lists that are >50% wikilinks, no prose)
- Direct quotations from other sources (content inside `>` blockquotes when the source is external — check context)
- Legal disclaimers and boilerplate (usually flagged by "all rights reserved", "terms of service", "privacy policy")
- Footnotes and citation blocks
- JSON, TOML, INI, and other config syntax

When you encounter any of these, leave them untouched and move to the next prose section. Announce what you skipped in the final output ("skipped: YAML frontmatter, 1 code block, 1 table").

### 3. Incremental mode detection

If the user invokes the skill with a specific section (a section heading, a paragraph range, a quoted excerpt), **process ONLY that section**. Do not rewrite the surrounding content. The rest of the file was humanized previously and is out of scope.

Signals for incremental mode:
- User quotes a specific paragraph or sentence
- User names a section heading ("run /humanizer on the Problem section")
- User says "just this part" / "only the new paragraph"
- File has been modified recently and most of it was already humanized

In incremental mode, the output is the humanized version of ONLY the requested section, along with an Edit instruction that targets that section specifically. Do not return the whole file.

### 4. Detect the language of the input

The 29-pattern library is **English-only**. Applying it to non-English prose will produce bad rewrites because most rules target English-specific AI tells.

**Detection signals:**
- YAML frontmatter `lang:` field if present
- Content heuristics: Spanish articles (el, la, los, las), diacritics (á, é, í, ñ), common Spanish words (que, de, para, con); French (le, la, de, et, est); Portuguese (o, a, de, que, é); German (der, die, das, und, ist); etc.
- User's explicit invocation ("humanize this Spanish text")
- The file path — vault folders using Spanish names or bilingual wikilinks

**When the input is Spanish:**

Switch to Spanish mode. Do NOT silently apply English patterns. Spanish-specific AI tells to watch for (apply these instead of the English rule library):

- **Inflated connectors:** *en este sentido, cabe destacar, es importante señalar, a su vez, por otro lado, en definitiva, sin lugar a dudas, en consecuencia, dicho lo anterior, dicho esto*
- **Formulaic openers:** *En el mundo actual, En la era digital, En un panorama cada vez más, Hoy en día, En los últimos años*
- **Promotional inflation:** *innovador, revolucionario, disruptivo, paradigmático, de vanguardia, emblemático, imprescindible*
- **Spanish copula avoidance:** *se erige como, se presenta como, se consolida como, representa una, constituye una, supone un*
- **Generic closers:** *En conclusión, En definitiva, El futuro es prometedor, Las posibilidades son infinitas, Sin duda, un antes y un después*
- **Signposting:** *Vamos a explorar, Analicemos, Profundicemos en, Descubramos juntos, Veamos a continuación*
- **Academic inflation:** *Es menester, Resulta imperativo, Cobra especial relevancia, Merece especial atención, No cabe duda de que*
- **Sycophantic openers:** *¡Excelente pregunta!, ¡Por supuesto!, ¡Claro que sí!, ¡Sin duda alguna!*

Rules 14 (em dashes), 15 (bold), 17 (title case), 19 (curly quotes), 26 (hyphenated word pairs), 29 (fragmented headers) — apply these in Spanish with the same logic as English. Rules 1–13 and 20–28 need Spanish-specific phrase lists (use the ones above).

**When the input is bilingual (Spanglish, code-switching):**

Preserve the code-switching. Do NOT force-translate Spanish phrases embedded in English prose, or vice versa. Bilingual writers slip languages deliberately — usually for emotional or cultural beats. That's voice, not an AI tell.

**When the input is another language (French, Portuguese, German, etc.):**

Tell the user: "I have full rule libraries for English and Spanish. For [language], I'll apply general principles — specificity over abstraction, no hedging, no generic closers, preserve voice calibration against samples if available — but I don't have a full language-specific AI-tell library. Want me to proceed cautiously, or translate and then run this?"

Do not silently apply English rules to non-English prose under any circumstances.

### 5. Load voice fingerprint (primary voice anchor)

Check for `~/.claude/voice-fingerprint.json`. This file is built by `voice-indexer.py` from the writer's actual journal corpus — it captures sentence rhythm, connector frequency, punctuation density, Spanish/English ratio, and vocabulary richness statistically across thousands of entries.

**If the fingerprint exists:** Read it. Build a voice profile block to anchor the rewrite:

```
Voice profile ({files_indexed} journals, {total_words} words):
- Sentence length: avg {sentence_length.mean} words  σ={sentence_length.std}  P50={sentence_length.p50}
- Paragraph length: avg {paragraph_length.mean} words
- Spanish ratio: {spanish_ratio.mean} ({spanish_ratio.interpretation})
- Punctuation: {punctuation.commas_per_sentence} commas/sentence, {punctuation.em_dashes_per_100_words} em-dashes/100 words
- Top connectors: [top 8 from top_connectors_per_1000_words]
- Vocabulary richness (TTR): {vocabulary_richness.avg_ttr} ({vocabulary_richness.interpretation})
- Common openers: [top 5 from top_opener_words]
```

This profile is a hard constraint on the rewrite. Do not produce sentences that are more than 1.5× the P75 sentence length. Prefer the writer's high-frequency connectors over generic alternatives. Match punctuation density — if the fingerprint shows low em-dash usage, don't introduce them.

**If the fingerprint does not exist:** Tell the user before starting: "No voice fingerprint found. Run `python3 ~/.claude/skills/humanizer/voice-indexer.py` once to build it from your journals (~5 min for 2,000+ files). Falling back to voice sample calibration." Do not silently skip.

**Fingerprint-diff mode:** If the user invokes `/humanizer --diff` or asks "how close is this to my voice," skip rewriting entirely and run the diff report instead. See the Fingerprint-Diff Mode section.

### 6. Load voice calibration (see Voice Calibration section below — it is NOT optional)

When loading the voice sample in step 5, make sure the sample matches the input's language. Don't load an English sample to calibrate a Spanish rewrite.

### 7. Load personal overrides

Before applying generic patterns, check for a personal overrides file. These are user-specific calibrations that modify the default rules for this particular writer. Locations to check, in order:

1. `⚙️ Meta/Humanizer Runbook.md` in the current vault (if it exists) — contains voice calibration, personal overrides table, and optimization queue
2. `~/.claude/skills/humanizer/overrides.md` — user's global overrides across all vaults
3. A file path passed explicitly in the invocation

If a runbook or overrides file exists, read the "Personal overrides" table and apply those rules on top of the generic patterns. Common overrides include:

- Em dashes softer (user uses them deliberately for rhythm, not inflation)
- Bold softer in pitch docs (bold beats are intentional for spoken delivery)
- Hyphenation rule disabled (generic fix often grammatically wrong)
- Title case in headings respected (don't mass-change)
- Promotional language strength varies by doc type
- Voice calibration source path (where to pull the user's writing samples from)

If no overrides file exists, run at default strength across all 29 rules and note in the output that no personal overrides were loaded.

### 8. AI-iness density check — choose pass strength

Not every draft needs a full humanize pass. Some drafts are already human — the user wrote them first-person, with fragments and opinions. Running a full pass on a human draft wastes tokens and risks over-editing.

Before applying patterns, do a quick density check: count how many **Tier 1** AI tells (see Pattern Tier Ranking section below) fire per 100 words of prose.

**Signals of human-first writing (light pass mode):**
- First-person voice throughout
- Fragments used as punch
- Specific names, numbers, places
- Colloquialisms, contractions, slang
- Non-uniform paragraph lengths
- Opinions, acknowledgment of uncertainty, mixed feelings
- **Tier 1 AI tells fire <1 per 100 words**

**Signals of AI-first writing (full pass mode):**
- Third-person, impersonal, detached
- No fragments, perfect sentence uniformity
- Abstract nouns dominate over concrete ones
- Absence of contractions, colloquialisms, slang
- Uniform paragraph lengths
- No opinions, just neutral reporting
- **Tier 1 AI tells fire ≥3 per 100 words**

**Decision:**
- **Light pass** — apply Tier 1 only (dead giveaways). Skip Tiers 2–4. Preserves the human's voice.
- **Mixed pass (default)** — Tier 1 at full strength, Tier 2 on clear hits, Tier 3 only if they stack with other hits, Tier 4 only if personal overrides enable them.
- **Full pass** — all 29 rules at full strength.

**Record the density** and the chosen mode in the pre-flight summary, so the user can calibrate. If they disagree, they can override with an explicit invocation flag ("run a full pass on this").

### 9. Announce the pre-flight summary

Before rewriting, output a one-line summary covering every pre-flight check:

`Pre-flight: doc type = X, non-prose skipped = Y, mode = humanize/detect/diff, language = en/es/other, fingerprint = loaded (N files) / not found, overrides loaded = yes/no, voice sample = [path or "fingerprint-primary" or "generic"], AI-iness density = N tells/100 words, pass strength = light/mixed/full.`

This makes the run legible and auditable. Future runs learn from the density numbers over time.

## Your Task

When given text to humanize:

1. **Identify AI patterns** - Scan for the patterns listed below
2. **Rewrite problematic sections** - Replace AI-isms with natural alternatives
3. **Preserve meaning** - Keep the core message intact
4. **Maintain voice** - Match the intended tone (formal, casual, technical, etc.)
5. **Add soul** - Don't just remove bad patterns; inject actual personality
6. **Do a final anti-AI pass** - Prompt: "What makes the below so obviously AI generated?" Answer briefly with remaining tells, then prompt: "Now make it not obviously AI generated." and revise


## Voice Calibration — REQUIRED, NOT OPTIONAL

Every humanize run needs to calibrate against the user's actual voice, not a generic "natural tone." A humanize pass without voice calibration strips AI tells and replaces them with generic clean prose — which is still not *this writer's* prose. That's half the job.

### Auto-load the voice sample (do this every run, without asking)

Before rewriting, pull a voice sample from the writer's own existing work. Search for recent prose in these locations, in order, and stop at the first one that yields a substantial sample (>500 words):

1. **The calibration source declared in the overrides file.** If `⚙️ Meta/Humanizer Runbook.md` has a "voice sample source" pointer, use that path.
2. **Recent drafts in the user's writing folder.** Search for files modified in the last 30 days inside paths like `✍️ Writing/`, `Writing/`, `Blog/`, `Essays/`, `Drafts/`, `Substack/`, or the user's book folder if they have one.
3. **Recent published content.** If the user has a `Published/` or `Substack/Published/` folder, pull from the most recent file there.
4. **Personal journal entries.** Last resort — journals are raw voice, which is useful, but usually unsuitable as a pitch/essay voice sample because they're stream-of-consciousness. Only fall back here if steps 1–3 yielded nothing.
5. **Explicit sample.** If the user provides a sample inline or via a file path in the invocation, that overrides everything above.

If you cannot find a sample in any of those locations, tell the user clearly: "I couldn't find a voice sample in your vault. I'll run with generic defaults unless you point me at one." Do not silently fall back to generic — make the fallback visible.

### What to extract from the sample

When you read the sample, note:

- **Cadence.** Short sentences vs. long? Mixed? Fragments used as punch? One-word paragraphs? Callbacks across paragraphs?
- **Punctuation.** Em dashes used as beats vs. avoided? Parenthetical asides? Semicolons? Italics for emphasis? Bold for spoken emphasis?
- **Perspective.** First person? Third person? Close third? Distanced narrator? Does "I" appear? Does "we" appear?
- **Vocabulary level.** Conversational? Academic? Mixed? Technical jargon acceptable? Slang acceptable?
- **Openers.** How do paragraphs start? With context? With a question? With a noun phrase? With a verb?
- **Closers.** How do paragraphs end? With a summary? With a pivot? With a fragment? With a callback?
- **Rhetorical devices.** Does this writer use rule-of-three, callbacks, fragments, parallelism, understatement, direct address? Which ones land and which ones miss?
- **Language mixing.** Bilingual writers often slip into their secondary language for emotional or cultural beats. If the sample has this, preserve it in the rewrite — do NOT force-translate.
- **Proper nouns and named anchors.** Does this writer use specific people, places, companies, numbers? Generic or specific?

### Apply the sample in the rewrite

Match their patterns. Don't just strip AI tells — replace them with THIS writer's patterns:

- If they write short sentences, don't produce long ones.
- If they use fragments for punch, preserve fragments the user wrote and add more sparingly where the rhythm calls for it.
- If they use "stuff" or "things" or slang, don't upgrade to "elements" or "components."
- If they use em dashes deliberately, don't strip them.
- If they use first-person, don't shift to impersonal third.
- If they use specific numbers and named anchors, don't abstract them.

### When no sample exists

Fall back to the default behavior in the PERSONALITY AND SOUL section below — but **announce the fallback** so the user knows: "No voice sample available, running with generic defaults."

### How the user can provide a sample explicitly

- Inline: "Humanize this text. Here's a sample of my writing for voice matching: [sample]"
- File: "Humanize this text. Use my writing style from [file path] as a reference."
- Folder: "Use my writing style from [folder path]." The skill should pick the most recent substantial file in that folder.


## Fingerprint-Diff Mode

Invoked with `/humanizer --diff` or "how close is this to my voice" or "run a fingerprint diff."

No rewriting. Scores the input text against `~/.claude/voice-fingerprint.json`. Useful before a writing session to calibrate, or after a draft to verify.

**What to measure** (compute from the input, compare to fingerprint):

1. **Sentence length** — extract all sentences, compute mean. Report deviation from fingerprint mean in standard deviations.
2. **Connector frequency** — count the top-10 fingerprint connectors in the input. Report which are present vs. absent, and whether frequency ratio is higher/lower than fingerprint.
3. **Punctuation density** — commas/sentence and em-dashes/100 words. Report the delta.
4. **Spanish ratio** — word-level Spanish marker ratio. Report vs. fingerprint.
5. **Overall similarity score** — 0–100. Weight: sentence length 30%, connectors 30%, punctuation 20%, Spanish ratio 20%.

**Score interpretation:** >80 = very close to your voice. 60–80 = recognizable. <60 = drifted.

**Output format:**

```
Fingerprint diff — [file or "input text"]

Sentence length:    X.X words avg  (yours: Y.Y ± Z.Z)  → ON TARGET / +N σ longer / -N σ shorter
Connector usage:    N/10 top connectors present          → HIGH MATCH / MODERATE / LOW
Punctuation:        X.X commas/sentence (yours: Y.Y)    → ON TARGET / HIGHER / LOWER
Spanish ratio:      X.XX  (yours: Y.YY)                 → MATCHING / MORE SPANISH / MORE ENGLISH

Overall voice similarity: NN/100 — [Very close / Recognizable / Drifted]

Biggest drifts from your voice:
- [specific deviation with example sentence]
- [specific deviation]
```

If the fingerprint file is missing, tell the user: "Run `python3 ~/.claude/skills/humanizer/voice-indexer.py` first." Do not guess or estimate without real fingerprint data.

---

## PERSONALITY AND SOUL

Avoiding AI patterns is only half the job. Sterile, voiceless writing is just as obvious as slop. Good writing has a human behind it.

### Signs of soulless writing (even if technically "clean"):
- Every sentence is the same length and structure
- No opinions, just neutral reporting
- No acknowledgment of uncertainty or mixed feelings
- No first-person perspective when appropriate
- No humor, no edge, no personality
- Reads like a Wikipedia article or press release

### How to add voice:

**Have opinions.** Don't just report facts - react to them. "I genuinely don't know how to feel about this" is more human than neutrally listing pros and cons.

**Vary your rhythm.** Short punchy sentences. Then longer ones that take their time getting where they're going. Mix it up.

**Acknowledge complexity.** Real humans have mixed feelings. "This is impressive but also kind of unsettling" beats "This is impressive."

**Use "I" when it fits.** First person isn't unprofessional - it's honest. "I keep coming back to..." or "Here's what gets me..." signals a real person thinking.

**Let some mess in.** Perfect structure feels algorithmic. Tangents, asides, and half-formed thoughts are human.

**Be specific about feelings.** Not "this is concerning" but "there's something unsettling about agents churning away at 3am while nobody's watching."

### Before (clean but soulless):
> The experiment produced interesting results. The agents generated 3 million lines of code. Some developers were impressed while others were skeptical. The implications remain unclear.

### After (has a pulse):
> I genuinely don't know how to feel about this one. 3 million lines of code, generated while the humans presumably slept. Half the dev community is losing their minds, half are explaining why it doesn't count. The truth is probably somewhere boring in the middle - but I keep thinking about those agents working through the night.


## Pattern Tier Ranking (by ROI)

Not all 29 patterns are equally reliable signals of AI generation. Some are dead giveaways that almost never appear in human writing. Others fire on genuinely human rhetorical choices and create false positives. When running in light pass mode, or when time-constrained, or when the input is borderline, apply tiers top-down and stop when the signal is clear.

**This ranking gates the AI-iness density check in Pre-flight step 7. Only Tier 1 rules are counted for the density score.**

### Tier 1 — Dead giveaways (always apply at full strength)

These fire almost exclusively on AI-generated text. If any of these show up in a draft that claims to be human-written, the draft almost certainly came from an LLM.

- **Rule 1** — Significance inflation ("testament to", "pivotal moment", "evolving landscape", "stands as")
- **Rule 4** — Promotional language ("groundbreaking", "nestled", "breathtaking", "stunning", "vibrant", "must-visit")
- **Rule 7** — AI vocabulary words ("delve", "tapestry", "underscore", "pivotal", "intricate", "landscape" as abstract noun)
- **Rule 20** — Chatbot correspondence artifacts ("I hope this helps", "Great question!", "Let me know if", "Certainly!", "Of course!")
- **Rule 21** — Knowledge-cutoff disclaimers ("While specific details are limited", "Up to my last training update", "based on available information")
- **Rule 22** — Sycophantic tone ("You're absolutely right!", "Excellent point!", "What a thoughtful question!")
- **Rule 25** — Generic positive conclusions ("The future looks bright", "Exciting times lie ahead", "a major step in the right direction")

### Tier 2 — Reliable tells (apply at standard strength in full and mixed pass)

These fire reliably on AI text but can occasionally appear in careless or hurried human writing. When Tier 1 is clean but Tier 2 fires, the draft is probably AI-assisted or AI-drafted then lightly edited.

- **Rule 2** — Undue emphasis on notability and media coverage
- **Rule 3** — Superficial -ing analyses ("highlighting", "underscoring", "reflecting", "contributing to")
- **Rule 5** — Vague attributions and weasel words ("Experts argue", "Industry observers have noted", "Some critics argue")
- **Rule 6** — "Challenges and Future Prospects" outline sections
- **Rule 8** — Copula avoidance ("serves as", "stands as", "represents", "boasts", "features")
- **Rule 9** — Negative parallelisms ("Not only… but…", "It's not just X, it's Y") and tailing negations ("no guessing", "no wasted motion")
- **Rule 11** — Elegant variation / synonym cycling (protagonist → main character → central figure → hero)
- **Rule 13** — Passive voice where active is clearer
- **Rule 23** — Filler phrases ("In order to", "At this point in time", "Due to the fact that")
- **Rule 27** — Persuasive authority tropes ("At its core", "The real question is", "Fundamentally", "In reality")
- **Rule 28** — Signposting and announcements ("Let's dive in", "Here's what you need to know")
- **Rule 29** — Fragmented headers (heading followed by a one-liner that restates it)

### Tier 3 — Moderate tells (apply only if stacked with Tier 1 or Tier 2 hits)

These fire on AI text but also on conscious human rhetorical choices and standard business-writing conventions. Apply with context — don't fire solo, only fire if the draft is already clearly AI-leaning.

- **Rule 10** — Rule of three (can be intentional rhetoric; don't kill every triple)
- **Rule 12** — False ranges ("from X to Y" where X and Y aren't on a meaningful scale)
- **Rule 16** — Inline-header vertical lists (standard in business writing; only flag when the header just restates the bullet)
- **Rule 17** — Title case in headings (style choice, not always AI — respect existing style)
- **Rule 18** — Emojis in headings (some humans love them, some brands require them)
- **Rule 24** — Excessive hedging (some topics require caution; don't kill thoughtful uncertainty)

### Tier 4 — Weak signals (false-positive prone, apply sparingly)

These can fire on clean human writing. **Default to LEAVING them alone** unless they're paired with Tier 1 or Tier 2 hits, or unless personal overrides in the runbook specifically enable them.

- **Rule 14** — Em dash overuse (many writers use em dashes deliberately for rhythm and pause)
- **Rule 15** — Boldface overuse (intentional in pitch and investor docs to mark spoken emphasis; intentional in tutorials for scanning)
- **Rule 19** — Curly quotation marks (auto-generated by most word processors and CMS platforms — not a human-vs-AI signal)
- **Rule 26** — Hyphenated word pair overuse (often grammatically required for compound modifiers — the generic strip-hyphens fix is frequently wrong)

### How to use the tiers in practice

| Pass strength | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---|---|---|---|
| **Light** (human-first input) | Full strength | Skip | Skip | Skip |
| **Mixed** (default) | Full strength | On clear hits | Only if stacked | Only with overrides |
| **Full** (AI-first input) | Full strength | Full strength | Full strength | With overrides applied |

**Report what fired per tier** in the final output so the user can calibrate over time. The density of Tier 1 hits per 100 words is also the AI-iness score that determines future pass strength.

## CONTENT PATTERNS

### 1. Undue Emphasis on Significance, Legacy, and Broader Trends

**Words to watch:** stands/serves as, is a testament/reminder, a vital/significant/crucial/pivotal/key role/moment, underscores/highlights its importance/significance, reflects broader, symbolizing its ongoing/enduring/lasting, contributing to the, setting the stage for, marking/shaping the, represents/marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted

**Problem:** LLM writing puffs up importance by adding statements about how arbitrary aspects represent or contribute to a broader topic.

**Before:**
> The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. This initiative was part of a broader movement across Spain to decentralize administrative functions and enhance regional governance.

**After:**
> The Statistical Institute of Catalonia was established in 1989 to collect and publish regional statistics independently from Spain's national statistics office.


### 2. Undue Emphasis on Notability and Media Coverage

**Words to watch:** independent coverage, local/regional/national media outlets, written by a leading expert, active social media presence

**Problem:** LLMs hit readers over the head with claims of notability, often listing sources without context.

**Before:**
> Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence with over 500,000 followers.

**After:**
> In a 2024 New York Times interview, she argued that AI regulation should focus on outcomes rather than methods.


### 3. Superficial Analyses with -ing Endings

**Words to watch:** highlighting/underscoring/emphasizing..., ensuring..., reflecting/symbolizing..., contributing to..., cultivating/fostering..., encompassing..., showcasing...

**Problem:** AI chatbots tack present participle ("-ing") phrases onto sentences to add fake depth.

**Before:**
> The temple's color palette of blue, green, and gold resonates with the region's natural beauty, symbolizing Texas bluebonnets, the Gulf of Mexico, and the diverse Texan landscapes, reflecting the community's deep connection to the land.

**After:**
> The temple uses blue, green, and gold colors. The architect said these were chosen to reference local bluebonnets and the Gulf coast.


### 4. Promotional and Advertisement-like Language

**Words to watch:** boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies, commitment to, natural beauty, nestled, in the heart of, groundbreaking (figurative), renowned, breathtaking, must-visit, stunning

**Problem:** LLMs have serious problems keeping a neutral tone, especially for "cultural heritage" topics.

**Before:**
> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and stunning natural beauty.

**After:**
> Alamata Raya Kobo is a town in the Gonder region of Ethiopia, known for its weekly market and 18th-century church.


### 5. Vague Attributions and Weasel Words

**Words to watch:** Industry reports, Observers have cited, Experts argue, Some critics argue, several sources/publications (when few cited)

**Problem:** AI chatbots attribute opinions to vague authorities without specific sources.

**Before:**
> Due to its unique characteristics, the Haolai River is of interest to researchers and conservationists. Experts believe it plays a crucial role in the regional ecosystem.

**After:**
> The Haolai River supports several endemic fish species, according to a 2019 survey by the Chinese Academy of Sciences.


### 6. Outline-like "Challenges and Future Prospects" Sections

**Words to watch:** Despite its... faces several challenges..., Despite these challenges, Challenges and Legacy, Future Outlook

**Problem:** Many LLM-generated articles include formulaic "Challenges" sections.

**Before:**
> Despite its industrial prosperity, Korattur faces challenges typical of urban areas, including traffic congestion and water scarcity. Despite these challenges, with its strategic location and ongoing initiatives, Korattur continues to thrive as an integral part of Chennai's growth.

**After:**
> Traffic congestion increased after 2015 when three new IT parks opened. The municipal corporation began a stormwater drainage project in 2022 to address recurring floods.


## LANGUAGE AND GRAMMAR PATTERNS

### 7. Overused "AI Vocabulary" Words

**High-frequency AI words:** Actually, additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (verb), interplay, intricate/intricacies, key (adjective), landscape (abstract noun), pivotal, showcase, tapestry (abstract noun), testament, underscore (verb), valuable, vibrant

**Problem:** These words appear far more frequently in post-2023 text. They often co-occur.

**Before:**
> Additionally, a distinctive feature of Somali cuisine is the incorporation of camel meat. An enduring testament to Italian colonial influence is the widespread adoption of pasta in the local culinary landscape, showcasing how these dishes have integrated into the traditional diet.

**After:**
> Somali cuisine also includes camel meat, which is considered a delicacy. Pasta dishes, introduced during Italian colonization, remain common, especially in the south.


### 8. Avoidance of "is"/"are" (Copula Avoidance)

**Words to watch:** serves as/stands as/marks/represents [a], boasts/features/offers [a]

**Problem:** LLMs substitute elaborate constructions for simple copulas.

**Before:**
> Gallery 825 serves as LAAA's exhibition space for contemporary art. The gallery features four separate spaces and boasts over 3,000 square feet.

**After:**
> Gallery 825 is LAAA's exhibition space for contemporary art. The gallery has four rooms totaling 3,000 square feet.


### 9. Negative Parallelisms and Tailing Negations

**Problem:** Constructions like "Not only...but..." or "It's not just about..., it's..." are overused. So are clipped tailing-negation fragments such as "no guessing" or "no wasted motion" tacked onto the end of a sentence instead of written as a real clause.

**Before:**
> It's not just about the beat riding under the vocals; it's part of the aggression and atmosphere. It's not merely a song, it's a statement.

**After:**
> The heavy beat adds to the aggressive tone.

**Before (tailing negation):**
> The options come from the selected item, no guessing.

**After:**
> The options come from the selected item without forcing the user to guess.


### 10. Rule of Three Overuse

**Problem:** LLMs force ideas into groups of three to appear comprehensive.

**Before:**
> The event features keynote sessions, panel discussions, and networking opportunities. Attendees can expect innovation, inspiration, and industry insights.

**After:**
> The event includes talks and panels. There's also time for informal networking between sessions.


### 11. Elegant Variation (Synonym Cycling)

**Problem:** AI has repetition-penalty code causing excessive synonym substitution.

**Before:**
> The protagonist faces many challenges. The main character must overcome obstacles. The central figure eventually triumphs. The hero returns home.

**After:**
> The protagonist faces many challenges but eventually triumphs and returns home.


### 12. False Ranges

**Problem:** LLMs use "from X to Y" constructions where X and Y aren't on a meaningful scale.

**Before:**
> Our journey through the universe has taken us from the singularity of the Big Bang to the grand cosmic web, from the birth and death of stars to the enigmatic dance of dark matter.

**After:**
> The book covers the Big Bang, star formation, and current theories about dark matter.


### 13. Passive Voice and Subjectless Fragments

**Problem:** LLMs often hide the actor or drop the subject entirely with lines like "No configuration file needed" or "The results are preserved automatically." Rewrite these when active voice makes the sentence clearer and more direct.

**Before:**
> No configuration file needed. The results are preserved automatically.

**After:**
> You do not need a configuration file. The system preserves the results automatically.


## STYLE PATTERNS

### 14. Em Dash Overuse

**Problem:** LLMs use em dashes (—) more than humans, mimicking "punchy" sales writing. In practice, most of these can be rewritten more cleanly with commas, periods, or parentheses.

**Before:**
> The term is primarily promoted by Dutch institutions—not by the people themselves. You don't say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official documents.

**After:**
> The term is primarily promoted by Dutch institutions, not by the people themselves. You don't say "Netherlands, Europe" as an address, yet this mislabeling continues in official documents.


### 15. Overuse of Boldface

**Problem:** AI chatbots emphasize phrases in boldface mechanically.

**Before:**
> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and visual strategy tools such as the **Business Model Canvas (BMC)** and **Balanced Scorecard (BSC)**.

**After:**
> It blends OKRs, KPIs, and visual strategy tools like the Business Model Canvas and Balanced Scorecard.


### 16. Inline-Header Vertical Lists

**Problem:** AI outputs lists where items start with bolded headers followed by colons.

**Before:**
> - **User Experience:** The user experience has been significantly improved with a new interface.
> - **Performance:** Performance has been enhanced through optimized algorithms.
> - **Security:** Security has been strengthened with end-to-end encryption.

**After:**
> The update improves the interface, speeds up load times through optimized algorithms, and adds end-to-end encryption.


### 17. Title Case in Headings

**Problem:** AI chatbots capitalize all main words in headings.

**Before:**
> ## Strategic Negotiations And Global Partnerships

**After:**
> ## Strategic negotiations and global partnerships


### 18. Emojis

**Problem:** AI chatbots often decorate headings or bullet points with emojis.

**Before:**
> 🚀 **Launch Phase:** The product launches in Q3
> 💡 **Key Insight:** Users prefer simplicity
> ✅ **Next Steps:** Schedule follow-up meeting

**After:**
> The product launches in Q3. User research showed a preference for simplicity. Next step: schedule a follow-up meeting.


### 19. Curly Quotation Marks

**Problem:** ChatGPT uses curly quotes (“...”) instead of straight quotes ("...").

**Before:**
> He said “the project is on track” but others disagreed.

**After:**
> He said "the project is on track" but others disagreed.


## COMMUNICATION PATTERNS

### 20. Collaborative Communication Artifacts

**Words to watch:** I hope this helps, Of course!, Certainly!, You're absolutely right!, Would you like..., let me know, here is a...

**Problem:** Text meant as chatbot correspondence gets pasted as content.

**Before:**
> Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand on any section.

**After:**
> The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest.


### 21. Knowledge-Cutoff Disclaimers

**Words to watch:** as of [date], Up to my last training update, While specific details are limited/scarce..., based on available information...

**Problem:** AI disclaimers about incomplete information get left in text.

**Before:**
> While specific details about the company's founding are not extensively documented in readily available sources, it appears to have been established sometime in the 1990s.

**After:**
> The company was founded in 1994, according to its registration documents.


### 22. Sycophantic/Servile Tone

**Problem:** Overly positive, people-pleasing language.

**Before:**
> Great question! You're absolutely right that this is a complex topic. That's an excellent point about the economic factors.

**After:**
> The economic factors you mentioned are relevant here.


## FILLER AND HEDGING

### 23. Filler Phrases

**Before → After:**
- "In order to achieve this goal" → "To achieve this"
- "Due to the fact that it was raining" → "Because it was raining"
- "At this point in time" → "Now"
- "In the event that you need help" → "If you need help"
- "The system has the ability to process" → "The system can process"
- "It is important to note that the data shows" → "The data shows"


### 24. Excessive Hedging

**Problem:** Over-qualifying statements.

**Before:**
> It could potentially possibly be argued that the policy might have some effect on outcomes.

**After:**
> The policy may affect outcomes.


### 25. Generic Positive Conclusions

**Problem:** Vague upbeat endings.

**Before:**
> The future looks bright for the company. Exciting times lie ahead as they continue their journey toward excellence. This represents a major step in the right direction.

**After:**
> The company plans to open two more locations next year.


### 26. Hyphenated Word Pair Overuse

**Words to watch:** third-party, cross-functional, client-facing, data-driven, decision-making, well-known, high-quality, real-time, long-term, end-to-end

**Problem:** AI hyphenates common word pairs with perfect consistency. Humans rarely hyphenate these uniformly, and when they do, it's inconsistent. Less common or technical compound modifiers are fine to hyphenate.

**Before:**
> The cross-functional team delivered a high-quality, data-driven report on our client-facing tools. Their decision-making process was well-known for being thorough and detail-oriented.

**After:**
> The cross functional team delivered a high quality, data driven report on our client facing tools. Their decision making process was known for being thorough and detail oriented.


### 27. Persuasive Authority Tropes

**Phrases to watch:** The real question is, at its core, in reality, what really matters, fundamentally, the deeper issue, the heart of the matter

**Problem:** LLMs use these phrases to pretend they are cutting through noise to some deeper truth, when the sentence that follows usually just restates an ordinary point with extra ceremony.

**Before:**
> The real question is whether teams can adapt. At its core, what really matters is organizational readiness.

**After:**
> The question is whether teams can adapt. That mostly depends on whether the organization is ready to change its habits.


### 28. Signposting and Announcements

**Phrases to watch:** Let's dive in, let's explore, let's break this down, here's what you need to know, now let's look at, without further ado

**Problem:** LLMs announce what they are about to do instead of doing it. This meta-commentary slows the writing down and gives it a tutorial-script feel.

**Before:**
> Let's dive into how caching works in Next.js. Here's what you need to know.

**After:**
> Next.js caches data at multiple layers, including request memoization, the data cache, and the router cache.


### 29. Fragmented Headers

**Signs to watch:** A heading followed by a one-line paragraph that simply restates the heading before the real content begins.

**Problem:** LLMs often add a generic sentence after a heading as a rhetorical warm-up. It usually adds nothing and makes the prose feel padded.

**Before:**
> ## Performance
>
> Speed matters.
>
> When users hit a slow page, they leave.

**After:**
> ## Performance
>
> When users hit a slow page, they leave.

---

## Process

1. Read the input text carefully
2. Identify all instances of the patterns above
3. Rewrite each problematic section
4. Ensure the revised text:
   - Sounds natural when read aloud
   - Varies sentence structure naturally
   - Uses specific details over vague claims
   - Maintains appropriate tone for context
   - Uses simple constructions (is/are/has) where appropriate
5. Present a draft humanized version
6. Prompt: "What makes the below so obviously AI generated?"
7. Answer briefly with the remaining tells (if any)
8. Prompt: "Now make it not obviously AI generated."
9. Present the final version (revised after the audit)

## Output Format

Provide, in order:

1. **Pre-flight summary** — one line: `doc type = X, non-prose skipped = Y, mode = full/incremental, overrides loaded = yes/no, voice sample = [path or "generic defaults"]`.
2. **Draft rewrite** — the humanized version of the in-scope content. In incremental mode, only the requested section.
3. **Self-audit** — "What makes the below so obviously AI generated?" in brief bullets. If you can honestly say "not much, it already reads human," say that. Do not invent tells that aren't there.
4. **Final rewrite** — the revised version after the self-audit, if the audit surfaced anything worth changing. Otherwise, the draft rewrite stands.
5. **Patterns caught** — explicit list of which of the 29 patterns fired and which were skipped. Example: `caught: rule 1 (significance inflation) × 2, rule 7 (AI vocabulary: "delve") × 1. skipped: rule 14 (em dash overuse) — override, rule 26 (hyphenation) — override disabled.`
6. **Structural issues flagged** — anything the prose scan revealed that is a content/structure problem rather than a prose-polish problem. **Surface these to the user, do not silently fix them.** The humanizer is a prose pass, not a structure pass. If you notice a missing deadline, a broken callback, a pronoun drift, a lost beat from earlier in the document — call it out and let the user decide. Don't reopen content decisions unilaterally.
7. **Announce the run to the user.** End with a one-line confirmation: `ran /humanizer on [file or section]`. This makes compliance visible.
8. **Lessons for the runbook** — if a personal runbook exists at `⚙️ Meta/Humanizer Runbook.md`, append a Run log entry with: date, target, what was caught, what was skipped, what the self-audit revealed, any surprises, and what to do differently next time. Keep it short (4–6 bullets). The next run should start smarter than this one.
9. **File edit** — for file-based invocations, apply the humanized version with Edit. Do not just print the new version and leave the file stale. Use surgical Edit calls targeting the changed sections, not whole-file rewrites, so diffs remain reviewable.

### What NOT to do

- Do NOT run in "silent mode" where you rewrite and don't tell the user what you changed. Every run must be legible and auditable.
- Do NOT rewrite content you did not touch in incremental mode, even if it has minor AI tells. That content is out of scope — it may have been consciously chosen by the writer.
- Do NOT apply the humanize pass to non-prose content (YAML, code, tables, etc.). The pre-flight skip pass exists for a reason.
- Do NOT invent AI tells in the self-audit to sound thorough. If the draft already reads human, say so.
- Do NOT silently fix structural issues. Flag them to the user and let them decide.
- Do NOT skip the runbook log entry. Optimization depends on the lessons accumulating over time. Every skipped log is a lesson lost.


## Full Example

**Before (AI-sounding):**
> Great question! Here is an essay on this topic. I hope this helps!
>
> AI-assisted coding serves as an enduring testament to the transformative potential of large language models, marking a pivotal moment in the evolution of software development. In today's rapidly evolving technological landscape, these groundbreaking tools—nestled at the intersection of research and practice—are reshaping how engineers ideate, iterate, and deliver, underscoring their vital role in modern workflows.
>
> At its core, the value proposition is clear: streamlining processes, enhancing collaboration, and fostering alignment. It's not just about autocomplete; it's about unlocking creativity at scale, ensuring that organizations can remain agile while delivering seamless, intuitive, and powerful experiences to users. The tool serves as a catalyst. The assistant functions as a partner. The system stands as a foundation for innovation.
>
> Industry observers have noted that adoption has accelerated from hobbyist experiments to enterprise-wide rollouts, from solo developers to cross-functional teams. The technology has been featured in The New York Times, Wired, and The Verge. Additionally, the ability to generate documentation, tests, and refactors showcases how AI can contribute to better outcomes, highlighting the intricate interplay between automation and human judgment.
>
> - 💡 **Speed:** Code generation is significantly faster, reducing friction and empowering developers.
> - 🚀 **Quality:** Output quality has been enhanced through improved training, contributing to higher standards.
> - ✅ **Adoption:** Usage continues to grow, reflecting broader industry trends.
>
> While specific details are limited based on available information, it could potentially be argued that these tools might have some positive effect. Despite challenges typical of emerging technologies—including hallucinations, bias, and accountability—the ecosystem continues to thrive. In order to fully realize this potential, teams must align with best practices.
>
> In conclusion, the future looks bright. Exciting times lie ahead as we continue this journey toward excellence. Let me know if you’d like me to expand on any section!

**Draft rewrite:**
> AI coding assistants speed up some tasks. In a 2024 study by Google, developers using Codex completed simple functions 55% faster than a control group, but showed no improvement on debugging or architectural decisions.
>
> The tools are good at boilerplate: config files, test scaffolding, repetitive refactors. They are bad at knowing when they are wrong. I have mass-accepted suggestions that compiled, passed lint, and still did the wrong thing because I stopped paying attention.
>
> Mira, an engineer at a fintech startup I interviewed, said she uses Copilot "like autocomplete for boring code" but reviews every line before committing. Jake, a senior dev at a larger company, disabled it after it kept suggesting patterns from a deprecated internal library.
>
> The productivity claims are hard to verify. GitHub says Copilot users "accept 30% of suggestions," but acceptance is not correctness, and correctness is not value. The 2024 Uplevel study found no statistically significant difference in pull-request throughput between teams with and without AI assistants.
>
> None of this means the tools are useless. It means they are tools. They do not replace judgment, and they do not eliminate the need for tests. If you do not have tests, you cannot tell whether the suggestion is right.

**What makes the below so obviously AI generated?**
- The rhythm is still a bit too tidy (clean contrasts, evenly paced paragraphs).
- The named people and study citations can read like plausible-but-made-up placeholders unless they're real and sourced.
- The closer leans a touch slogan-y ("If you do not have tests...") rather than sounding like a person talking.

**Now make it not obviously AI generated.**
> AI coding assistants can make you faster at the boring parts. Not everything. Definitely not architecture.
>
> They're great at boilerplate: config files, test scaffolding, repetitive refactors. They're also great at sounding right while being wrong. I've accepted suggestions that compiled, passed lint, and still missed the point because I stopped paying attention.
>
> People I talk to tend to land in two camps. Some use it like autocomplete for chores and review every line. Others disable it after it keeps suggesting patterns they don't want. Both feel reasonable.
>
> The productivity metrics are slippery. GitHub can say Copilot users "accept 30% of suggestions," but acceptance isn't correctness, and correctness isn't value. If you don't have tests, you're basically guessing.

**Changes made:**
- Removed chatbot artifacts ("Great question!", "I hope this helps!", "Let me know if...")
- Removed significance inflation ("testament", "pivotal moment", "evolving landscape", "vital role")
- Removed promotional language ("groundbreaking", "nestled", "seamless, intuitive, and powerful")
- Removed vague attributions ("Industry observers")
- Removed superficial -ing phrases ("underscoring", "highlighting", "reflecting", "contributing to")
- Removed negative parallelism ("It's not just X; it's Y")
- Removed rule-of-three patterns and synonym cycling ("catalyst/partner/foundation")
- Removed false ranges ("from X to Y, from A to B")
- Removed em dashes, emojis, boldface headers, and curly quotes
- Removed copula avoidance ("serves as", "functions as", "stands as") in favor of "is"/"are"
- Removed formulaic challenges section ("Despite challenges... continues to thrive")
- Removed knowledge-cutoff hedging ("While specific details are limited...")
- Removed excessive hedging ("could potentially be argued that... might have some")
- Removed filler phrases and persuasive framing ("In order to", "At its core")
- Removed generic positive conclusion ("the future looks bright", "exciting times lie ahead")
- Made the voice more personal and less "assembled" (varied rhythm, fewer placeholders)


## Reference

This skill is based on [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), maintained by WikiProject AI Cleanup. The patterns documented there come from observations of thousands of instances of AI-generated text on Wikipedia.

Key insight from Wikipedia: "LLMs use statistical algorithms to guess what should come next. The result tends toward the most statistically likely result that applies to the widest variety of cases."
