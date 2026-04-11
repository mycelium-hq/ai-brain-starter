# Session start — daily AI brain setup update check

At the start of every session, after loading the usual context (CLAUDE.md, Last Session.md, Current Priorities.md), do a quick **once-per-day** check for updates to the AI brain setup itself. The user is non-technical and doesn't run terminal commands — you do this for them, and you translate the result into plain English.

## How to run the check

Run this command quietly (don't show output to the user yet):

**Mac / Linux:**
```bash
bash ~/.claude/skills/ai-brain-starter/scripts/update-check.sh
```

**Windows (PowerShell):**
```powershell
powershell -File "$env:USERPROFILE\.claude\skills\ai-brain-starter\scripts\update-check.ps1"
```

The script outputs one of four statuses: `UP_TO_DATE`, `SKIPPED_TODAY`, `BEHIND`, or `ERROR`.

## How to handle each status

### `SKIPPED_TODAY`

Already checked today. Do nothing. Don't mention it to the user.

### `UP_TO_DATE`

Their setup is current. Do nothing. Don't mention it to the user — they don't need a "you're up to date" message every day.

### `ERROR`

Something went wrong (network down, repo missing, etc.). The script's `REASON:` line tells you what. **Do not surface this to the user unless it's recurring.** A one-time fetch failure is normal (their wifi might be flaky); a persistent failure means their setup is broken and you should help them fix it.

### `BEHIND`

This is the interesting case. The script outputs:
- `COMMITS_BEHIND: <number>` — how many updates they're missing
- `---CHANGELOG_NEW---` block — the raw CHANGELOG entries since their current version, in markdown

**Translate the CHANGELOG entries into plain English.** The CHANGELOG is written for humans but uses some technical phrasing — "Phase 0", "MCP", "skills", "scripts", etc. Strip the jargon. Focus on what the user gets:

- **Skip:** version numbers, file paths, git commits, code snippets, install commands
- **Keep:** user-facing benefits (new tools, faster workflows, fixed bugs that affected them, new features)
- **Tone:** warm and conversational, not a release notes dump

**Then say to the user, in their primary language:**

> "Hey, just a heads up — your AI brain setup has an update available. Here's what's new:
>
> [1–4 plain-English bullets summarizing the new features and fixes from the CHANGELOG slice. Pick the 4 most user-relevant. Skip the technical ones.]
>
> Want me to install it? It takes about a minute and it's safe — I just run a script that updates everything automatically. Or I can hold off until later if you're in the middle of something."

**If they say yes:**

Run the bootstrap, which is idempotent and only installs what's missing:

**Mac / Linux:**
```bash
bash ~/.claude/skills/ai-brain-starter/bootstrap.sh
```

**Windows (PowerShell):**
```powershell
powershell -File "$env:USERPROFILE\.claude\skills\ai-brain-starter\bootstrap.ps1"
```

When the bootstrap finishes, parse its verification block. If everything passed, tell the user:

> "Done. Your setup is now up to date. [If anything visible changed, mention it: 'You should see the new /[skill-name] command available in this session.']"

If the verification block reported failures (red ✗ markers), tell the user EXACTLY which items failed and offer to retry. **Never silently ignore failures** — that's how broken setups get baked in for weeks.

**If they say no / not now:**

Don't run the bootstrap. Just say: "No problem. I'll check again tomorrow." The script already wrote today's date to the cooldown file, so you won't ask again until tomorrow.

## What to do if the check command itself isn't installed

If `~/.claude/skills/ai-brain-starter/scripts/update-check.sh` doesn't exist, the user is on a very old version. Tell them: "Heads up — your AI brain setup is from before automatic updates were added. Want me to do a one-time refresh so future updates work automatically?" If yes, run the bootstrap (which will pull the latest and create the update-check script).

## Why this rule matters

Users on this setup are non-technical. They will never run `git pull` themselves. Without this rule, they would stay on whatever version they first installed forever — missing every bug fix, every new tool, every workflow improvement. The rule makes "you're always on the latest" the default without ever asking the user to think about it.
