# health-mcp

**Local-only. Your health data never leaves your machine. The scores this MCP produces are directional, not diagnostic.**

Apple Health MCP server for the ai-brain-starter substrate. Brings biometric, cycle, lab, sleep, longevity, symptom, and ECG data into the substrate so the daily-journal, coaching, advisory-panel, patterns, and insights skills can read body context alongside the emotional track.

32 tools across 8 categories. Three Apple Health ingestion modes plus manual lab CSV import. Open scoring algorithms with weights documented inline. DuckDB storage at `~/.claude/health-mcp/health.duckdb`.

## What changed in v0.2

Built per advisory-panel synthesis 2026-05-10. The substrate now covers the full HealthKit surface: 108 quantity types (every Apple Health metric), 47 symptom categories, 14 cycle/reproductive types, ECG, and iOS 17+ State of Mind mood logs. New tools for cycle phase awareness, sleep regularity, longevity panel, somatic pre-check before coaching, nutrition under-fuel detection, year-over-year long-window comparison, body-literacy prompts, and symptom-vs-Floor correlation. Lab CSV import for the clinical chemistry Apple Health doesn't capture (ApoB, fasting insulin, hs-CRP, full thyroid, sex hormones).

## Why this exists

The substrate ships skills for daily journaling, coaching, advisory-panel synthesis, weekly insights. Each one is more accurate when it knows how the body felt during the moments it analyzes. The vault-aware tools READ journal frontmatter (Floor tags) and pair them with biometrics. No other Apple Health MCP knows about Obsidian Floor frontmatter; that pairing is the substrate's differentiator.

## Tools (32)

### Ingestion
- `health_import_xml(zip_or_xml_path, force=False)` — Apple Health export.zip
- `health_import_csv(folder_path, force=False)` — Simple Health Export CSV folder
- `health_import_labs(csv_path, lab_format='auto', force=False)` — LabCorp / Quest / Function Health / generic CSV
- `health_status()` — DB stats per table + last import + top types
- `health_recommended_labs()` — recommended-panel reference list with WHY for each marker

### Query
- `health_schema()` — every record type with row count + date range
- `health_query(sql, max_rows=1000)` — read-only DuckDB SQL passthrough
- `health_metric_series(metric, start, end, aggregation)` — time series

### Analytics
- `health_workout_list(start, end, activity_type)` — workouts
- `health_sleep_summary(start, end)` — per-night sleep stages
- `health_recovery_score(date)` — 0-100, HRV + RHR + sleep
- `health_sleep_score(date)` — 0-100, duration + efficiency + REM% + deep%
- `health_strain_score(date)` — 0-21, log-compressed activity load

### Surface
- `health_longevity_panel(date)` — VO2Max, walking speed, walking steadiness, lean mass, body fat, Zone 2 minutes
- `health_sleep_regularity(start, end)` — bed/wake variance + latency + nap detection
- `health_somatic_state(date, lookback_min)` — recent HR/HRV volatility + body_says_slow_down boolean for coaching pre-check
- `health_nutrition_summary(start, end)` — daily macros + under-fuel detector
- `health_long_window(metric, years)` — year-over-year + persistent-asymmetry detection
- `health_audio_exposure(start, end, threshold_db)` — environmental + headphone audio above threshold
- `health_lab_panel(date, lookback_days)` — most recent lab values per marker

### Cycle
- `health_cycle_context(date)` — current phase + cycle day + length variance + irregularity flag
- `health_phase_tagged_metric(metric, start, end)` — daily metric series with cycle phase per day
- `health_phase_means(metric, days)` — metric segmented by cycle phase

### Symptoms / ECG / State of mind
- `health_symptom_timeline(start, end, symptom_type)` — symptom log entries
- `health_ecg_list(start, end)` — ECG entries with classification
- `health_state_of_mind_timeline(start, end)` — iOS 17+ mood logs

### Vault-aware (substrate differentiator)
- `health_journal_context(date, voice_profile)` — 24h roll-up rendered in 'clinical' / 'warm' / 'curious' register
- `health_journal_body_question(date)` — context-aware embodiment prompt (returns a question, not a number)
- `health_floor_correlation(metric, days, vault_root)` — Pearson r vs floor_level + per-floor means
- `health_symptom_correlation(symptom_type, days, vault_root)` — symptom incidence per Floor
- `health_coaching_context(start, end, theme, vault_root)` — recovery-vs-stress + Floor distribution
- `health_panel_context(date, vault_root)` — same-day snapshot for panel decisions
- `health_weekly_rollup(week_start)` — feeds /insights weekly review
- `health_long_window_with_journal(metric, years, vault_root)` — YoY + Floor distribution by month

### Live
- `health_live_query(metric, host, port, start, end)` — Health Auto Export TCP

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
      "env": {"HEALTH_MCP_DB": "~/.claude/health-mcp/health.duckdb"}
    }
  }
}
```

Restart Claude Code. `claude mcp list` should show `health: ✓ Connected`.

## First-run path (free + universal)

iOS Health > Profile > Export All Health Data > export.zip > AirDrop to your computer > run `health_import_xml('/path/to/export.zip')`. Idempotent: re-runs on the same SHA skip unless `force=True`.

The streaming parser handles 1M+ record exports without memory pressure.

## Three ingestion modes

| Mode | Cost | Use case |
|---|---|---|
| Apple Health XML export.zip | **Free** | Universal, works for any iPhone user, manual snapshot |
| Simple Health Export CSV | **Free** ([App Store](https://apps.apple.com/app/simple-health-export-csv)) | CSV per metric, manual snapshot |
| Health Auto Export TCP | **Paid** ($5/mo, [App Store](https://apps.apple.com/app/health-auto-export-json-csv)) | Real-time queries over local Wi-Fi |

See [SETUP.md](SETUP.md) for the full step-by-step on each mode.

## Recommended labs (and why)

`health_recommended_labs()` returns the substrate's lab-panel reference list. Each entry has marker + category + why + suggested frequency + cost band.

The why-it-matters anchor for substrate users:

- **Apple Health captures the visible 20% of health.** Steps, heart rate, sleep, exercise minutes. It does not capture the chemistry that drives chronic disease.
- **Recovery score has a blind spot.** Without fasting insulin and hs-CRP, the recovery formula recommends "rest more" for what is actually subclinical hypothyroidism, chronic inflammation, or metabolic syndrome. The labs change the prescription.
- **The full panel runs ~$200-400 annually at LabCorp / Quest direct-pay** (no insurance needed in most US states). Function Health bundles the workflow at a higher price point. Order direct, get it drawn at any commercial lab, export the result, import here.

The 16-marker reference panel: ApoB, Lp(a), hs-CRP, Fasting Insulin, HbA1c, Fasting Glucose, Triglyceride/HDL ratio, Full thyroid (TSH + free T3 + free T4 + reverse T3 + TPO antibodies), Vitamin D 25-OH, Ferritin, B12 + Folate + Homocysteine, Magnesium RBC, Sex hormones (Estradiol + Progesterone + Testosterone + DHEA-S + SHBG), Cortisol (4-point salivary), CMP, CBC.

## Open scoring algorithms

All scores are deterministic Python with weights documented inline in `scores.py`. Directional, not diagnostic. Surface as guidance, never as medical advice.

| Score | Range | Inputs | Weights |
|---|---|---|---|
| Recovery | 0-100 | HRV (z-score vs 30-day) + RHR + sleep duration + sleep efficiency | 40/20/25/15 |
| Sleep | 0-100 | duration + efficiency + REM% + deep% | 40/25/20/15 |
| Strain | 0-21 | active/basal kcal ratio + HR-elevated min + workout min | log compression |
| Sleep regularity | 0-100 | bed-time stdev + wake-time stdev + duration stdev | 40/40/20 |

The longevity panel surfaces VO2Max + walking speed + walking steadiness + lean mass + Zone 2 minutes per Attia's *Outlive* framing.

For research-grade scoring, [open-wearables](https://github.com/the-momentum/open-wearables) ships sleep_score and resilience_score (Q1 2026) — a heavier multi-wearable platform. health-mcp is the lightweight Apple-Health-focused alternative.

## Pairs with these skills

- `ingest-health` — orchestrator that wraps the three import modes
- `health-context` — auto-fires on `daily-journal`, `coaching`, `panel`, `patterns`, `insights` invocations to inject biometric context

## Privacy

- Local-only by design. DuckDB at `~/.claude/health-mcp/health.duckdb`. No cloud sync, no telemetry.
- Vault-aware tools READ journal frontmatter; never write.
- Live mode uses local Wi-Fi only; no internet round-trip.
- `*.duckdb` is in `.gitignore`. Never commit your health DB.
- Lab CSV imports stay local. The substrate never sends any health or lab data to a third party.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

41 tests, synthetic fixtures only. No real health data is committed.

## License

MIT. See [LICENSE](LICENSE).
