# health-mcp

Apple Health MCP server for the ai-brain-starter substrate. Multi-mode ingestion (XML export, Simple Health Export CSV, Health Auto Export TCP-live), DuckDB query layer, open scoring algorithms, and vault-aware tools that pair with the daily-journal, coaching, advisory-panel, patterns, and insights skills.

## Why this exists

The substrate ships skills for daily journaling, coaching, advisory-panel synthesis, weekly insights. Each one would be more accurate if it knew how the user's body felt during the moments it analyzes. Apple Health holds that signal; nobody was bringing it into the substrate.

This MCP closes that gap. It pairs HRV, sleep, recovery, and workout data with the journal frontmatter (Floor tags, themes) so:

- **daily-journal** can prompt with "you slept 5h, HRV was 28ms vs your 42ms baseline; how did your body feel?"
- **patterns** can flag "low-Floor days correlate with low HRV (r = -0.42, n = 38)"
- **coaching** can surface "your last 7 sessions clustered on days with deep+REM under 60 minutes"
- **advisory-panel** can fold "today's recovery is -18 vs 7-day avg" into a deferral suggestion
- **insights** can include weekly recovery trend in the review

## Tools (15)

### Ingestion
- `health_import_xml(zip_or_xml_path, force=False)` — Apple Health export.zip
- `health_import_csv(folder_path, force=False)` — Simple Health Export CSVs
- `health_status()` — DB stats + last import + top metric types

### Query
- `health_schema()` — every record type with row count + date range
- `health_query(sql, max_rows=1000)` — read-only DuckDB SQL
- `health_metric_series(metric, start, end, aggregation)` — time series

### Analytics
- `health_workout_list(start, end, activity_type=None)` — workout sessions
- `health_sleep_summary(start, end)` — per-night stage breakdown
- `health_recovery_score(date)` — open algorithm, 0-100, components reported
- `health_sleep_score(date)` — 0-100 with duration / efficiency / REM% / deep%
- `health_strain_score(date)` — 0-21 Whoop-shape scale, log mapping

### Vault-aware (substrate differentiator)
- `health_journal_context(date)` — 24h roll-up for daily-journal
- `health_floor_correlation(metric, days, vault_root)` — Pearson r per Floor
- `health_coaching_context(start, end, theme, vault_root)` — recovery-vs-stress over a window
- `health_panel_context(date, vault_root)` — same-day snapshot for panel decisions
- `health_weekly_rollup(week_start)` — feeds /insights weekly review

### Live
- `health_live_query(metric, host, port, start, end)` — TCP query against Health Auto Export iOS app

## Install

```bash
cd services/health-mcp
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Register in your project `.mcp.json`:

```json
{
  "mcpServers": {
    "health": {
      "command": "python3",
      "args": ["-m", "main"],
      "env": {
        "HEALTH_MCP_DB": "~/.claude/health-mcp/health.duckdb"
      }
    }
  }
}
```

Restart Claude Code. `claude mcp list` should show `health: ✓ Connected`.

## First import

See [SETUP.md](SETUP.md) for getting the export off your iPhone. Three modes are supported; pick the one that fits.

```
# Mode A — Apple Health XML export (free, manual, universal)
health_import_xml("/path/to/apple_health_export.zip")

# Mode B — Simple Health Export CSV (free, manual)
health_import_csv("/path/to/simple_health_export_folder")

# Mode C — Health Auto Export TCP live (paid app, real-time)
health_live_query("heart_rate", host="192.168.1.42", port=9000)
```

## Pairs with these skills

- `ingest-health` — orchestrator that wraps the three import modes
- `health-context` — auto-fires on `daily-journal`, `coaching`, `panel`, `patterns`, `insights` invocations to inject health context

## Open scoring algorithms

All three scores are deterministic Python with weights and formulas documented inline in `scores.py`. They are directional, not diagnostic. Surface as guidance, never as medical advice.

| Score | Range | Inputs | Weights |
|---|---|---|---|
| Recovery | 0-100 | HRV (z-score vs 30-day) + RHR + sleep duration + sleep efficiency | 40/20/25/15 |
| Sleep | 0-100 | duration + efficiency + REM% + deep% | 40/25/20/15 |
| Strain | 0-21 | active/basal kcal ratio + HR-elevated min + workout min | log compression |

For research-grade scoring, plug in [open-wearables](https://github.com/the-momentum/open-wearables) for sleep_score and resilience_score (Q1 2026 release).

## Privacy

- Local-only by design. DuckDB at `~/.claude/health-mcp/health.duckdb`.
- No cloud sync, no telemetry.
- Vault-aware tools READ vault frontmatter; never write.
- Live mode uses local Wi-Fi only; no internet round-trip.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Synthetic fixtures only. No real health data is committed.

## License

MIT. See [LICENSE](LICENSE).
