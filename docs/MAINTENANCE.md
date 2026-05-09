# Vault Maintenance

Automated hygiene checks to keep your vault clean over time. These complement the one-time setup from `bootstrap.sh` with ongoing maintenance.

## Scripts

### vault_maintenance.py

Monthly scan that checks 7 categories of vault hygiene issues:

- **Inbox overdue** - files sitting in Inbox/ longer than 7 days
- **Naming issues** - filenames over 60 chars or starting with lowercase (likely un-renamed imports)
- **Stray binaries** - images, PDFs, and docs outside designated folders
- **Backup accumulation** - .bak and .backup_ files scattered across the vault
- **Empty folders** - folders with 0 files
- **Large folders** - any folder with 500+ files (warning threshold)
- **Graphify backups** - graph.json.backup_* count (target: 3 or fewer)

```bash
python3 scripts/vault_maintenance.py --vault-root /path/to/vault
```

Output: a Markdown report at `Meta/Maintenance Report.md` (auto-detects emoji-prefixed Meta folder).

Options:
- `--binary-allowed Media Pics Archive` - override which folders are allowed to contain binary files

### rotate_graphify_backups.py

Keeps the N most recent graphify backups and deletes the rest. Also cleans .bak files older than N days.

```bash
python3 scripts/rotate_graphify_backups.py --vault-root /path/to/vault
python3 scripts/rotate_graphify_backups.py --vault-root /path/to/vault --keep 5 --bak-max-age 14
```

### rotate-last-session.py

Keeps `Last Session.md` lean by archiving older sessions to monthly files. `Last Session.md` is read on every UserPromptSubmit, so every stale session in it pays a token tax on every prompt.

```bash
python3 scripts/rotate-last-session.py --vault-root /path/to/vault          # keep last 3 (default)
python3 scripts/rotate-last-session.py --vault-root /path/to/vault --keep 1 # keep only the newest
python3 scripts/rotate-last-session.py --vault-root /path/to/vault --dry-run
```

### decision-outcome-check.py

Walks the Decision Log and surfaces decisions older than N days (default 30) with a blank `Outcome:` field. A decision log without outcomes can't teach you about your own patterns. Run weekly or wire into a scheduled task.

```bash
python3 scripts/decision-outcome-check.py --vault-root /path/to/vault           # default 30 days
python3 scripts/decision-outcome-check.py --vault-root /path/to/vault --days 14 # more aggressive
python3 scripts/decision-outcome-check.py --vault-root /path/to/vault --dry-run
```

## Scheduled Tasks

Set these up as Claude Code scheduled tasks for hands-off maintenance:

### Naming convention: prefix cron-only tasks with `_`

Scheduled tasks live in `~/.claude/scheduled-tasks/<name>/SKILL.md`. Claude Code's slash autocomplete registers these alongside `~/.claude/skills/` entries, so a user typing `/` sees both real skills and cron-triggered tasks in the same list. That is confusing when a task shares a stem with a real skill (e.g., `daily-journal` the cron-style task vs `journal` the conversational skill).

Workaround until upstream supports a `cron_only: true` frontmatter flag (tracked in [anthropics/claude-code#57508](https://github.com/anthropics/claude-code/issues/57508)): name your scheduled tasks with a leading underscore so they sort to the bottom of autocomplete and read as cron-only at a glance.

| Bad | Good |
|---|---|
| `daily-journal` | `_daily-journal-cron` |
| `graphify-weekly-check` | `_graphify-weekly-cron` |
| `monthly-token-optimization` | `_monthly-token-cron` |

Edit the existing task by renaming the directory and updating the `name:` field in its `SKILL.md` frontmatter to match. `/diagnose` will warn on any scheduled task that does not follow this convention or that collides with an installed skill name.

### Monthly Vault Maintenance (recommended)
- **Schedule:** 1st of every month, 9am
- **Cron:** `0 9 1 * *`
- **Prompt:** "Run the vault maintenance scan. Execute: python3 '{vault}/Meta/scripts/vault_maintenance.py' --vault-root '{vault}'. Read the generated Maintenance Report and summarize findings."

### Quarterly Vault Audit (optional)
- **Schedule:** 1st of Jan/Apr/Jul/Oct, 10am
- **Cron:** `0 10 1 1,4,7,10 *`
- **Prompt:** See [QUARTERLY-RUNBOOK.md](QUARTERLY-RUNBOOK.md) — a 10-step runbook that refreshes About Me, vault map counts, domain summaries, CRM spot checks, wikilink reference, and trend files. Goes deeper than the monthly scan. Paste the runbook body into your scheduled task prompt.

### Weekly Graphify Backup Rotation (recommended if using graphify)
- **Schedule:** Sundays, 3am
- **Cron:** `0 3 * * 0`
- **Prompt:** "Run graphify backup rotation. Execute: python3 '{vault}/Meta/scripts/rotate_graphify_backups.py' --vault-root '{vault}'. Report results."

## The Inbox Pattern

Create an `Inbox/` folder at your vault root as a quick-capture landing zone. The rule: nothing stays there longer than 7 days. The monthly maintenance scan flags overdue items.

This prevents the "junk drawer" problem where notes pile up in random folders because you didn't have time to file them properly. Everything enters through Inbox, then gets filed to its permanent home within a week.

Add this to your vault's obsidian rules:
> **Inbox zero.** Inbox/ is the quick-capture landing zone. Nothing stays there longer than 7 days. The monthly maintenance scan flags overdue items. When filing out, move in Obsidian UI so wikilinks auto-update.
