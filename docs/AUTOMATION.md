---
name: automation
description: How the health stack auto-triggers without the user remembering commands
---

# Automation — health stack v0.5

The substrate's health stack has 41 tools, 5 skills, and 2 auto-trigger hooks. The point of the hooks is so the user doesn't need to remember the tools or the skills. Whenever they're in Claude Code at all, the chain fires.

This doc explains the auto-trigger chain, what fires when, and how to verify it's working.

## The chain

```
06:30 (any time) — User opens Claude Code
    │
    ▼
SessionStart hook fires
    │
    ▼
hooks/health-auto-sync.py
    │   Checks last Oura import age. If > 24h: pulls yesterday's data.
    │   Checks last Fitbit import age. If > 24h: pulls yesterday's data.
    │   Apple Health skipped (requires iOS interaction).
    │
    ▼
User types /journal (or similar) at any point in the session
    │
    ▼
Stop hook fires when /journal completes
    │
    ▼
hooks/coach-auto-prescribe-on-journal.py
    │   Reads <vault>/Meta/coach-profile.yaml.
    │   Checks if today's prescription exists. If not, fires
    │   health_coach_prescribe with the saved profile.
    │   Runs scripts/backfill-journal-body-context.py for yesterday only
    │   (appends Body track section below yesterday's verbatim journal).
    │
    ▼
If profile.calendar_drop=true AND google-workspace MCP connected:
    │   Drops today's workout to Google Calendar at preferred_workout_clock.
    │
    ▼
Done. Workout sits in calendar. Yesterday's journal has body context.
Nothing else for the user to remember.
```

## What auto-fires vs what stays manual

**Auto:**
- Wearable sync (Oura, Fitbit) — on every SessionStart, if data is > 24h stale
- Daily prescription — when user types /journal (or equivalent)
- Yesterday's body-track backfill — when user types /journal
- Calendar drop of today's workout — same trigger, if configured
- /weekly + /monthly insights body track — already auto-fires via section 0d in the insights skill
- health-context auto-fires inside /journal, /coaching, /panel, /patterns (existing wiring)

**Manual (by design — Bainbridge panel dissent integrated):**
- `/coach log` — logging RPE + lift actuals after a session. The body stays in the loop; the substrate never auto-logs completion.
- Apple Health re-export — requires iOS interaction, can't be triggered from desktop. The hookify nudge surfaces a reminder every 28 days.
- Lab import — manual CSV upload from patient portal. Hookify reminds when an out-of-range marker is > 90 days without a re-test.
- One-time backfill of the full year (`/backfill-journal-body-context`) — runs once per year-window, then daily backfill takes over.
- `/health-setup` for first-time install (vendor + OS picker) — manual because the user is doing OAuth flows + setting env vars.

## Failure modes + recovery

**1. Wearable API down at session start.** Hook catches exception, exits silently. Next session retries. No noise, no broken state.

**2. User skips /journal one day.** Tomorrow's /journal triggers the chain for two days at once (yesterday backfill + today prescription). No missed days.

**3. User doesn't open Claude Code for a week.** Next session pulls 7 days of wearable backfill in one shot. SessionStart hook handles ranges, not just single days.

**4. health-mcp not yet installed.** Hooks exit silently. Once `/health-setup` is run, hooks start firing.

**5. Coach profile not yet set.** Stop hook exits silently. Once `/coach profile` is run, hooks start firing.

**6. Calendar drop fails (google-workspace MCP not connected).** The prescription is still created in the DB and surfaces on next /coach today. The hook only TRIES the calendar drop; failure doesn't block.

## How to verify

Run `/health doctor` to see the freshness of every source, last prescription + completion, which hooks are installed, and any out-of-range labs needing attention. Color-coded green / yellow / red so you can scan in 30 seconds.

## How to install

`/health-setup` ends with an auto-wire step. Default: yes. The wizard:

1. Verifies `~/.claude/settings.json` exists.
2. Adds entries for:
   - SessionStart → `health-auto-sync.py`
   - Stop (matcher: `mcp__.*journal|daily-journal|journal`) → `coach-auto-prescribe-on-journal.py`
3. Validates the JSON parses cleanly before saving.
4. Reports "auto-trigger wired" with the rough trigger points.

If you said no during setup and want to wire them later, just say `/health-setup` again and pick the auto-wire step.

To remove the auto-trigger: edit `~/.claude/settings.json` and drop the two entries. Skills and tools keep working manually.

## Opt-in: scheduled tasks instead of hooks

If you prefer cron-style scheduling (machine on, network up, fires at fixed times regardless of whether you open Claude Code), you can wire scheduled tasks via the `/schedule` skill. Suggested cadence:

- `_health-daily-sync` — 06:00 daily, runs `health_import_oura(yesterday, yesterday)` + `health_import_fitbit(yesterday, yesterday)`
- `_coach-daily-prescription` — preferred_workout_clock - 30min, runs `/coach today`
- `_coach-weekly-plan` — Sundays at 18:00, runs `/coach week`

The hook path is preferred because it doesn't depend on the machine being on at a fixed time, but both can coexist (the substrate is idempotent on duplicate runs).

## Why this matters

A user who has to remember `/coach today` every morning will forget by day 4. A user whose workout appears in their calendar at 7am without them doing anything will train. Capability without trigger isn't deployed; it's a museum.

The Bainbridge dissent at the original panel (2026-05-10) was load-bearing: auto-trigger the ANALYSIS, never auto-trigger the ACTION. The substrate prepares the workout and surfaces it; you decide whether to do it. That's the line.
