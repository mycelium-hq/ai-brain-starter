"""Voice-bridge: translate biometric facts from clinical register to a register
that fits inside the daily-journal / coaching / advisory-panel skills.

Why: the daily-journal skill speaks warm and curious. The coaching skill
speaks compassionate and slow. The advisory-panel skill speaks structured.
When health-context dumps "HRV 28ms vs 42ms 30-day baseline (-33%)" into
those prompts, the host skill's voice breaks.

This module renders the same facts in three registers:
  clinical — exact numbers, percent deltas, technical names. For data export
             and for the user's own reference.
  warm     — narrative sentences. "Your body had a slow night — HRV ran a
             third lower than your baseline." Default for daily-journal.
  curious  — open-ended observations + a question. "Your HRV came in low
             last night. Anything you want to notice about how the day
             before landed?" Default for coaching.

The skill picks the register via voice_profile config. The output is a STRING
ready to be folded into a prompt, not a structured dict — that's the bridge.
"""
from __future__ import annotations

from typing import Any


def _delta_phrase(delta_pct: float, magnitude_words: tuple[str, str, str] = ("slightly", "noticeably", "much")) -> str:
    """Map a percentage delta into a magnitude word."""
    abs_d = abs(delta_pct)
    if abs_d < 10:
        return magnitude_words[0]
    if abs_d < 25:
        return magnitude_words[1]
    return magnitude_words[2]


def _hrv_phrase(hrv: float | None, baseline: float | None, profile: str) -> str:
    if hrv is None:
        return ""
    if baseline is None or baseline == 0:
        if profile == "clinical":
            return f"HRV {hrv}ms"
        return f"HRV came in around {round(hrv)}ms"
    delta_pct = (hrv - baseline) / baseline * 100
    if profile == "clinical":
        sign = "+" if delta_pct >= 0 else ""
        return f"HRV {hrv}ms ({sign}{round(delta_pct)}% vs 30-day {round(baseline)}ms)"
    direction = "above" if delta_pct > 0 else "below"
    mag = _delta_phrase(delta_pct)
    if profile == "warm":
        return f"HRV ran {mag} {direction} your usual ({round(hrv)}ms vs {round(baseline)}ms)"
    return f"HRV ran {mag} {direction} your usual last night"


def _sleep_phrase(asleep_min: int, efficiency: float, profile: str) -> str:
    h = asleep_min // 60
    m = asleep_min % 60
    if profile == "clinical":
        return f"sleep {h}h {m}m, efficiency {round(efficiency * 100)}%"
    if profile == "warm":
        if asleep_min < 360:
            return f"you slept {h}h {m}m — short night"
        if asleep_min < 420:
            return f"you slept {h}h {m}m"
        return f"you slept {h}h {m}m — full rest"
    if asleep_min < 360:
        return "you got less rest than usual last night"
    if asleep_min < 420:
        return "rest landed in the middle of your usual range"
    return "your body got the rest it asked for"


def _rhr_phrase(rhr: float | None, profile: str) -> str:
    if rhr is None:
        return ""
    if profile == "clinical":
        return f"RHR {round(rhr)} bpm"
    if profile == "warm":
        if rhr > 75:
            return f"resting heart rate ran high ({round(rhr)} bpm)"
        if rhr < 55:
            return f"resting heart rate ran calm ({round(rhr)} bpm)"
        return f"resting heart rate {round(rhr)} bpm"
    return ""


def render_journal_context(ctx: dict[str, Any], profile: str = "curious") -> str:
    """Render journal_context output as a prompt string in the chosen register."""
    profile = profile.lower()
    if profile not in ("clinical", "warm", "curious"):
        profile = "curious"
    bits: list[str] = []
    hrv = ctx.get("hrv_ms")
    rhr = ctx.get("rhr_bpm")
    asleep = ctx.get("sleep_asleep_min", 0)
    efficiency = ctx.get("sleep_efficiency", 0)
    workouts = ctx.get("workout_count", 0)
    workout_min = ctx.get("workout_min", 0)
    steps = ctx.get("steps_total", 0)
    mindful = ctx.get("mindful_min", 0)

    if profile == "clinical":
        if hrv is not None:
            bits.append(_hrv_phrase(hrv, None, profile))
        if rhr is not None:
            bits.append(_rhr_phrase(rhr, profile))
        if asleep > 0:
            bits.append(_sleep_phrase(asleep, efficiency, profile))
        if steps:
            bits.append(f"steps {steps}")
        if workouts:
            bits.append(f"workouts {workouts} ({workout_min}min)")
        if mindful:
            bits.append(f"mindful {mindful}min")
        return "Body, today: " + ", ".join(bits) + "."

    if profile == "warm":
        if asleep > 0:
            bits.append(_sleep_phrase(asleep, efficiency, profile))
        if hrv is not None:
            bits.append(_hrv_phrase(hrv, None, profile))
        if rhr is not None:
            bits.append(_rhr_phrase(rhr, profile))
        if workouts:
            bits.append(f"you moved for {workout_min} minutes")
        if mindful:
            bits.append(f"you took {mindful} mindful minutes")
        text = "Body, today: " + "; ".join(b for b in bits if b) + "."
        return text

    # curious
    if asleep > 0:
        bits.append(_sleep_phrase(asleep, efficiency, profile))
    if hrv is not None:
        bits.append(_hrv_phrase(hrv, None, profile))
    if not bits:
        return ""
    body = "; ".join(b for b in bits if b)
    return f"Body, last 24h: {body}.\nAnything you want to notice about how that maps to what happened yesterday?"


def render_journal_context_with_baseline(
    ctx: dict[str, Any],
    hrv_baseline: float | None,
    profile: str = "curious",
) -> str:
    """Same as render_journal_context but uses a 30-day HRV baseline for the
    delta phrase. The baseline must come from the caller (computed by the
    score module to avoid double-querying)."""
    profile = profile.lower()
    if profile not in ("clinical", "warm", "curious"):
        profile = "curious"
    hrv = ctx.get("hrv_ms")
    rhr = ctx.get("rhr_bpm")
    asleep = ctx.get("sleep_asleep_min", 0)
    efficiency = ctx.get("sleep_efficiency", 0)
    bits: list[str] = []
    if asleep > 0:
        bits.append(_sleep_phrase(asleep, efficiency, profile))
    if hrv is not None and hrv_baseline is not None:
        bits.append(_hrv_phrase(hrv, hrv_baseline, profile))
    elif hrv is not None:
        bits.append(_hrv_phrase(hrv, None, profile))
    if rhr is not None and profile == "warm":
        bits.append(_rhr_phrase(rhr, profile))
    if not bits:
        return ""
    body = "; ".join(b for b in bits if b)
    if profile == "curious":
        return f"Body, last 24h: {body}.\nAnything you want to notice about how that maps to what happened yesterday?"
    return f"Body, today: {body}."


def render_body_question(ctx: dict[str, Any]) -> str:
    """Body-literacy prompt (Bainbridge, panel 2026-05-10): return a question,
    not a number. The question is context-aware — it lands differently
    depending on whether the body had a hard night, a strong day, etc."""
    asleep = ctx.get("sleep_asleep_min", 0)
    hrv = ctx.get("hrv_ms")
    workout = ctx.get("workout_count", 0)
    rem = ctx.get("sleep_rem_min", 0)
    deep = ctx.get("sleep_deep_min", 0)

    if asleep < 360 and (rem + deep) < 60:
        return "Your body had a hard night. What did it want from you today that you didn't give it?"
    if hrv is not None and hrv < 25:
        return "HRV came in low. What is your body holding right now that hasn't moved through yet?"
    if workout > 0 and asleep > 420:
        return "You moved and you rested. What did your body teach you today that it couldn't teach you yesterday?"
    if asleep > 480 and (rem + deep) > 120:
        return "Your body had a deep night. What is it asking you to take on now that it's restored?"
    return "How does your body feel right now? Not what should you be feeling — what's actually there?"
