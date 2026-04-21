## Phase 19: First Test Drive

"Everything is set up. Let's test it."

1. "Close this Claude session and open a new one in your vault folder."
2. "Ask me: 'What do you know about me?'"
3. "I should answer from your CLAUDE.md without you explaining anything."

If they want to keep going in this session:

"Or — let's do your first journal entry right now. How was today?"

Run the journal interview. Save the entry. Show them the file in their vault.

"That's your first entry. The vault is alive now. Every conversation from here makes it smarter."

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

## Important Notes for Claude

- GO SLOW. Wait for answers. Don't dump instructions.
- **NEVER STOP MID-SETUP.** After completing each phase, ALWAYS continue to the next phase automatically. Do not wait for the user to ask "what's next?" — tell them what's coming and proceed. The only reasons to pause are: (1) the user explicitly says "let's stop here" or "I need a break," (2) a critical install failed and needs manual intervention, or (3) the user asks a question that needs answering before continuing. After the journal phase especially — there are 10+ more phases. Don't stop there.
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
