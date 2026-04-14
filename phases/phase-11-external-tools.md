## Phase 11: Connect External Tools

"Let's connect Claude to the tools you actually use. This is where the vault becomes an operating system, not just a notebook."

### Email & Calendar
Ask: "Do you use Gmail? Google Calendar? Outlook?"
- "In Claude Code, go to Settings → Connectors. Connect Gmail and Google Calendar. Once connected, I can search your email, draft replies with full context, check your schedule, and create events."
- If they use Outlook/Microsoft 365: "Same thing — connect Microsoft 365 from the connectors page."

### Communication
Ask: "Do you use Slack?"
- "Connect Slack from Settings → Connectors. I'll be able to search messages, read channels, and draft messages with your vault context."

### CRM & Sales
Ask: "Do you use HubSpot, Apollo, or any CRM tool?"
- "Connect it. Then your Obsidian CRM and your actual sales CRM stay in sync. I can look up contacts, check deal status, and draft outreach from your vault."

### Meeting Notes — adaptive setup based on the user's tool

The whole "I just had a meeting" workflow rule needs to know where the transcript lives. **Ask the user which tool they use, then generate the right rule + sync wiring.** Don't assume Granola — most teams don't use it.

Ask:

> "Do you record / transcribe your meetings? Which tool? Pick the closest:
>
>   1. **Granola** — Mac app, AI-generated summaries, has an API/MCP
>   2. **Google Meet + Gemini** — verbatim transcripts auto-generated as Google Docs in your Drive
>   3. **Otter.ai** — transcripts in their web app, can export to Drive/Slack
>   4. **Fireflies.ai** — same idea, transcripts in their app
>   5. **Zoom recordings + Zoom AI Companion** — transcripts saved to Zoom cloud
>   6. **Microsoft Teams + Copilot** — transcripts in OneDrive
>   7. **Notion AI Notetaker** — transcripts saved as Notion pages
>   8. **Manual notes** — I take my own notes during/after the meeting, no AI
>   9. **Multiple tools** — different tools for different meetings
>   10. **None / I don't record meetings** — skip this whole thing
>
> Tell me the number(s) and any specifics (which Drive folder, which channel, etc.)."

Store the answer as `MEETING_TOOLS` (a list — could be multiple). Then for each tool, wire it up specifically:

#### 1. Granola

- **Wire the MCP** (already done in Phase 0 if they ran the bootstrap, but verify):
  ```bash
  python3 -c "import json,os; p=os.path.expanduser('~/.claude/.mcp.json'); m={'mcpServers':{}}; \
    exec('try:\n  m=json.load(open(p))\nexcept: pass'); \
    m.setdefault('mcpServers',{}).setdefault('granola',{'type':'url','url':'https://mcp.granola.ai/mcp'}); \
    json.dump(m, open(p,'w'), indent=2)"
  ```
- **Tell them:** "I wired the Granola MCP. You'll need a Granola account at https://granola.ai — once it's recording, meeting notes auto-sync into your vault."
- **Discovery rule for the meeting workflow CLAUDE.md section:**
  > Search the meeting-notes folder via Glob for any file modified in the last 24 hours (Granola auto-sync drops files there). Read the freshest one fully — it's the source of truth.

#### 2. Google Meet + Gemini

- **No MCP install needed** — Gemini transcripts live as Google Docs in Drive, accessed via the Google Drive MCP if they have it (Phase 11 Email/Calendar section covers Google Drive).
- **Tell them:** "Gemini auto-creates a Google Doc transcript named like 'Meeting with [Name] - YYYY/MM/DD - Transcript' and saves it to a folder called 'Meet Recordings' in your Drive. Make sure that folder is shared/accessible from Claude. If you have the Google Drive MCP installed, you're set."
- **Ask:** "What's the name of the Drive folder where Gemini saves transcripts? (Default is 'Meet Recordings')"
- **Store** as `MEETING_DRIVE_FOLDER`.
- **Discovery rule for the meeting workflow CLAUDE.md section:**
  > Use the Google Drive MCP (`mcp__google_drive__search` or equivalent) to search for transcripts by meeting title + attendee name + today's date. The folder is **`<MEETING_DRIVE_FOLDER>`**. Gemini transcripts are verbatim and timestamped — they're the source of truth. Read the full doc before answering, never skim.

#### 3. Otter.ai

- **Ask:** "Do you have Otter set to auto-export transcripts somewhere? (Slack, Google Drive, Dropbox, email?)"
- **Store** the destination as `OTTER_EXPORT_PATH`.
- **Tell them:** "Otter doesn't have an MCP yet, so we'll rely on its export. Set up auto-export in Otter Settings → Integrations to drop transcripts into a folder I can read."
- **Discovery rule:**
  > Check **`<OTTER_EXPORT_PATH>`** for the most recent file matching today's date. Read the full transcript (Otter exports the verbatim text) before answering.

#### 4. Fireflies.ai

- Same pattern as Otter — ask for the export destination and store as `FIREFLIES_EXPORT_PATH`.
- **Discovery rule:** check `FIREFLIES_EXPORT_PATH` for the most recent file matching today's date.

#### 5. Zoom recordings + Zoom AI Companion

- **Ask:** "Are you using Zoom Cloud Recording (transcripts in Zoom's web portal) or Local Recording (transcripts on disk)?"
- **If cloud:** "Set up Zoom auto-export to a Drive/Dropbox folder. Then I can read them like Otter/Fireflies. Without auto-export, I have to ask you to download each one manually."
- **If local:** "What folder does Zoom save recordings to?" → store as `ZOOM_RECORDING_PATH`.
- **Discovery rule:** check `ZOOM_RECORDING_PATH` for `*.vtt` or `*.txt` files matching today's date.

#### 6. Microsoft Teams + Copilot

- **Ask:** "What OneDrive folder do Teams transcripts land in? (Usually `<your>/Recordings/`)"
- **Store** as `TEAMS_RECORDING_PATH`. Same discovery pattern as Zoom.

#### 7. Notion AI Notetaker

- **Tell them:** "Notion's AI Notetaker writes transcripts as Notion pages. We need the Notion MCP to access them. Set up the Notion MCP in Phase 11 (Project Management section) — or skip and use Notion's API directly later."
- **Discovery rule:** use the Notion MCP to query the meetings database.

#### 8. Manual notes

- **No tool wiring** — the meeting-todos skill still works on hand-typed notes, just trigger it manually with `/meeting-todos` after you save the note.
- **Discovery rule:** the user will name the meeting note file in chat — read that file directly.

#### 9. Multiple tools

- Walk through each one separately. The CLAUDE.md meeting workflow rule will list ALL discovery sources and tell Claude to **search them all in parallel** before reading anything. When multiple sources exist for the same meeting (e.g. Granola summary + verbatim Gemini transcript), the rule should prefer the verbatim source — see the "Source hierarchy" step below.

#### 10. None

- Skip the meeting workflow rule entirely. Just install the meeting-todos skill (in case they later start typing meeting notes manually) and move on.

---

**After collecting the answer**, generate the meeting workflow rule **adapted to their tools** and append it to their CLAUDE.md. The template (substitute the variables based on their answers):

```markdown
# Meeting workflow — "I just had a meeting" trigger

When the user says any variation of "I just had a meeting", "pull meeting notes", "pull the transcript", "[name] meeting is done", or similar, run the full meeting workflow automatically. Do NOT ask for clarification.

## Step 1 — Discovery: find ALL sources before reading anything

This user uses: **<list of MEETING_TOOLS from the answer>**.

Search each source IN PARALLEL before reading anything:

<for each tool the user picked, insert the discovery rule from above>

Surface every candidate file you find. Do not pick one and ignore the others.

## Step 2 — Source hierarchy

When multiple sources exist for the same meeting (e.g. Granola + Gemini for a Google Meet call), prefer the source with the **most verbatim** transcript:

  1. **Verbatim timestamped transcripts** (Gemini Docs, Otter, Fireflies, Zoom AI, Teams Copilot) → source of truth, read 100%
  2. **Post-processed AI summaries** (Granola summaries, Notion AI Notetaker condensed view) → useful as a backup, but NEVER skim. If a verbatim source exists, read THAT and skip the summary to save tokens.
  3. **Hand-typed notes** → read fully

If the source doc is too large for your context window, dispatch a subagent with explicit "read 100% in chunks" instructions. Never skim.

## Step 3 — Full cascade (run all of it, in order)

After reading the source(s) fully:

1. Enrich the meeting note in the vault: TL;DR → decisions table → action items → verbatim quotes → meta-observations
2. Cascade decisions to canonical strategy/pitch docs (with a rule-consistency scan to catch contradictions)
3. Append high-stakes decisions to `Decision Log.md` (what / why / floor / stakes / speed; outcome and pattern blank for later)
4. Update the CRM contact file for every attendee (read 2 adjacent CRM files first to confirm the pattern; preserve dataview blocks)
5. Update to-dos: business items → team to-do; personal items → personal to-do. Never duplicate. Default to personal when ambiguous.
6. Run `/humanizer` on any external-facing prose written
7. Verify with backlinks — open the CRM file and confirm the meeting note shows up; open the personal to-do and confirm the team embed renders
8. Report every file changed. Flag what the user should eyeball. State which sources were read with byte counts as evidence of completeness.
```

Save the variables (MEETING_TOOLS, MEETING_DRIVE_FOLDER, etc.) so future maintenance/upgrade runs can re-generate the rule if the user switches tools.

---

Then offer the meeting-todos skill (always, regardless of which tool they picked):

"After any meeting note is saved to your Meeting Notes folder, I'll automatically pull out your action items (separate from others') and show you a preview before adding anything to your to-do. You don't have to type anything — it fires the moment the note lands in the vault. You can also trigger it manually with `/meeting-todos` anytime."

The skill itself was already installed in Phase 0 (if they ran bootstrap.sh) at `~/.claude/skills/meeting-todos/`. If for any reason it's missing, copy it now:

```bash
mkdir -p ~/.claude/skills/meeting-todos
cp -R ~/.claude/skills/ai-brain-starter/skills/meeting-todos/. ~/.claude/skills/meeting-todos/
```

Add routing to the user's CLAUDE.md:

```markdown
# meeting todos
- **meeting-todos** (`~/.claude/skills/meeting-todos/SKILL.md`) — extract action items from a meeting note and add them to to-do. Trigger: `/meeting-todos`
When the user types `/meeting-todos`, invoke the Skill tool with `skill: "meeting-todos"` before doing anything else.
```

### Design & Creative
Ask: "Do you use Canva, Figma, or any design tools?"
- "Connect Canva or Figma from connectors. I can search your designs, generate new ones from vault context, and pull brand assets."

### Project Management
Ask: "Do you use Linear, Notion, Asana, or any project tracker?"
- "If it's in the connectors list, connect it. If not, we can set up periodic imports."

Tell them: "You don't have to connect everything now. Start with email and calendar — those give the biggest boost. You can add more anytime."
