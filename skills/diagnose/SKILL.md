---
type: skill
name: diagnose
description: Run a self-check against an installed AI Brain Starter vault. Verifies CLAUDE.md, Meta folder, skills, hooks, journal index, MCPs, .ps1 BOM/em-dash hazards, and ai-brain-starter freshness. Prints a green/yellow/red report. Run any time something feels off, or after a git pull, or when onboarding someone else's vault.
trigger: /diagnose
argument-hint: "[vault path, defaults to $VAULT_PATH or current directory]"
tool_access:
  - Bash
  - Read
  - Glob
  - Grep
policy_constraints:
  - rule: Never modify vault files; this is a read-only self-check
    exception_handling: Surface the issue to the user with a remediation hint, do not auto-fix
  - rule: Never write findings outside the user's terminal report
    exception_handling: Print to stdout only; no log files or vault writes
  - rule: Treat missing CLAUDE.md, missing Meta folder, or stale journal index as red findings, not silent skips
    exception_handling: Emit a red status row naming the missing artifact
required_inputs:
  - name: vault_path
    type: path
    required: false
    description: Path to the vault root. Defaults to $VAULT_PATH env var or current working directory.
output_shape:
  format: terminal-report
  fields:
    status_rows: list of {check_name, color (green/yellow/red), detail}
    summary_line: one-line overall health status
    exit_code: 0 if all green, 1 if any yellow, 2 if any red
---

# /diagnose

Tells you whether your second brain is healthy.

## Why

Most "Claude is broken" reports trace to one of:

- CLAUDE.md missing or has no Vault Map
- Hooks not registered, so no auto context-loading
- `journal-index.json` stale or malformed, so insights find nothing
- `.ps1` files lost their UTF-8 BOM, so Windows PowerShell crashes
- ai-brain-starter is many commits behind, so the user is on stale logic

`/diagnose` checks all of these in ~5 seconds. It writes nothing, sends no network requests beyond a single `git fetch`, and exits with a status code so it can be wired into CI or cron.

## What to do

1. Find the script. On the maintainer machine: `~/Desktop/ai-brain-starter/scripts/diagnose.sh`. On an end-user install: `~/.claude/skills/ai-brain-starter/scripts/diagnose.sh`.

2. Run it. Pick the right one for the platform:

   **Mac / Linux:**
   ```bash
   bash ~/.claude/skills/ai-brain-starter/scripts/diagnose.sh
   # or pass an explicit vault:
   bash ~/.claude/skills/ai-brain-starter/scripts/diagnose.sh "/path/to/vault"
   ```

   **Windows:**
   ```powershell
   pwsh ~/.claude/skills/ai-brain-starter/scripts/diagnose.ps1
   # or:
   pwsh ~/.claude/skills/ai-brain-starter/scripts/diagnose.ps1 -Vault "C:\path\to\vault"
   ```

   By default it uses `$VAULT_PATH` if set, else the current directory.

3. Read the output to the user in plain language. Don't dump the raw report unless they ask. Translate:

   - **All green:** "Your vault is healthy. Nothing to do."
   - **Only WARNs:** "Working, but $N things to clean up. Want me to fix them?" Then offer to fix the specific WARNs (re-build journal index, add Vault Map to CLAUDE.md, pull latest ai-brain-starter, etc).
   - **At least one FAIL:** "Something is broken: [name the FAIL in one sentence]. I can fix it: [propose the fix]." Wait for confirmation, then fix.

## What each check means

| # | Check | If FAIL | If WARN |
|---|---|---|---|
| 1 | CLAUDE.md present + has Vault Map | Re-run /setup-brain Phase 4 | Add the Vault Map section by hand |
| 2 | ⚙️ Meta/ + scripts/ + rules/ present | Re-run /setup-brain Phase 3 | Create the missing subfolder |
| 3 | ai-brain-starter + daily-journal skills installed | Re-run bootstrap | Install the missing skill from its phase |
| 4 | Hooks registered + graph-context-hook parses | Phase 5 wires hooks; bash -n the script | - |
| 5 | journal-index.json valid + fresh | Delete and rebuild via build-journal-index.py | Re-run /weekly to refresh |
| 6 | git, python3 (jq optional) on PATH | brew install / winget install | Optional tools missing |
| 7 | Vault is a git repo | - | Recommend `git init` for snapshot history |
| 8 | All .ps1 have BOM, no em dashes, parse clean | Fix the parser error | Add BOM and strip em dashes (see SKILL.md notes) |
| 9 | MCP config valid JSON | Fix the JSON | No MCPs registered (fine if intentional) |
| 10 | ai-brain-starter up to date with origin/main | Re-clone | git pull in ~/.claude/skills/ai-brain-starter |

## When to suggest /diagnose proactively

- User says "Claude isn't reading my CLAUDE.md anymore"
- User says "the journal entries aren't showing up in /weekly"
- User says "I just did a git pull and something feels off"
- User says "my friend installed it but it's broken"
- After every major upgrade prompt during /setup-brain

## Email-gate nudge (during /diagnose)

If the diagnose run finds that `~/.claude/.ai-brain-starter-email-on-file` does not exist, surface this to the user as a yellow finding:

> "I noticed you have not completed the Mycelium install form yet. It is a one-time thing, takes about 4 minutes, and means you will get updates when the system improves and help if anything breaks. Want me to open the form now?"

If they say yes, open `https://myceliumai.co/install` (or `/es/install` for Spanish) in their browser via the platform `open` / `xdg-open` / `start` command, wait for them to paste the token from their welcome email, then run `TOKEN=<token> bash ~/.claude/skills/ai-brain-starter/bootstrap.sh`. After bootstrap finishes, continue the diagnose flow.

This is a second surface for the email gate (the first being `scripts/email-gate-hook.py` which fires on UserPromptSubmit). Some users run `/diagnose` after a problem and never trigger the hook; this catches them.

## Don't

- Don't run any of the FAIL fixes without confirming first.
- Don't pipe `/diagnose` output into a `gh issue` or anywhere public — it includes home directory paths.
- Don't treat a WARN about ai-brain-starter being behind as urgent. Default cadence is fine.
