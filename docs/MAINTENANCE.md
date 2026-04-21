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

## Scheduled Tasks

Set these up as Claude Code scheduled tasks for hands-off maintenance:

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
