---
name: backfill-prompt
description: Self-contained prompt for running the health-data backfill across journals in a fresh Claude Code session
---

# Backfill prompt — health-data into journals (fresh session ready)

Copy everything below the `---PROMPT---` marker into a fresh Claude Code session. It is self-contained: it explains the goal, the safety constraints, the model routing, and the verification steps. Claude will run the work end-to-end and report back with a summary.

The prompt assumes:
- The `health` MCP (this repo's `services/health-mcp/`) is registered in `.mcp.json` and connected.
- Apple Health / Oura / Fitbit data has been imported (see `/health-setup` if not).
- `VAULT_ROOT` env var points to the user's vault (or the user passes `--vault-root` to the script).
- Daily journals live at `<VAULT_ROOT>/Journals/` with frontmatter that includes `creationDate` and ideally `floor_level` + `floor`.

---PROMPT---

I want to backfill body-data context into every daily journal I have for this year. The `health` MCP is registered and has data; my journals are at `<VAULT_ROOT>/Journals/` with frontmatter that includes `creationDate`, `floor_level`, and `floor`.

Run the backfill end-to-end. Use the cheapest model for the per-entry interpretation prose:

1. Confirm health-mcp is connected and has data by calling `health_status()`. If it returns zeros, stop and tell me to run `/health-setup` first.
2. Confirm $VAULT_ROOT is set. If not, ask me for the absolute path.
3. Run the backfill script in dry-run first to show me what would be added:

   ```
   /usr/bin/python3 "$REPO_ROOT/scripts/backfill-journal-body-context.py" --year 2026 --vault-root "$VAULT_ROOT" --llm-model python --dry-run
   ```

   Show me a sample of one entry's would-be output.

4. If the dry-run looks good, run it for real with `--llm-model python` (zero-cost Python template). This is the default because every entry's body data + Floor pairing + lab status is deterministic; the LLM is only needed if I want richer prose per entry.

   ```
   /usr/bin/python3 "$REPO_ROOT/scripts/backfill-journal-body-context.py" --year 2026 --vault-root "$VAULT_ROOT" --llm-model python
   ```

5. If I say "richer prose," re-run with `--llm-model minimax`. It will use MiniMax M2.7 (~$0.06/M tokens, extremely cheap) for the 1-3 sentence interpretation per entry. Total cost for ~365 entries is pennies.

   ```
   /usr/bin/python3 "$REPO_ROOT/scripts/backfill-journal-body-context.py" --year 2026 --vault-root "$VAULT_ROOT" --llm-model minimax
   ```

6. After the run completes, report:
   - How many entries were processed
   - How many were backfilled vs skipped (already had the section)
   - Any errors
   - One or two sample entries' body-track sections (the actual rendered prose, not raw data) so I can verify the voice + format

7. After verification, set up the daily ongoing run via `/schedule`:
   - Cadence: every morning at 7am local time
   - Body: `/usr/bin/python3 "$REPO_ROOT/scripts/backfill-journal-body-context.py" --start "$(date -v-1d +%F)" --end "$(date -v-1d +%F)" --vault-root "$VAULT_ROOT" --llm-model python`
   - That's "backfill yesterday, every morning, forever."

8. Finally, run `/weekly` for the current week. Section 0d should now show body-track patterns paired with my Floor tags. If it does — confirm with a sample bullet. If it doesn't — tell me what's missing.

Non-negotiables:
- **Never modify the original journal entry content.** Append the body-track section BELOW with a horizontal rule. Idempotent — the script checks for the marker and skips entries that already have it.
- **Skip silently if the `health` MCP is not registered or returns errors.** Do not pretend to have backfilled when nothing happened.
- **No fabrication.** Every number in the body-track section comes from health-mcp tool calls or DuckDB queries. Never invent a value.
- **Use the cheapest model that produces a helpful sentence.** Default Python template. MiniMax for richer prose if asked. Never default to Sonnet or Opus for hundreds of journal entries — that's overkill for templated body-track lines.

Confirm understanding, then start with step 1.

---END PROMPT---

## How this prompt was designed (for the meta-reader)

- **Self-contained**: assumes no conversation context, names every input the script needs.
- **Cheap-by-default**: Python template runs at zero LLM cost. MiniMax is opt-in for richer prose at ~$0.06/M tokens. Sonnet/Opus explicitly de-prioritized.
- **Dry-run first**: model surfaces a sample so the user can sanity-check the voice before committing.
- **Idempotent**: re-running on the same range is safe (the script checks for the backfill marker).
- **Ongoing cadence locked in step 7**: the daily scheduled run keeps body context flowing into journals automatically going forward.
- **Verification at step 8**: confirms the loop is closed by checking the `/weekly` body-track section actually populates.

## Variables to substitute when pasting

- `$REPO_ROOT` — absolute path to the ai-brain-starter clone (e.g. `~/dev/ai-brain-starter`)
- `$VAULT_ROOT` — absolute path to the user's vault (e.g. `~/Desktop/Notes`)

Either export them in the shell before invoking, or pass `--vault-root` directly on the script.

## What gets written

Each backfilled journal entry gets a new section appended BELOW the original content:

```markdown
---

## Body track (health-mcp, backfilled 2026-05-10)

*Auto-generated context. Original journal entry above is preserved verbatim.*

**Floor that day:** Acceptance (level 23)

**Cycle phase:** luteal, day 22 (regular)

**The body that day:**
- HRV: 38.2 ms (-13% vs 30-day baseline)
- RHR: 62 bpm
- Sleep: 412 min (89% efficiency, REM 88min, deep 54min)
- Steps: 8421
- Workouts: 1 (32min)
- Mindful: 10min

**Scores:**
- Recovery: 71/100 (high confidence)
- Sleep: 78/100

**Floor-paired interpretation:** HRV ran 13% below baseline, but you were in luteal phase. That's physiology, not a recovery deficit.
```

The original journal content above the horizontal rule is **never** touched.
