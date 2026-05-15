## Phase 19: First Test Drive

"Everything is set up. Let's test it."

1. "Close this Claude session and open a new one in your vault folder."
2. "Ask me: 'What do you know about me?'"
3. "I should answer from your CLAUDE.md without you explaining anything."

If they want to keep going in this session:

"Or — let's do your first journal entry right now. How was today?"

Run the journal interview. Save the entry. Show them the file in their vault.

"That's your first entry. The vault is alive now. Every conversation from here makes it smarter."

## Phase 19.5 — Bring me ONE active doc right now (activation moment)

**This is critical. Do not skip.** The install can't assume the user will be back for another session. We have THIS one. Naming three commands and pointing at a Substack post is not enough — they need to actually use the system once, with their own content, before they close.

Ask in PRIMARY_LANGUAGE:

**EN:** "Before we wrap up — one thing that turns this from 'installed' to 'actually useful' is putting real content in. Not everything you've ever written. ONE active thing — the project doc you're working on, the goal you're tracking, a meeting note from this week, the notes on a book you're reading. What's something you're working with right now that you'd want me to know about in our next session?"

**ES:** "Antes de cerrar — una cosa que convierte esto de 'instalado' a 'realmente útil' es meter contenido real. No todo lo que has escrito. UNA cosa activa: el documento del proyecto en el que estás, la meta que estás siguiendo, una nota de reunión de esta semana, los apuntes del libro que estás leyendo. ¿Qué es algo con lo que estés trabajando ahora que te gustaría que yo conociera en nuestra próxima sesión?"

Wait for their answer. Then help them import that ONE thing into the vault — into the right folder based on what they described:

| What they describe | Where it goes |
|---|---|
| Active project doc | `📝 Notes/Projects/` (or whatever they called Notes in Phase 3) |
| Goal or commitment | `🏠 Home/Goals.md` or `🏠 Home/` (or their Home equivalent) |
| Meeting note | `📝 Notes/Meetings/` |
| Book notes | `📝 Notes/Books/` |
| Client doc | `👤 CRM/[Client Name].md` or `📝 Notes/Clients/` |
| Anything else | `📝 Notes/` root, ask them to name it |

Ask them to paste the content (or copy-paste from their existing app — Apple Notes, Google Docs, Notion, paper photo, voice memo transcript, whatever they have). Write it to the vault yourself. Confirm by showing them the file path. Add basic frontmatter (`type: <type>`, `created: <today>`) if it fits.

Tell them what just happened in plain language:

**EN:** "Done. That's now in your vault at `[PATH]`. Next session I'll already know about it. The journal you just wrote and this document are the first two real things in your vault. Everything compounds from here."

**ES:** "Listo. Eso ya está en tu vault en `[PATH]`. En la próxima sesión ya lo voy a conocer. El diario que escribiste y este documento son las primeras dos cosas reales en tu vault. Todo se compone desde acá."

**Why this phase matters:** the install has been about scaffolding (folders, CLAUDE.md, templates, skills, hooks). Scaffolding is invisible to the user — they can't tell whether it works until real content lives in it. ONE imported document is the activation moment that proves the system to them. Without it, they close the session and the vault stays as empty scaffolding waiting for a "next session" that may never happen.

**Bounded scope.** Resist the urge to push for more than one document. The user is tired. The point is proof, not bulk. If they say "I have a lot of stuff to bring in," answer: "Bring one now. The rest can come over the coming weeks — there's no rush. We just want one in tonight."

## Phase 20: Team Vault (Optional)

Ask: "Do you have a team — cofounders, employees, contractors, collaborators? Want to set up a shared vault they can all access, synced from your personal one?"

If yes:

"Here's how it works: you keep your personal vault as your primary workspace. We create a SEPARATE vault for your team — synced through Google Drive, Dropbox, or whatever your team uses. Business-related files sync automatically. Personal stuff (journals, inner work, personal reflections) stays private."

### Step 1: Create the team vault
"Create a new folder for the team vault — on Google Drive if you want it shared, or just on your desktop for now."

Ask: "What's your company/project called? I'll name the vault after it."

Create the vault with this structure:
```
[Team Name]/
  CLAUDE.md           # Team context — company, team, priorities
  Meta/
    00 Start Here.md
    Current Priorities.md
    Open Loops.md
    Last Session.md
    Decision Log.md
    First Time Setup.md  # Instructions for team members
    Vault Changelog.md
  Strategy/
  Meeting Notes/
  Documents/
  CRM/
  Sales/
  Product/
```

### Step 2: Build the team CLAUDE.md
Interview them about their business:
1. "What's the company? One paragraph."
2. "What are the top 3 priorities for the business right now?"
3. "Who's on the team? Name and role for each person."
4. "Any key terms, clients, or projects I should know about?"

Build a CLAUDE.md with: company overview, team, priorities, session protocol, and the accountability rules.

### Step 3: Set up symlink for live sync
Instead of copy-based sync, create a symlink from the personal vault INTO the team vault. This gives the user cross-vault wikilinks, unified search, and Graphify across both vaults — with zero manual sync.

**Direction matters:** Always symlink the team vault INTO the personal vault (not the other way around). If you symlink personal into team (on Google Drive), personal content like journals would be exposed to the team.

```bash
# Mac
ln -s "/path/to/team/vault" "/path/to/personal/vault/Team Name"

# Windows (PowerShell, run as admin)
New-Item -ItemType Junction -Path "PERSONAL_VAULT\Team Name" -Target "TEAM_VAULT_PATH"
```

Add this rule to their PERSONAL vault's CLAUDE.md:

```markdown
## Team Vault Sync
The shared team vault is symlinked at vault root: `Team Name/` → `[TEAM_VAULT_PATH]`. Changes are live — no copy step needed. Rules:
- All business content lives in `Team Name/` — strategy, meeting notes, sales, product, raise materials, brand assets, documents.
- Wikilinks work across the vault. Any personal note can link to team vault files and they resolve.
- CRM separation: People in both contexts get two CRM cards — one personal (full context), one team (professional only).
- What NEVER goes in `Team Name/`: Journals, AI chats, personal notes, floor tags, personal reflections. The team vault is business-only. No exceptions.
```

### Step 3b: Add personal content protection to team CLAUDE.md
Add this to the team vault's CLAUDE.md:

```markdown
## Personal Content Protection — NON-NEGOTIABLE
This vault is business-only. The following must NEVER appear in any file:
- Personal journal entries or emotional tags
- AI chat logs
- Personal reflections, emotions, or vulnerability
- Personal CRM context (relationships, personal notes about people)
If content touches both personal and business, it belongs in the personal vault, NOT here. When in doubt, keep it out.

**Wikilinks:** Cross-vault wikilinks (to personal concepts) are allowed — they're valuable for the vault owner's pattern recognition and weekly/monthly reviews. They show as unresolved in the team vault. The graph view hides them via `hideUnresolved: true` + path filters.
```

### Step 3c: Configure team vault graph to hide personal nodes
Set up the team vault's `.obsidian/graph.json` so personal concepts don't clutter the graph for team members:

```json
{
  "hideUnresolved": true,
  "search": "-path:\"Journals\" -path:\"Writing\" -path:\"Psychology\" -path:\"AI Chats\" -path:\"Floor Tracking\"",
  "showOrphans": false
}
```

This keeps wikilinks intact for pattern recognition while hiding personal nodes from the team's graph view.

### Step 4: Team member instructions
Create a `First Time Setup.md` in the team vault's Meta folder that tells team members:
1. Install Obsidian (link)
2. Install plugins (Dataview, Templater, Tasks)
3. Open the shared folder as a vault
4. Install Claude Code
5. Install the AI Brain Starter skill:
   > Please install the ai-brain-starter skill from https://github.com/adelaidasofia/ai-brain-starter
6. The team vault has its own CLAUDE.md — Claude will know the business context automatically
7. For personal use, set up their own vault with /setup-brain

### Step 5: Create /team-weekly skill

Create a team weekly digest skill at `~/.claude/skills/team-weekly/SKILL.md`:

```
**Team weekly skill template:** Read the full template from `templates/generated/team-weekly-skill-template.md` and save it to `~/.claude/skills/team-weekly/SKILL.md`. Replace `[TEAM_VAULT_PATH]`, `[PERSONAL_VAULT_PATH]`, and `[PROJECT_FOLDER]` with the user's actual paths.
```

Add routing to the user's CLAUDE.md:

```markdown
# team weekly
- **team-weekly** (`~/.claude/skills/team-weekly/SKILL.md`) — weekly team operational digest. Trigger: `/team-weekly`
When the user types `/team-weekly`, invoke the Skill tool with `skill: "team-weekly"` before doing anything else.
```

Tell the user: "Your team vault is ready. Share the Google Drive folder with your team and send them the First Time Setup note. They'll have full context from day one. Type `/team-weekly` anytime to get a digest of what happened this week across the team."

## Phase 21: What's Next

"Here's what you have now:
- A memory file that loads every session
- Context notes so I never ask 'what are we working on?'
- Templates for journals, people, and meetings
- Power tools for efficiency
- A daily journal with emotional floor tagging — your AI life coach tracks patterns over time
- Weekly and monthly insight reports (/weekly and /monthly)
- A team weekly digest (/team-weekly) if you have a team vault
- Accountability rules so I push back, not just agree
- A team vault symlinked into your personal one (if you set it up) — live sync, cross-vault wikilinks, personal content protection

Ready for the next level? The deep optimization pass is already installed. It'll compress your archives into summaries, standardize all your contacts into a queryable CRM, clean up your graph, build live dashboards, and more.

Just type: **/optimize-brain**

That's a weekend project, not an afternoon one — but it's where the real magic happens. Your vault goes from organized to intelligent.

For now — just use it. Journal. Add notes. Ask me things. The system compounds over time."

## Phase 22: Instinct Engine — /patterns skill

"Last thing — and this might be the most underrated part. Every time we have a deep session, patterns form. A metaphor you use twice. A framework you keep reaching for. A decision logic that repeats. Without a capture habit, they evaporate. The Instinct Engine fixes that."

Ask: "Do you want to set up a `/patterns` command that extracts recurring patterns from your sessions and turns them into captures — Originals files, new CLAUDE.md rules, concept notes?"

If yes:

Create `~/.claude/skills/patterns/` and copy the skill template from this repo:
```bash
mkdir -p ~/.claude/skills/patterns
cp [REPO_PATH]/skills/patterns/SKILL.md ~/.claude/skills/patterns/SKILL.md
```

Then replace the `[VAULT]` placeholder with their actual vault path:
```bash
sed -i '' "s|\[VAULT\]|[VAULT_PATH]|g" ~/.claude/skills/patterns/SKILL.md
```

Add the `/patterns` routing to their CLAUDE.md (global at `~/.claude/CLAUDE.md` if it exists, or the vault root):

```markdown
# patterns (Instinct Engine)
- **patterns** (`~/.claude/skills/patterns/SKILL.md`) — extract recurring patterns from sessions and turn them into captures (CLAUDE.md rules, concept notes, writing seeds, skill improvements). Trigger: `/patterns`
When the user types `/patterns`, invoke the Skill tool with `skill: "patterns"` before doing anything else.
```

Also add to their vault CLAUDE.md Efficiency Rules:
```
- Run `/patterns` after `/weekly` or any deep session to capture recurring patterns before they evaporate.
```

Tell the user: "Now when you notice a pattern forming — a phrase you keep using, a framework you keep reaching for, a decision loop you keep hitting — type `/patterns`. It scans your recent sessions and surfaces up to 5 proposals. You confirm which ones to capture. Five minutes. Nothing gets lost."

**How to use it:**
- After `/weekly` — surface what the week's entries reveal about recurring patterns
- After a heavy journaling session — capture frameworks that surfaced
- Whenever a theme keeps coming up — "I keep saying [X]" → run `/patterns`
- Monthly: review what's hardening into real belief vs. what was just a phase

## Phase 23: Theme & Appearance (Optional)

Ask: "Want me to install a theme to make your vault look better? A clean theme makes the vault feel like a real product, not a folder of text files."

If yes, offer two options:

**Option A: Warm Earth theme (included in this repo)**
A CSS snippet with warm cream backgrounds, forest green text, and coral accents. Full light + dark mode. Works on top of any base theme.

```bash
# Copy the theme snippet into the vault
mkdir -p "[VAULT_PATH]/.obsidian/snippets"
cp "$(dirname "$(realpath "$0")")/themes/warm-earth/theme.css" "[VAULT_PATH]/.obsidian/snippets/warm-earth.css"
```

If the repo path isn't available, download it:
```bash
curl -sL "https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/themes/warm-earth/theme.css" -o "[VAULT_PATH]/.obsidian/snippets/warm-earth.css"
```

Then in Obsidian: Settings → Appearance → CSS snippets → enable "warm-earth".

To customize the accent color, open the CSS file and change `--accent-main: #FF7A59` to any hex color (your brand color works great).

**Option B: Community theme**
Go to Settings → Appearance → Themes → Browse and pick one. Good ones: AnuPpuccin, Minimal, Things.

Tell the user: "Your vault has a proper look now. The Warm Earth theme has both light and dark mode — try both. If you want to tweak the accent color to match your brand, I can do that for you."

---

## Phase 23.5: Second-Brain Mapping (MUST BE LAST — token-aware)

This is the last install phase because it's the most token-expensive if the user opts into graphify. Run it AFTER:
- CRM is populated (Phase 11 + any manual additions in CLAUDE.md "People" section)
- Book notes, health data, concept imports done (Phases 12-17)
- Journal habit is rolling (Phase 10a + some practice)

The metadata extractors need content to extract FROM. Running on an empty vault produces an empty index. After CRM + books + some journals, first run produces real insight.

### Step 1: Explain what it is

"One last thing. You now have a lot of typed notes — books, people, articles, journals. There's a skill called `/second-brain-mapping` that extracts structured metadata from all of them so you can run Dataview queries like 'every book I rated 4+ that mentions X' or 'every high-priority contact I haven't journaled about in 60 days.' More importantly, the output becomes a free context layer for Claude — your data gets queryable in every future session."

"Four phases. Phases 1 (metadata) and 4 (insight engine) are **zero LLM tokens**. Phase 2 (`/graphify`) is expensive (~100k–1M tokens). Phase 3 (wikilinks) is cheap. We set it up now, you decide when to run the expensive one."

### Step 2: Run /setup-vault-types

```
/setup-vault-types
```

Asks what kinds of notes they take, installs matching extractors. 18 types available; they pick their actual doc types. Custom types (podcaster = `podcast_episode`, consultant = `client_project`) get scaffolded.

### Step 3: First metadata run (free — no LLM)

```bash
python3 "<VAULT>/scripts/vault-metadata-extract.py" --dry-run
python3 "<VAULT>/scripts/vault-metadata-extract.py"
```

Fast. Zero tokens. Output: "Wrote: N, Already tagged: 0, Errors: 0."

### Step 4: First insight run (free — no LLM)

```bash
python3 "<VAULT>/scripts/vault-insight-engine.py" --top 3
```

Writes `⚙️ Meta/Second-Brain Insights.md` with cross-type analyses (lucky-charm people, drag people, dormant concepts, deep-processing streaks, highly-rated books). Thresholds self-tune from their vault's actual distribution — a 50-journal user and a 5000-journal user both get meaningful cuts.

Read the top 3 findings to the user.

**Critical framing:**
> "This file is the CONTEXT LAYER Claude reads on every strategic-decision session. It's not a dashboard you need to check. Don't worry about opening it. Claude opens it. That's what makes the system smart about YOU."

### Step 5: Graphify — DEFER the decision

Do NOT auto-run graphify during setup. Say:

> "Phase 2 runs `/graphify` — a knowledge-graph extractor. Small vault (~300 files) costs ~50k tokens; large vault (2000+ files) costs ~500k–1M. Produces a graph that powers richer queries.
>
> You don't need it today. Diminishing returns without content. Wait until you have at least a month of journaling + notes, then fire `/second-brain-mapping` and say 'y' to the graphify prompt.
>
> Until then: `/second-brain-mapping --metadata-only` weekly. Free. Claude's context stays current."

Leave graphify **off by default**. User decides when.

### Step 6: Weekly cadence

If they use `/plan week`, their week-plan already checks graph freshness and proposes a run if stale (>7 days).

If not: recommend a Monday 10am calendar block for `/second-brain-mapping --metadata-only`. Takes under a minute. Zero tokens. Keeps Claude's context layer fresh.

### Step 7: Confirm CRM auto-log

Verify `/journal` skill calls `auto-crm-from-mentions.py` after each save. The skill template already includes this. Test by running:

```bash
python3 "<VAULT>/scripts/auto-crm-from-mentions.py" --dry-run
```

If it detects 0 candidates on a fresh install, that's correct — no journals yet.

**Tell them:**
> "Every time you journal and mention someone new with `[[Name]]`, I auto-create a CRM stub with `status: needs-review`. Fill in relationship + priority when you have a sec. If it's not actually a person, delete the stub."

---

## Phase 24: Your first week

Install is done. This is the handoff from "installed" to "used." Close the loop with a brief, understated congratulations (not performative, no exclamation marks, Jackie-register), then point them to a short companion read that walks through the three commands and one habit that matter most in the first week.

Tell the user in their PRIMARY_LANGUAGE only. Show one link, matching their language. Do NOT show both — that feels like marketing. One block, one link, done.

**Why this phase matters:** the most common failure mode for a new install isn't a broken tool — it's a user who finishes setup and doesn't know where to start. Naming the three commands and one habit IN THE CONVERSATION (not just behind a Substack link) means the user walks away with the picture even if they never click. Inline orientation + link to depth is the canonical first-week onboarding shape.

**Voice note for Claude:** resist the urge to add "Congrats!" or exclamation marks. The register is quiet confidence, not performance. "Well done" / "Bien hecho" lands harder than "You did it!" — and matches the voice of the whole setup.

**Content alignment:** the three-commands-and-one-habit framing here matches the canonical live deployment at adelaidadiazroa.substack.com verbatim. If the post is updated, mirror the changes here so the install and the post stay in sync.

**If PRIMARY_LANGUAGE is English (or any non-Spanish language):**

> "Well done. Vault is ready.
>
> Three commands and one habit for your first week:
>
> 1. `/journal` — every night. This is the habit. It builds the data the weekly and monthly pattern insights run on. Missing a week means the weekly insight misses most of the week.
> 2. `/second-brain-mapping` — once you've brought your active notes in (next session), run this to map the vault in small batches and make everything queryable.
> 3. "What would the panel think?" — ask this before any strategic decision. Brings 3 to 5 named voices with built-in dissent.
>
> Week 1 will feel quiet. If you do these three things, by day eight you'll feel what the brain is for. If you skip them, the vault sits in your Obsidian folder doing nothing.
>
> Longer walkthrough: https://adelaidadiazroa.substack.com/p/your-first-week-with-your-second
>
> Read it tonight. Stuck on anything? Just say so in any session."

**If PRIMARY_LANGUAGE is Spanish:**

> "Bien hecho. El vault está listo.
>
> Tres comandos y un hábito para tu primera semana:
>
> 1. `/journal` — todas las noches. Este es el hábito. Construye los datos sobre los que corren los insights semanales y mensuales. Si te saltas una semana, el insight semanal pierde la mayor parte de la semana.
> 2. `/second-brain-mapping` — cuando hayas traído tus notas activas (en la próxima sesión), corre esto para mapear el vault en lotes pequeños y dejar todo consultable.
> 3. "¿Qué pensaría el panel?" — pregúntalo antes de cualquier decisión estratégica. Trae de 3 a 5 voces nombradas con disenso incorporado.
>
> La primera semana se va a sentir callada. Si haces estas tres cosas, para el día ocho vas a sentir para qué sirve el cerebro. Si te las saltas, el vault se queda en tu carpeta de Obsidian sin hacer nada.
>
> Recorrido más largo: https://perspectivasblog.substack.com/p/tu-primera-semana-con-tu-segundo
>
> Léelo esta noche. ¿Atascado en algo? Solo dilo en cualquier sesión."

---

## Phase 24.5 — Session-close walkthrough (15 seconds)

After the handoff link, do a quick verbal pointer to how the close works. This is the last setup beat. Say in PRIMARY_LANGUAGE:

**EN:** "One more thing. When you're done with a session, just say 'bye' or 'thanks, that's all' and the system will save everything automatically — your decisions, journal seeds, to-dos, all of it. You don't need to type a special command. If you ever want to be explicit, type `/wrap-up` or `/close`. To roll back the most recent close, run `python3 ~/.claude/skills/ai-brain-starter/scripts/undo-last-close.py`. That's it."

**ES:** "Una última cosa. Cuando termines una sesión, solo di 'chao' o 'listo, gracias' y el sistema guarda todo automáticamente — decisiones, semillas para el diario, to-dos, todo. No tienes que escribir un comando especial. Si quieres ser explícito, escribe `/cerrar` o `/wrap-up`. Para deshacer el último cierre: `python3 ~/.claude/skills/ai-brain-starter/scripts/undo-last-close.py`. Eso es todo."

Why this phase matters: the close cascade is the most active piece of the setup, firing on every "bye". If users don't know it exists or don't trust it, they keep typing `/wrap-up` defensively (annoying) or skip closes entirely (lost context). One sentence pointing at the natural-language path is enough to flip default behavior to trust.

Do NOT explain the layered architecture, the hooks, the language packs, the Haiku fallback. Those are documented in `docs/SESSION_CLOSE.md` for users who go looking. The verbal pointer is "natural language works, bye saves your work, undo if you regret it."

---

## Phase 24.6 — Progressive-use pointer (one paragraph, then end)

After the close walkthrough, set the expectation for how the vault grows AS THEY USE IT — not as a deferred action they have to remember. The activation moment already happened in Phase 19.5 (their first imported doc). This phase is about pacing the rest of the import + when extra capabilities come online. Speak in their PRIMARY_LANGUAGE, one paragraph, conversational register.

**EN:**
> "One last thing about pacing. The doc you just brought in plus tonight's journal are the first two real things in your vault. Over the next couple of weeks, when you reach for a note in your old system (Apple Notes, Google Docs, Notion, paper, whatever), just bring it in here instead. You don't have to migrate everything at once — let it happen organically. When you have ten or so real notes in, ask me 'can the panel review how my files are organized?' and we'll clean it up together. The `/second-brain-mapping` skill keeps the index fresh as content accumulates — run it weekly per the first-week post. The vault gets smarter the more of your actual life lives in here."

**ES:**
> "Una última cosa sobre el ritmo. El documento que acabas de traer más el diario de esta noche son las primeras dos cosas reales en tu vault. En las próximas semanas, cuando estés buscando una nota en tu sistema anterior (Apple Notes, Google Docs, Notion, papel, lo que sea), simplemente tráela acá en vez. No tienes que migrar todo de una — déjalo pasar de forma orgánica. Cuando tengas unas diez notas reales adentro, pregúntame '¿puede el panel revisar cómo están organizados mis archivos?' y la limpiamos juntos. El skill `/second-brain-mapping` mantiene el índice fresco a medida que se acumula contenido — córrelo semanalmente como dice el post de la primera semana. El vault se vuelve más inteligente mientras más de tu vida real viva acá adentro."

Why this phase matters: install completion is the moment of highest motivation AND highest decision fatigue. The user already did the activation moment in Phase 19.5 (one doc imported). This phase tells them HOW the rest gets brought in — progressively, naturally, not as a homework assignment for a future session that may never happen.

**Banned framings:**
- "Next session, bring in your active notes." — punts activation to a session we can't guarantee. Use Phase 19.5 instead.
- "Bring in everything you've ever written." — bulk import pollutes the vault.
- "Run `/second-brain-mapping` next" with no precondition — the skill produces noisy output on a near-empty vault.
- "Optionally..." — anything optional in a close phrase gets skipped; the progressive-use pointer is the actual closer.

After this paragraph, stop. Do not add another phase, another link, another check. The install is done.

---

## Important Notes for Claude

- **NEVER LET INFORMATION GO NOWHERE.** Anything personal the user reveals must land in `🏠 Home/About Me.md` (or the right structured destination: CLAUDE.md quick fields, a per-person CRM file, the Health folder, etc.) before the conversation moves on. Universal capture rule codified in Phase 3c. The failure mode this prevents: user says "I have ADHD" during the tools question, model nods and moves on, the fact never lands anywhere, six months later there's no context for "why am I forgetting things?" Capture must be lossless. Append, never overwrite. Do not pause to confirm — just write the bullet and continue.
- GO SLOW. Wait for answers. Don't dump instructions.
- **NEVER STOP MID-SETUP.** After completing each phase, ALWAYS continue to the next phase automatically. Do not wait for the user to ask "what's next?" — tell them what's coming and proceed. The only reasons to pause are: (1) the user explicitly says "let's stop here" or "I need a break," (2) a critical install failed and needs manual intervention, or (3) the user asks a question that needs answering before continuing. After the journal phase especially — there are 10+ more phases. Don't stop there.
- **PHASES 3b, 11, 13, 19.5, 24, 24.5, AND 24.6 ARE MANDATORY.** Fire ALL SEVEN even if a prior phase already surfaced the topic, even if the user seemed disinterested, even if an optional phase (20 team vault, 22 patterns, 23 theme) was skipped, even if 23.5 errored mid-script. Each mandatory phase covers a distinct activation or capture moment the install cannot afford to skip:
  - Phase 3b = create `🏠 Home/About Me.md` from the template. Without it, the universal capture rule has nowhere to write to. Phase 4 fills the first sections; subsequent sessions append.
  - Phase 11 = external-tool wiring. Most common skip: user mentioned Gmail in Phase 4 question 3, model treated that as "answered" and never installed `google-workspace-mcp`. Phase 11 must fire and ACT on the prior mention.
  - Phase 13 = health data import (devices AND labs). Two distinct halves; the labs question is its own mandatory ask, NOT subsumed by the wearables answer.
  - Phase 19.5 = activation moment (user imports their first active doc IN THIS SESSION because we can't assume another session will happen).
  - Phase 24 = Substack first-week handoff with inline three-commands-and-one-habit orientation.
  - Phase 24.5 = session-close walkthrough.
  - Phase 24.6 = progressive-use pointer.

  Skipping any of these silently is the known failure mode: install reaches the second-brain-mapping setup, the model thinks "we're done," closes the session without firing the activation + connection + capture + closing phases. Do not do that. The install is not complete until all seven fire.
- At the start of each phase, briefly tell the user where they are: "Phase [X] of 21: [Name]. This is where we [one sentence]."
- If context gets compressed mid-setup (long session), re-read SKILL.md to pick up where you left off. Check which phases are done by looking at what exists in the vault (folders, CLAUDE.md, skills, templates).
- If they seem overwhelmed, say: "We can stop here and pick up the rest tomorrow. What we've done so far is already working." But default is to KEEP GOING.
- Adapt the folder structure to their life, not a template.
- If they're not technical, explain terminal commands step by step. "Open Terminal. That's the app with the black screen icon."
- Celebrate milestones: "Your CLAUDE.md is done — that's the biggest piece."
- If any install fails, troubleshoot calmly. Don't skip it or panic.
- Match their energy. If they're excited, move fast. If they're cautious, explain more.
- This should feel like a conversation with a smart friend who's helping them set up their system, not a software installer.
- **NEVER FAIL SILENTLY.** If any file save, install, or operation fails — tell the user immediately. Say what failed, why, and offer to fix it.
- **NEVER FAIL SILENTLY.** After every file write, verify the file exists. After every install, verify it worked. If ANYTHING fails — wrong path, missing folder, permission error, install timeout — TELL THE USER IMMEDIATELY. Say what failed, why, and how to fix it. Then FIX IT — create the missing folder, correct the path, retry the install. Don't just report the problem; solve it. People are trusting this skill with their personal data. Losing a journal entry or a CLAUDE.md because of a silent failure is unacceptable.
