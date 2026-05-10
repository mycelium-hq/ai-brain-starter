# health-mcp setup

Three ingestion modes. Pick the one that fits your data flow.

## Mode A: Apple Health XML export (free, manual, universal)

The most universal path. Works for anyone with an iPhone, no third-party app needed.

1. On your iPhone, open the Health app
2. Tap your profile picture (top right)
3. Scroll to the bottom and tap **Export All Health Data**
4. Wait 1-3 minutes while iOS bundles the export. You'll get an `export.zip`
5. AirDrop or share the zip to your computer
6. Run:

   ```
   health_import_xml("/path/to/export.zip")
   ```

Idempotent: re-running on the same zip returns `skipped: true`. Pass `force=True` to re-import. Typical exports are 50-500 MB; the streaming parser handles 1M+ records without memory pressure.

## Mode B: Simple Health Export CSV (free, manual)

If you prefer CSV per-metric files. Good for users who want to inspect the raw data first.

1. Install [Simple Health Export](https://apps.apple.com/app/simple-health-export-csv) on your iPhone (free)
2. In the app, select the metric types you want to export
3. Export to Files / iCloud Drive / AirDrop
4. Drop the folder onto your computer
5. Run:

   ```
   health_import_csv("/path/to/simple_health_export_folder")
   ```

The folder should contain `HKQuantityTypeIdentifier*.csv` and/or `HKCategoryTypeIdentifier*.csv` files.

## Mode C: Health Auto Export TCP live (paid iOS app, real-time)

Real-time access without manual exports. Costs ~$5/mo on iOS but no manual export step.

1. Install [Health Auto Export](https://apps.apple.com/app/health-auto-export-json-csv) on your iPhone
2. Subscribe to the Premium tier
3. In the app, enable **TCP Server** (Settings → Integrations)
4. Note the iPhone's local IP (Settings → Wi-Fi → tap network → IP Address) and the TCP port (default 9000)
5. Keep the iPhone on the same Wi-Fi as your computer
6. Test:

   ```
   health_live_query("heart_rate", host="192.168.1.42", port=9000, start="2026-05-09", end="2026-05-10")
   ```

This mode is v1 shim — the call returns the raw Health Auto Export response. v0.2 will normalize into the same DuckDB schema as Modes A/B.

## After import

Sanity-check:

```
health_status()
# {records_count: 1234567, workouts_count: 482, sleep_count: 9876, ...}

health_schema()
# [{type: "HKQuantityTypeIdentifierStepCount", count: 458291, first: "2018-09-01", last: "2026-05-10"}, ...]

health_recovery_score("2026-05-09")
# {score: 72, components: {hrv: 0.65, rhr: 0.80, sleep_duration: 0.85, sleep_efficiency: 0.90}, confidence: "high"}
```

## Wiring the vault-aware tools

To get Floor correlation working, your daily journal frontmatter needs:

```yaml
---
type: journal
creationDate: 2026-05-09
floor_level: 14    # numeric, on a 1-N consciousness scale
floor: Acceptance  # name (optional, used for per-floor breakdowns)
---
```

If you only have `floor` (string) and not `floor_level` (numeric), the correlation tool returns per-floor means instead of a single Pearson r. Both are useful.

## Troubleshooting

- **"No export.xml found inside zip"** — Apple's export.zip should contain `apple_health_export/export.xml`. Some third-party converters strip the inner directory; if so, re-export from the iOS Health app directly.
- **"could not reach Health Auto Export"** — iPhone is asleep, the app isn't running, or it's on a different Wi-Fi. The iOS app puts the TCP server to sleep when backgrounded for too long; re-open it before each query session.
- **Empty recovery score** — needs HRV + RHR + sleep data. Apple Watch records HRV during sleep; without an Apple Watch, recovery score will return `confidence: "low"` based on whatever inputs are present.
- **DuckDB locked** — only one writer at a time. If a long ingest is in flight, queries queue.

## Privacy disclaimer

This server stores your health data in a local DuckDB file. Treat it as you would any other file containing personal medical information: don't commit it to git, don't sync it to cloud storage, and don't share the DB file with anyone.

The scores reported are directional, not diagnostic. Use them as inputs to journaling and self-reflection, not as substitutes for medical advice.
