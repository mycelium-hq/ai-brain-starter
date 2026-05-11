## Apple Shortcuts bridge for health-mcp

Free, Apple-native auto-sync of HealthKit data into the health-mcp DuckDB.
Runs as a daily personal automation on your iPhone, writes a single JSON file
to iCloud Drive, the Mac picks it up and ingests on the next `/journal` Stop.

No third-party iOS apps. No subscriptions. No re-exports. Set it up once.

## How it works

```
iPhone Shortcut (daily, 6:00 AM, "Run Without Asking")
    │
    ├── Find Health Samples (HRV, RHR, sleep, steps, workouts, mindful, cycle, ...)
    ├── Build JSON dictionary
    └── Save to iCloud Drive: health-mcp/<YYYY-MM-DD>.json
                                    │
                                    └── (iCloud syncs to Mac)
                                            │
                                            └── On next /journal Stop hook:
                                                    coach-auto-prescribe-on-journal.py
                                                            │
                                                            └── shortcut_normalize.iter_payload
                                                                    │
                                                                    └── DuckDB rows
```

The Mac side is already wired (no setup). You only need to build the iPhone
Shortcut once.

## Build the Shortcut on your iPhone (5 minutes, free)

### Prerequisites

- iPhone running iOS 17 or later (older versions work but require a manual tap each morning)
- iCloud Drive enabled on the iPhone (Settings -> Apple ID -> iCloud -> iCloud Drive ON)
- The same iCloud account signed in on your Mac
- Health data being recorded (Apple Watch ideal but not required)

### Step 1: Create the iCloud Drive folder

On your Mac, open Finder -> iCloud Drive, create a new folder named exactly:

```
health-mcp
```

This is where the iPhone Shortcut will write payloads. The Mac receiver
auto-creates a `processed/` subfolder on first ingest.

### Step 2: Build the Shortcut

Open the **Shortcuts** app on your iPhone -> tap **+** (top right) -> name
it `Health Daily Sync`. Add the following actions in order. Each `Find Health
Samples` action filters by sample type and returns the last 24 hours.

1. **Date** action: pick "Yesterday" -> store in variable `yesterday`
2. **Find Health Samples** action: type = `Heart Rate`, sort by `Start Date`, no limit, where `Start Date is today`
3. **Repeat** for each of these sample types (one Find Health Samples action per type):
   - `Heart Rate Variability`
   - `Resting Heart Rate`
   - `Step Count`
   - `Active Energy`
   - `VO2 Max`
   - `Walking Heart Rate Average`
   - `Mindful Minutes`
4. **Find Health Samples**: type = `Sleep Analysis` (returns sleep stage segments)
5. **Find Workouts**: no filter (returns yesterday's workouts via the date filter)
6. **Find Health Samples**: type = `Menstrual Flow`
7. **Dictionary** action: build a dictionary matching the schema below. Each
   `Find Health Samples` result becomes a list under
   `samples.HKQuantityTypeIdentifier<Type>`.
8. **Get Contents of Dictionary** -> **Get Text from Dictionary** (JSON format)
9. **Save File** action: destination = iCloud Drive -> health-mcp folder,
   filename = `<formatted yesterday's date as YYYY-MM-DD>.json`, overwrite = ON

Final action: **Stop and Output** the dictionary so you can debug from the
Shortcuts app run log.

### Step 3: Schedule the daily automation

In Shortcuts -> tap **Automation** (bottom tab) -> **+** -> **Time of Day** ->
6:00 AM (or whenever you wake up) -> **Daily** -> tap your `Health Daily Sync`
Shortcut -> **Run Without Asking** = ON -> Done.

That's it. Every morning at 6 AM your iPhone fires the Shortcut silently,
writes yesterday's HealthKit data to iCloud Drive, the Mac picks it up on the
next `/journal` you run.

## Payload schema

The Shortcut writes a single JSON object per day. The Mac normalizer accepts
this shape:

```json
{
  "schema_version": 1,
  "exported_at": "2026-05-10T06:00:00-05:00",
  "date": "2026-05-09",
  "device": "iPhone",
  "samples": {
    "HKQuantityTypeIdentifierHeartRate": [
      {"start": "2026-05-09T08:00:00-05:00",
       "end":   "2026-05-09T08:00:30-05:00",
       "value": 62, "unit": "count/min", "source": "Apple Watch"}
    ],
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": [...],
    "HKQuantityTypeIdentifierRestingHeartRate":         [...],
    "HKQuantityTypeIdentifierStepCount":                [...],
    "HKQuantityTypeIdentifierActiveEnergyBurned":       [...],
    "HKQuantityTypeIdentifierVO2Max":                   [...]
  },
  "sleep":    [{"start": "...", "end": "...", "stage": "REM",  "source": "Apple Watch"}],
  "workouts": [{"activity_type": "Running", "start": "...", "end": "...",
                "duration_min": 32, "distance_km": 5.2, "energy_kcal": 320,
                "source": "Apple Watch"}],
  "mindful":  [{"start": "...", "end": "...", "duration_min": 10}],
  "cycle":    [{"type": "MenstrualFlow", "start": "...", "value": "medium"}]
}
```

Missing keys are tolerated. Unknown sample types pass through as-is into the
`records` table. Add or remove sample types in your Shortcut without
breaking the Mac side.

## Coverage and limits

Apple Shortcuts can read most HealthKit types via `Find Health Samples`,
including HRV, RHR, sleep stages, steps, workouts, mindful minutes, cycle
data, and VO2 Max. A few types are not exposed:

- ECG records (the `Find Health Samples` action skips them)
- Symptom logs (limited surface)
- State of Mind (iOS 17.2+, partial)

For full coverage, run `health_import_xml` periodically (monthly is plenty)
alongside the daily Shortcut sync. The substrate de-dupes via file SHA so the
two paths coexist cleanly.

## Manual run

To process the iCloud inbox on demand without waiting for `/journal`:

```python
health_sweep_shortcut_inbox()
```

Or for a single file:

```python
health_import_shortcut("~/Library/Mobile Documents/com~apple~CloudDocs/health-mcp/2026-05-09.json")
```

## Troubleshooting

**No payloads ever land on the Mac.** Check the Shortcut ran on the iPhone
(Shortcuts app -> Automation -> tap the automation -> view recent runs). If
the run failed, the most common cause is the Save File action pointing at the
wrong iCloud Drive folder. Re-pick the destination explicitly.

**"Run Without Asking" toggle is greyed out.** That means iOS thinks the
trigger requires confirmation. Double-check it is a *Time of Day* trigger,
not a *When App Opens* trigger. Time of Day allows silent run on iOS 17+.

**Payload lands but no rows appear in DuckDB.** Run `health_sweep_shortcut_inbox()`
manually and check the result. If `files_processed` is 0, verify the inbox
folder is exactly `~/Library/Mobile Documents/com~apple~CloudDocs/health-mcp/`
(case matters).

**iCloud sync is slow.** Apple sometimes delays iCloud Drive sync by 5-30
minutes. The Mac side processes payloads when they arrive; if your `/journal`
runs before iCloud has synced, the chain just picks them up on the next run.

**Bypass for the daily chain.** Set `HEALTH_AUTO_SYNC_BYPASS=1` in your env
to skip ALL wearable syncs in the chain (Oura, Fitbit, AND Apple Shortcut).
