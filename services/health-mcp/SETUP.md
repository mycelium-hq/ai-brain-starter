# health-mcp setup

**Local-only. Your health data never leaves your machine. Every score is directional, not diagnostic.**

Three Apple Health ingestion modes plus optional manual lab CSV import. Pick the modes that fit your data flow.

## Mode A: Apple Health XML export — free, manual, universal

Works for any iPhone user. No third-party app, no subscription.

1. On your iPhone, open the Health app
2. Tap your profile picture (top right)
3. Scroll to the bottom and tap **Export All Health Data**
4. Wait 1-3 minutes while iOS bundles the export. You will get an `export.zip`
5. AirDrop or share the zip to your computer
6. Run:

   ```
   health_import_xml("/path/to/export.zip")
   ```

Idempotent: re-running on the same zip returns `skipped: true`. Pass `force=True` to re-import. Typical exports are 50-500 MB; the streaming parser handles 1M+ records without memory pressure.

What v0.2 imports from your export:
- 108 quantity types (steps, heart rate, HRV, RHR, VO2Max, sleeping wrist temperature, blood oxygen, body temperature, body mass, lean mass, walking speed, walking steadiness, all dietary intake categories, audio exposure, time in daylight, etc.)
- 14 cycle / reproductive types (menstrual flow, cervical mucus, ovulation tests, pregnancy, contraceptive, lactation, sexual activity)
- 47 symptom + cardio-event + sensory-event types (headache, bloating, fatigue, hot flashes, night sweats, lower back pain, pelvic pain, mood changes, breast pain, irregular heart rhythm event, low cardio fitness event, etc.)
- ECG records (sinus rhythm, AFib, inconclusive)
- iOS 17+ State of Mind mood logs (valence + labels + associations)
- Sleep stage segments (REM / deep / core / awake / in-bed)
- Workout sessions (80+ activity types)
- Mindful sessions

## Mode B: Simple Health Export CSV — free, manual

Free iOS app. Useful when you want to inspect raw CSVs first.

1. Install [Simple Health Export](https://apps.apple.com/app/simple-health-export-csv) on your iPhone (free)
2. In the app, select the metric types to export
3. Export to Files / iCloud Drive / AirDrop
4. Drop the folder onto your computer
5. Run:

   ```
   health_import_csv("/path/to/simple_health_export_folder")
   ```

The folder should contain `HKQuantityTypeIdentifier*.csv` and/or `HKCategoryTypeIdentifier*.csv` files.

## Mode C: Health Auto Export TCP — paid iOS app, real-time

Costs ~$5/mo on iOS. Trade-off: real-time access without manual exports.

1. Install [Health Auto Export](https://apps.apple.com/app/health-auto-export-json-csv) on your iPhone
2. Subscribe to the Premium tier
3. In the app, enable **TCP Server** (Settings > Integrations)
4. Note the iPhone's local IP and the TCP port (default 9000)
5. Keep the iPhone on the same Wi-Fi as your computer
6. Test:

   ```
   health_live_query("heart_rate", host="192.168.1.42", port=9000, start="2026-05-09", end="2026-05-10")
   ```

This mode is a v0.2 shim — the call returns the raw response. Future versions will normalize into the same DuckDB schema as Modes A/B.

## Optional: Lab CSV import

Apple Health does not capture clinical lab panels. To pair lab chemistry with biometrics, export from your patient portal and run:

```
health_import_labs("/path/to/labs.csv", lab_format="auto")
```

Supported formats: `labcorp`, `quest`, `function`, `generic`. Auto-detection by header shape.

Generic CSV shape if you are converting from another source:

```
test_date,panel,marker,value,unit,range_low,range_high,status,source
2026-05-01,metabolic,Fasting Insulin,4.2,uIU/mL,2.6,24.9,in_range,labcorp
```

Why bother? Run `health_recommended_labs()` for the substrate's reference panel with the WHY for each marker. Short version: Apple Health captures the visible 20% of health (heart rate, sleep, steps); the chemistry that drives chronic disease (ApoB, fasting insulin, hs-CRP, full thyroid, sex hormones) is invisible to it. The recovery-score formula in this MCP cannot detect chronic inflammation, subclinical hypothyroidism, or metabolic dysfunction. A lab panel can. The labs change the prescription.

The 16-marker reference panel: ApoB, Lp(a), hs-CRP, Fasting Insulin, HbA1c, Fasting Glucose, Triglyceride/HDL ratio, Full thyroid (TSH + free T3 + free T4 + reverse T3 + TPO antibodies), Vitamin D 25-OH, Ferritin, B12 + Folate + Homocysteine, Magnesium RBC, Sex hormones (Estradiol + Progesterone + Testosterone + DHEA-S + SHBG), Cortisol (4-point salivary), CMP, CBC.

The full panel runs ~$200-400/year at LabCorp or Quest direct-pay (no insurance needed in most US states). Order direct, get it drawn at any commercial lab, export the result CSV, import here.

## After import — sanity checks

```
health_status()
# {records_count, workouts_count, sleep_count, cycle_count, symptoms_count,
#  ecg_count, state_of_mind_count, labs_count, last_import, ...}

health_schema()
# Per-type row counts + date ranges

health_recovery_score("2026-05-09")
# {score: 72, components: {...}, confidence: "high"}

health_cycle_context("2026-05-09")
# {phase: "luteal", cycle_day: 22, irregularity: "regular", ...}

health_longevity_panel("2026-05-09")
# {vo2max: 42.5, walking_steadiness_pct: 92, lean_body_mass_kg: 48.2, zone2_minutes_30d: 480, ...}
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

Symptom correlation (Pagliano, panel 2026-05-10) reads symptoms either from Apple Health (preferred — log via the iOS Health app) or from a `symptoms:` array in your journal frontmatter.

## Voice profile for journal context

```
health_journal_context("2026-05-09", voice_profile="curious")
```

Three registers:
- **clinical** — exact numbers + percent deltas. For data export and reference.
- **warm** — narrative sentences. Default for daily-journal.
- **curious** — observation + question. Default for coaching. Returns "Body, last 24h: you slept 5h 12m short night; HRV ran noticeably below your usual. Anything you want to notice about how that maps to what happened yesterday?"

The journal skill pulls the rendered string and pastes it into the prompt directly, so the journaling voice is preserved.

## Troubleshooting

- **"No export.xml found inside zip"** — re-export from iOS Health directly.
- **"could not reach Health Auto Export"** — iPhone is asleep, the app is closed, or it is on a different Wi-Fi. The iOS app puts the TCP server to sleep when backgrounded for too long; re-open it before each query session.
- **Empty recovery score** — needs HRV + RHR + sleep data. Apple Watch records HRV during sleep; without an Apple Watch, recovery score will return `confidence: "low"` based on whatever inputs are present.
- **Empty cycle context** — needs Apple Health menstrual flow records. Log periods in iOS Health (Cycle Tracking) or via a paired app (Clue, Flo).
- **DuckDB locked** — only one writer at a time. Long ingest jobs hold the write lock; other tool calls queue.

## Privacy disclaimer

This server stores your health data in a local DuckDB file. Treat it as you would any other file containing personal medical information. Do not commit it to git. Do not sync it to cloud storage you do not trust. Do not share the DB file.

The scores reported are directional, not diagnostic. Use them as inputs to journaling and self-reflection, not as substitutes for medical advice. The recommended-labs reference list is informational; your physician sets your actual care plan.
