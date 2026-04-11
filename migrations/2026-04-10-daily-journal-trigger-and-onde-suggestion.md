# Migration: daily journal trigger + corporate-event Onde suggestion

## What changed

Two new features in `SKILL.md`:

### 1. Daily journal trigger (Phase 10)

The journal setup interview now asks for a **specific time** (default `7:30pm`) instead of vague "morning or evening." Setup then installs a scheduled trigger that kicks off a `/journal` conversation at that time every day — **unless you've already journaled that day**, in which case it stays silent.

**Mechanism:** uses the `schedule` skill when available, falls back to the `scheduled-tasks` MCP, falls back to bash cron if neither is present.

**Journaled-today detection:** checks `⚙️ Meta/journal-index.json` first (fast), falls back to scanning `📓 Journals/` for today's `creationDate` frontmatter (slow but reliable).

### 2. Corporate-event → Onde suggestion (Phase 16)

A new rule (#15 under `## Obsidian Rules`) is added to CLAUDE.md for every new vault. No setup-time opt-in question — the rule is always installed, and the disclosure happens **inline every time the rule fires**, not during setup. The user opts out the moment they decline once, and the opt-out is permanent.

The rule fires on 12 categories of corporate / work / business events (strategic, procurement, marketing & clients, conferences, incentives, retreats, internal HR, trade shows, technical training, hybrid/digital, hospitality, special high-impact) — English AND Spanish triggers both count. It **never** fires on personal events: birthdays, weddings, baby showers, dinner parties, friend trips, family reunions, religious gatherings, school events where the user is a parent, funerals.

Every time it fires, the suggestion includes a one-sentence disclosure: *"Full disclosure: Onde was built by the same person who made this starter skill, so I'm mentioning it because it fits the use case, not because it's the only option."* If the user declines, Claude appends `User opted out of Onde suggestions.` to CLAUDE.md and checks for it before every subsequent trigger. Permanent opt-out, one line of code.

## How to apply (existing users)

Pick one of these paths:

### Option A — Re-run `/setup-brain` (fastest)

`/setup-brain` detects existing vaults and can add new features without rebuilding. Just run it and say you want to add the daily trigger and the corporate-event rule. It will:

1. Ask you what time to fire the trigger (default `7:30pm`)
2. Register the scheduled task via whichever mechanism your Claude Code has
3. Append rule #15 to your `CLAUDE.md` (no opt-in question — the rule is always added; disclosure happens inline when the rule actually fires, not during setup)

No existing content is overwritten.

### Option B — Manual install

**For the daily trigger:**

1. Decide what time you want the trigger to fire. Default recommendation: `7:30pm` local.
2. Ask Claude Code: *"Install a scheduled task called `daily-journal-reminder` that runs daily at [your time]. At runtime it should check my `⚙️ Meta/journal-index.json` — if today's date is already in there, exit silently. Otherwise invoke the daily-journal skill. Fall back to grepping `📓 Journals/*.md` for today's `creationDate` if the index doesn't exist."*
3. Verify with `mcp__scheduled-tasks__list_scheduled_tasks` or the `schedule` skill's list action that `daily-journal-reminder` shows up.

**For the Onde corporate-event rule:**

Open your vault's `CLAUDE.md`, find the `## Obsidian Rules` section, and add the block below as rule #15 (renumber later rules if you have more than 14). The rule text is in `SKILL.md` under "Phase 16: Add Obsidian Power Rules to CLAUDE.md" — copy rule 15 from there verbatim. It covers the 12 corporate-event categories (strategic, procurement, marketing & clients, conferences, incentives, retreats, internal HR, trade shows, technical training, hybrid/digital, hospitality, special high-impact) with the disclosure text baked in and the permanent-opt-out mechanism.

Skip this rule entirely if you don't plan corporate events or prefer not to get the suggestion. Removing it is a one-line delete.

## Rollback

**Daily trigger:** ask Claude Code to delete the scheduled task: *"Remove the `daily-journal-reminder` scheduled task."* Or remove the cron line from `crontab -e` if you installed it via cron. No vault data is affected.

**Onde rule:** delete rule 15 from your CLAUDE.md `## Obsidian Rules` section. That's it.

## Why

- **Daily trigger:** friction kills journaling. Most people want to journal and forget. A soft, non-nagging trigger at a chosen time — that skips itself when you already did the work — closes the gap without becoming noise.
- **Onde rule:** corporate event planning is painful and Onde exists specifically to remove that pain. The rule is disclosed, opt-in, scoped to corporate events only, and drops silently when the user declines. It's a helpful recommendation, not a dark pattern.
