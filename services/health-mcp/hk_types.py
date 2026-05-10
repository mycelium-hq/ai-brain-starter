"""HealthKit type registry: the canonical map of every Apple Health surface
this MCP knows how to ingest and surface.

Sourced from Apple's HealthKit framework reference (developer.apple.com).
Categorized for tool routing: an aggregation tool that runs over "activity"
types should NOT include "lab" types, etc.

The structure:
  HK_QUANTITY_TYPES — every HKQuantityTypeIdentifier we ingest
  HK_CATEGORY_TYPES — every HKCategoryTypeIdentifier we ingest
  HK_WORKOUT_ACTIVITY_TYPES — workout activity-type display names
  CYCLE_TYPES, SYMPTOM_TYPES, NUTRITION_TYPES, LONGEVITY_TYPES,
  SLEEP_STAGE_MAP — semantic groupings for tool surfaces

aggregation: "sum" for cumulative metrics (steps, energy, distance, dietary
            intake) — daily total is meaningful.
            "avg" for rate metrics (HR, BP, RR) — daily mean is meaningful.
            "last" for snapshot metrics (body mass, waist, height) — most
            recent is meaningful.

Apple Health type identifiers are stable across iOS versions; deprecated ones
are kept here so historical data still parses.
"""
from __future__ import annotations

from typing import Any

# Sleep stage mapping (HKCategoryValueSleepAnalysis) — single source of truth.
SLEEP_STAGE_MAP = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleep": "asleep_unspecified",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep_unspecified",
}


HK_QUANTITY_TYPES: dict[str, dict[str, Any]] = {
    # ----- Activity (cumulative) -----
    "HKQuantityTypeIdentifierStepCount": {"category": "activity", "unit": "count", "aggregation": "sum", "display_name": "Steps"},
    "HKQuantityTypeIdentifierDistanceWalkingRunning": {"category": "activity", "unit": "km", "aggregation": "sum", "display_name": "Walking + running distance"},
    "HKQuantityTypeIdentifierDistanceCycling": {"category": "activity", "unit": "km", "aggregation": "sum", "display_name": "Cycling distance"},
    "HKQuantityTypeIdentifierDistanceSwimming": {"category": "activity", "unit": "m", "aggregation": "sum", "display_name": "Swimming distance"},
    "HKQuantityTypeIdentifierDistanceWheelchair": {"category": "activity", "unit": "m", "aggregation": "sum", "display_name": "Wheelchair distance"},
    "HKQuantityTypeIdentifierDistanceDownhillSnowSports": {"category": "activity", "unit": "m", "aggregation": "sum", "display_name": "Snow sports distance"},
    "HKQuantityTypeIdentifierActiveEnergyBurned": {"category": "activity", "unit": "kcal", "aggregation": "sum", "display_name": "Active energy"},
    "HKQuantityTypeIdentifierBasalEnergyBurned": {"category": "activity", "unit": "kcal", "aggregation": "sum", "display_name": "Resting energy"},
    "HKQuantityTypeIdentifierFlightsClimbed": {"category": "activity", "unit": "count", "aggregation": "sum", "display_name": "Flights climbed"},
    "HKQuantityTypeIdentifierAppleExerciseTime": {"category": "activity", "unit": "min", "aggregation": "sum", "display_name": "Exercise minutes"},
    "HKQuantityTypeIdentifierAppleStandTime": {"category": "activity", "unit": "min", "aggregation": "sum", "display_name": "Stand minutes"},
    "HKQuantityTypeIdentifierAppleMoveTime": {"category": "activity", "unit": "min", "aggregation": "sum", "display_name": "Move minutes"},
    "HKQuantityTypeIdentifierPushCount": {"category": "activity", "unit": "count", "aggregation": "sum", "display_name": "Wheelchair pushes"},
    "HKQuantityTypeIdentifierSwimmingStrokeCount": {"category": "activity", "unit": "count", "aggregation": "sum", "display_name": "Swimming strokes"},
    "HKQuantityTypeIdentifierNikeFuel": {"category": "activity", "unit": "count", "aggregation": "sum", "display_name": "NikeFuel"},
    "HKQuantityTypeIdentifierUnderwaterDepth": {"category": "activity", "unit": "m", "aggregation": "avg", "display_name": "Underwater depth"},

    # ----- Cardio fitness + gait + longevity (rate / snapshot) -----
    "HKQuantityTypeIdentifierVO2Max": {"category": "longevity", "unit": "ml/kg*min", "aggregation": "avg", "display_name": "VO2 Max"},
    "HKQuantityTypeIdentifierWalkingSpeed": {"category": "longevity", "unit": "m/s", "aggregation": "avg", "display_name": "Walking speed"},
    "HKQuantityTypeIdentifierWalkingStepLength": {"category": "longevity", "unit": "cm", "aggregation": "avg", "display_name": "Walking step length"},
    "HKQuantityTypeIdentifierWalkingAsymmetryPercentage": {"category": "longevity", "unit": "%", "aggregation": "avg", "display_name": "Walking asymmetry"},
    "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage": {"category": "longevity", "unit": "%", "aggregation": "avg", "display_name": "Double-support %"},
    "HKQuantityTypeIdentifierAppleWalkingSteadiness": {"category": "longevity", "unit": "%", "aggregation": "avg", "display_name": "Walking steadiness"},
    "HKQuantityTypeIdentifierSixMinuteWalkTestDistance": {"category": "longevity", "unit": "m", "aggregation": "avg", "display_name": "Six-minute walk distance"},
    "HKQuantityTypeIdentifierStairAscentSpeed": {"category": "longevity", "unit": "m/s", "aggregation": "avg", "display_name": "Stair ascent speed"},
    "HKQuantityTypeIdentifierStairDescentSpeed": {"category": "longevity", "unit": "m/s", "aggregation": "avg", "display_name": "Stair descent speed"},
    "HKQuantityTypeIdentifierRunningGroundContactTime": {"category": "longevity", "unit": "ms", "aggregation": "avg", "display_name": "Running ground contact"},
    "HKQuantityTypeIdentifierRunningPower": {"category": "longevity", "unit": "W", "aggregation": "avg", "display_name": "Running power"},
    "HKQuantityTypeIdentifierRunningSpeed": {"category": "longevity", "unit": "m/s", "aggregation": "avg", "display_name": "Running speed"},
    "HKQuantityTypeIdentifierRunningStrideLength": {"category": "longevity", "unit": "m", "aggregation": "avg", "display_name": "Running stride length"},
    "HKQuantityTypeIdentifierRunningVerticalOscillation": {"category": "longevity", "unit": "cm", "aggregation": "avg", "display_name": "Running vertical oscillation"},
    "HKQuantityTypeIdentifierCyclingCadence": {"category": "longevity", "unit": "rpm", "aggregation": "avg", "display_name": "Cycling cadence"},
    "HKQuantityTypeIdentifierCyclingFunctionalThresholdPower": {"category": "longevity", "unit": "W", "aggregation": "avg", "display_name": "Cycling FTP"},
    "HKQuantityTypeIdentifierCyclingPower": {"category": "longevity", "unit": "W", "aggregation": "avg", "display_name": "Cycling power"},
    "HKQuantityTypeIdentifierCyclingSpeed": {"category": "longevity", "unit": "m/s", "aggregation": "avg", "display_name": "Cycling speed"},
    "HKQuantityTypeIdentifierPhysicalEffort": {"category": "longevity", "unit": "kcal/(kg*hr)", "aggregation": "avg", "display_name": "Physical effort"},

    # ----- Heart -----
    "HKQuantityTypeIdentifierHeartRate": {"category": "cardio", "unit": "count/min", "aggregation": "avg", "display_name": "Heart rate"},
    "HKQuantityTypeIdentifierRestingHeartRate": {"category": "cardio", "unit": "count/min", "aggregation": "avg", "display_name": "Resting heart rate"},
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": {"category": "cardio", "unit": "count/min", "aggregation": "avg", "display_name": "Walking heart rate"},
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": {"category": "cardio", "unit": "ms", "aggregation": "avg", "display_name": "HRV (SDNN)"},
    "HKQuantityTypeIdentifierHeartRateRecoveryOneMinute": {"category": "cardio", "unit": "count/min", "aggregation": "avg", "display_name": "Heart rate recovery (1min)"},
    "HKQuantityTypeIdentifierAtrialFibrillationBurden": {"category": "cardio", "unit": "%", "aggregation": "avg", "display_name": "AFib burden"},
    "HKQuantityTypeIdentifierPeripheralPerfusionIndex": {"category": "cardio", "unit": "%", "aggregation": "avg", "display_name": "Peripheral perfusion index"},

    # ----- Vitals -----
    "HKQuantityTypeIdentifierBloodPressureSystolic": {"category": "vitals", "unit": "mmHg", "aggregation": "avg", "display_name": "Systolic BP"},
    "HKQuantityTypeIdentifierBloodPressureDiastolic": {"category": "vitals", "unit": "mmHg", "aggregation": "avg", "display_name": "Diastolic BP"},
    "HKQuantityTypeIdentifierOxygenSaturation": {"category": "vitals", "unit": "%", "aggregation": "avg", "display_name": "Blood oxygen"},
    "HKQuantityTypeIdentifierRespiratoryRate": {"category": "vitals", "unit": "count/min", "aggregation": "avg", "display_name": "Respiratory rate"},
    "HKQuantityTypeIdentifierBodyTemperature": {"category": "vitals", "unit": "degF", "aggregation": "avg", "display_name": "Body temperature"},
    "HKQuantityTypeIdentifierBasalBodyTemperature": {"category": "vitals", "unit": "degF", "aggregation": "avg", "display_name": "Basal body temperature"},
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": {"category": "vitals", "unit": "degF", "aggregation": "avg", "display_name": "Sleeping wrist temperature"},

    # ----- Body composition (snapshots) -----
    "HKQuantityTypeIdentifierBodyMass": {"category": "body", "unit": "kg", "aggregation": "last", "display_name": "Body mass"},
    "HKQuantityTypeIdentifierBodyMassIndex": {"category": "body", "unit": "kg/m^2", "aggregation": "last", "display_name": "BMI"},
    "HKQuantityTypeIdentifierBodyFatPercentage": {"category": "body", "unit": "%", "aggregation": "last", "display_name": "Body fat %"},
    "HKQuantityTypeIdentifierLeanBodyMass": {"category": "body", "unit": "kg", "aggregation": "last", "display_name": "Lean body mass"},
    "HKQuantityTypeIdentifierHeight": {"category": "body", "unit": "cm", "aggregation": "last", "display_name": "Height"},
    "HKQuantityTypeIdentifierWaistCircumference": {"category": "body", "unit": "cm", "aggregation": "last", "display_name": "Waist circumference"},
    "HKQuantityTypeIdentifierElectrodermalActivity": {"category": "body", "unit": "uS", "aggregation": "avg", "display_name": "Electrodermal activity"},

    # ----- Lab values + clinical -----
    "HKQuantityTypeIdentifierBloodGlucose": {"category": "lab", "unit": "mg/dL", "aggregation": "avg", "display_name": "Blood glucose"},
    "HKQuantityTypeIdentifierBloodAlcoholContent": {"category": "lab", "unit": "%", "aggregation": "avg", "display_name": "Blood alcohol content"},
    "HKQuantityTypeIdentifierForcedExpiratoryVolume1": {"category": "lab", "unit": "L", "aggregation": "avg", "display_name": "FEV1"},
    "HKQuantityTypeIdentifierForcedVitalCapacity": {"category": "lab", "unit": "L", "aggregation": "avg", "display_name": "FVC"},
    "HKQuantityTypeIdentifierPeakExpiratoryFlowRate": {"category": "lab", "unit": "L/min", "aggregation": "avg", "display_name": "Peak expiratory flow"},
    "HKQuantityTypeIdentifierInhalerUsage": {"category": "lab", "unit": "count", "aggregation": "sum", "display_name": "Inhaler puffs"},
    "HKQuantityTypeIdentifierInsulinDelivery": {"category": "lab", "unit": "IU", "aggregation": "sum", "display_name": "Insulin delivery"},
    "HKQuantityTypeIdentifierNumberOfTimesFallen": {"category": "lab", "unit": "count", "aggregation": "sum", "display_name": "Falls"},

    # ----- Sensory -----
    "HKQuantityTypeIdentifierEnvironmentalAudioExposure": {"category": "sensory", "unit": "dBASPL", "aggregation": "avg", "display_name": "Environmental audio"},
    "HKQuantityTypeIdentifierHeadphoneAudioExposure": {"category": "sensory", "unit": "dBASPL", "aggregation": "avg", "display_name": "Headphone audio"},
    "HKQuantityTypeIdentifierTimeInDaylight": {"category": "sensory", "unit": "min", "aggregation": "sum", "display_name": "Time in daylight"},
    "HKQuantityTypeIdentifierUVExposure": {"category": "sensory", "unit": "count", "aggregation": "sum", "display_name": "UV exposure"},

    # ----- Nutrition (cumulative dietary intake) -----
    "HKQuantityTypeIdentifierDietaryEnergyConsumed": {"category": "nutrition", "unit": "kcal", "aggregation": "sum", "display_name": "Energy consumed"},
    "HKQuantityTypeIdentifierDietaryFatTotal": {"category": "nutrition", "unit": "g", "aggregation": "sum", "display_name": "Fat (total)"},
    "HKQuantityTypeIdentifierDietaryFatPolyunsaturated": {"category": "nutrition", "unit": "g", "aggregation": "sum", "display_name": "Fat (polyunsaturated)"},
    "HKQuantityTypeIdentifierDietaryFatMonounsaturated": {"category": "nutrition", "unit": "g", "aggregation": "sum", "display_name": "Fat (monounsaturated)"},
    "HKQuantityTypeIdentifierDietaryFatSaturated": {"category": "nutrition", "unit": "g", "aggregation": "sum", "display_name": "Fat (saturated)"},
    "HKQuantityTypeIdentifierDietaryCholesterol": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Cholesterol"},
    "HKQuantityTypeIdentifierDietarySodium": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Sodium"},
    "HKQuantityTypeIdentifierDietaryCarbohydrates": {"category": "nutrition", "unit": "g", "aggregation": "sum", "display_name": "Carbohydrates"},
    "HKQuantityTypeIdentifierDietaryFiber": {"category": "nutrition", "unit": "g", "aggregation": "sum", "display_name": "Fiber"},
    "HKQuantityTypeIdentifierDietarySugar": {"category": "nutrition", "unit": "g", "aggregation": "sum", "display_name": "Sugar"},
    "HKQuantityTypeIdentifierDietaryProtein": {"category": "nutrition", "unit": "g", "aggregation": "sum", "display_name": "Protein"},
    "HKQuantityTypeIdentifierDietaryVitaminA": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Vitamin A"},
    "HKQuantityTypeIdentifierDietaryThiamin": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Thiamin (B1)"},
    "HKQuantityTypeIdentifierDietaryRiboflavin": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Riboflavin (B2)"},
    "HKQuantityTypeIdentifierDietaryNiacin": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Niacin (B3)"},
    "HKQuantityTypeIdentifierDietaryPantothenicAcid": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Pantothenic acid (B5)"},
    "HKQuantityTypeIdentifierDietaryVitaminB6": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Vitamin B6"},
    "HKQuantityTypeIdentifierDietaryBiotin": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Biotin (B7)"},
    "HKQuantityTypeIdentifierDietaryFolate": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Folate (B9)"},
    "HKQuantityTypeIdentifierDietaryVitaminB12": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Vitamin B12"},
    "HKQuantityTypeIdentifierDietaryVitaminC": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Vitamin C"},
    "HKQuantityTypeIdentifierDietaryVitaminD": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Vitamin D"},
    "HKQuantityTypeIdentifierDietaryVitaminE": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Vitamin E"},
    "HKQuantityTypeIdentifierDietaryVitaminK": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Vitamin K"},
    "HKQuantityTypeIdentifierDietaryCalcium": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Calcium"},
    "HKQuantityTypeIdentifierDietaryIron": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Iron"},
    "HKQuantityTypeIdentifierDietaryPhosphorus": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Phosphorus"},
    "HKQuantityTypeIdentifierDietaryIodine": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Iodine"},
    "HKQuantityTypeIdentifierDietaryMagnesium": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Magnesium"},
    "HKQuantityTypeIdentifierDietaryZinc": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Zinc"},
    "HKQuantityTypeIdentifierDietarySelenium": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Selenium"},
    "HKQuantityTypeIdentifierDietaryCopper": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Copper"},
    "HKQuantityTypeIdentifierDietaryManganese": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Manganese"},
    "HKQuantityTypeIdentifierDietaryChromium": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Chromium"},
    "HKQuantityTypeIdentifierDietaryMolybdenum": {"category": "nutrition", "unit": "mcg", "aggregation": "sum", "display_name": "Molybdenum"},
    "HKQuantityTypeIdentifierDietaryChloride": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Chloride"},
    "HKQuantityTypeIdentifierDietaryPotassium": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Potassium"},
    "HKQuantityTypeIdentifierDietaryCaffeine": {"category": "nutrition", "unit": "mg", "aggregation": "sum", "display_name": "Caffeine"},
    "HKQuantityTypeIdentifierDietaryWater": {"category": "nutrition", "unit": "ml", "aggregation": "sum", "display_name": "Water"},
    "HKQuantityTypeIdentifierNumberOfAlcoholicBeverages": {"category": "nutrition", "unit": "count", "aggregation": "sum", "display_name": "Alcoholic beverages"},
}


HK_CATEGORY_TYPES: dict[str, dict[str, Any]] = {
    # Sleep
    "HKCategoryTypeIdentifierSleepAnalysis": {"category": "sleep", "table": "sleep"},
    "HKCategoryTypeIdentifierSleepChanges": {"category": "sleep", "table": "symptoms"},

    # Mindfulness — duration-bearing, lives in records via duration math
    "HKCategoryTypeIdentifierMindfulSession": {"category": "mindfulness", "table": "records"},

    # Reproductive / cycle (every type Apple ships)
    "HKCategoryTypeIdentifierMenstrualFlow": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierIntermenstrualBleeding": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierInfrequentMenstrualCycles": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierIrregularMenstrualCycles": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierProlongedMenstrualPeriods": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierPersistentIntermenstrualBleeding": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierCervicalMucusQuality": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierOvulationTestResult": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierPregnancyTestResult": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierProgesteroneTestResult": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierContraceptive": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierLactation": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierPregnancy": {"category": "cycle", "table": "cycle"},
    "HKCategoryTypeIdentifierSexualActivity": {"category": "cycle", "table": "cycle"},

    # Symptoms (every type Apple ships in iOS 17+)
    "HKCategoryTypeIdentifierAcne": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierAppetiteChanges": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierBladderIncontinence": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierBloating": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierBreastPain": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierChestTightnessOrPain": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierChills": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierConstipation": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierCoughing": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierDiarrhea": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierDizziness": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierDrySkin": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierFainting": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierFatigue": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierFever": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierGeneralizedBodyAche": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierHairLoss": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierHeadache": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierHeartburn": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierHotFlashes": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierLossOfSmell": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierLossOfTaste": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierLowerBackPain": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierMemoryLapse": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierMoodChanges": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierNausea": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierNightSweats": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierPelvicPain": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierRapidPoundingOrFlutteringHeartbeat": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierRunnyNose": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierShortnessOfBreath": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierSinusCongestion": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierSkippedHeartbeat": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierSoreThroat": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierVaginalDryness": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierVomiting": {"category": "symptom", "table": "symptoms"},
    "HKCategoryTypeIdentifierWheezing": {"category": "symptom", "table": "symptoms"},

    # Cardio events
    "HKCategoryTypeIdentifierHighHeartRateEvent": {"category": "cardio_event", "table": "symptoms"},
    "HKCategoryTypeIdentifierLowHeartRateEvent": {"category": "cardio_event", "table": "symptoms"},
    "HKCategoryTypeIdentifierIrregularHeartRhythmEvent": {"category": "cardio_event", "table": "symptoms"},
    "HKCategoryTypeIdentifierLowCardioFitnessEvent": {"category": "cardio_event", "table": "symptoms"},
    "HKCategoryTypeIdentifierAppleWalkingSteadinessEvent": {"category": "cardio_event", "table": "symptoms"},

    # Hearing
    "HKCategoryTypeIdentifierAudioExposureEvent": {"category": "sensory", "table": "symptoms"},
    "HKCategoryTypeIdentifierEnvironmentalAudioExposureEvent": {"category": "sensory", "table": "symptoms"},
    "HKCategoryTypeIdentifierHeadphoneAudioExposureEvent": {"category": "sensory", "table": "symptoms"},

    # Toothbrushing + handwashing (lifestyle)
    "HKCategoryTypeIdentifierToothbrushingEvent": {"category": "lifestyle", "table": "symptoms"},
    "HKCategoryTypeIdentifierHandwashingEvent": {"category": "lifestyle", "table": "symptoms"},
}


# Cycle types — used by cycle.py for phase detection
CYCLE_TYPES = [t for t, meta in HK_CATEGORY_TYPES.items() if meta.get("category") == "cycle"]
SYMPTOM_TYPES = [t for t, meta in HK_CATEGORY_TYPES.items() if meta.get("category") in {"symptom", "cardio_event", "sensory", "lifestyle"}]
NUTRITION_TYPES = [t for t, meta in HK_QUANTITY_TYPES.items() if meta["category"] == "nutrition"]
LONGEVITY_TYPES = [t for t, meta in HK_QUANTITY_TYPES.items() if meta["category"] == "longevity"]
ACTIVITY_TYPES = [t for t, meta in HK_QUANTITY_TYPES.items() if meta["category"] == "activity"]
CARDIO_TYPES = [t for t, meta in HK_QUANTITY_TYPES.items() if meta["category"] == "cardio"]
VITALS_TYPES = [t for t, meta in HK_QUANTITY_TYPES.items() if meta["category"] == "vitals"]
SENSORY_TYPES = [t for t, meta in HK_QUANTITY_TYPES.items() if meta["category"] == "sensory"]


# Menstrual flow severity ordering (used by cycle.py to find the start of menstruation)
MENSTRUAL_FLOW_VALUES = {
    "HKCategoryValueMenstrualFlowUnspecified": 1,
    "HKCategoryValueMenstrualFlowLight": 1,
    "HKCategoryValueMenstrualFlowMedium": 2,
    "HKCategoryValueMenstrualFlowHeavy": 3,
    "HKCategoryValueMenstrualFlowNone": 0,
}


# Symptom severity (HKCategoryValueSeverity) — applies to most symptom types
SYMPTOM_SEVERITY_MAP = {
    "HKCategoryValueSeverityNotPresent": "not_present",
    "HKCategoryValueSeverityMild": "mild",
    "HKCategoryValueSeverityModerate": "moderate",
    "HKCategoryValueSeveritySevere": "severe",
    "HKCategoryValueSeverityUnspecified": "unspecified",
}


# Cervical mucus + ovulation test value maps
CERVICAL_MUCUS_MAP = {
    "HKCategoryValueCervicalMucusQualityDry": "dry",
    "HKCategoryValueCervicalMucusQualitySticky": "sticky",
    "HKCategoryValueCervicalMucusQualityCreamy": "creamy",
    "HKCategoryValueCervicalMucusQualityWatery": "watery",
    "HKCategoryValueCervicalMucusQualityEggWhite": "egg_white",
}
OVULATION_TEST_MAP = {
    "HKCategoryValueOvulationTestResultNegative": "negative",
    "HKCategoryValueOvulationTestResultLuteinizingHormoneSurge": "lh_surge",
    "HKCategoryValueOvulationTestResultIndeterminate": "indeterminate",
    "HKCategoryValueOvulationTestResultEstrogenSurge": "estrogen_surge",
}
PREGNANCY_TEST_MAP = {
    "HKCategoryValuePregnancyTestResultNegative": "negative",
    "HKCategoryValuePregnancyTestResultPositive": "positive",
    "HKCategoryValuePregnancyTestResultIndeterminate": "indeterminate",
}


def category_for_type(type_id: str) -> str:
    """Lookup the category for any quantity or category type. Returns 'other'
    for unknown types so the parser can store them under records and the LLM
    can still see them via health_query."""
    if type_id in HK_QUANTITY_TYPES:
        return HK_QUANTITY_TYPES[type_id]["category"]
    if type_id in HK_CATEGORY_TYPES:
        return HK_CATEGORY_TYPES[type_id]["category"]
    return "other"


def aggregation_for_type(type_id: str) -> str:
    """For HKQuantityTypeIdentifier, return 'sum' | 'avg' | 'last'.
    Default to 'avg' for unknown types — safer than sum for unit-mismatched values."""
    if type_id in HK_QUANTITY_TYPES:
        return HK_QUANTITY_TYPES[type_id]["aggregation"]
    return "avg"


def display_name(type_id: str) -> str:
    if type_id in HK_QUANTITY_TYPES:
        return HK_QUANTITY_TYPES[type_id]["display_name"]
    if type_id in HK_CATEGORY_TYPES:
        return type_id.replace("HKCategoryTypeIdentifier", "").replace("HKQuantityTypeIdentifier", "")
    return type_id
