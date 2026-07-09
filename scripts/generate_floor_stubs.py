#!/usr/bin/env python3
"""Generate one stub note per Floor + tier-index notes for the public substrate.

The substrate ships `floors.md` (one table). The `daily-journal` skill tags every
entry with wikilinks like `[[Fear]]` and `[[Low Floors]]`. Without per-floor
notes, those wikilinks resolve to empty bare-string nodes in the graph.

This script emits 34 floor stubs + 3 tier-index notes at `floors/<Name>.md`.
Bodies are the framework (energy line, elevator emotions involving the floor,
shadow-twin links, Substack series links) — not lived-experience prose.

Re-run after any change to the 34-floor canonical list in floors.md.
"""

import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "floors"

SUBSTACK_EN = "https://adelaidadiazroa.substack.com"
SUBSTACK_ES = "https://perspectivasblog.substack.com"

FLOORS = [
    (1,  "Disgust",       "Asco",          "Low",    "outward rejection, visceral 'get it away from me'"),
    (2,  "Shame",          "Vergüenza",     "Low",    "'I'm such an idiot,' self-disgust, hiding"),
    (3,  "Embarrassment",  "Bochorno",      "Low",    "social exposure, temporary, recoverable"),
    (4,  "Guilt",          "Culpa",         "Low",    "'I should be doing more,' letting people down"),
    (5,  "Apathy",         "Apatía",        "Low",    "'nothing matters,' checked out, numb"),
    (6,  "Resignation",    "Resignación",   "Low",    "defeated 'it is what it is' (not making peace)"),
    (7,  "Confusion",      "Confusión",     "Low",    "mind reaching and failing, contradictory thoughts"),
    (8,  "Loneliness",     "Soledad",       "Low",    "surrounded but unfound, no one gets it"),
    (9,  "Boredom",        "Aburrimiento",  "Low",    "restless, understimulated, the trampoline floor"),
    (10, "Grief",          "Duelo",         "Low",    "loss, sadness, missing someone or something"),
    (11, "Disappointment", "Decepción",     "Low",    "gap between hope and what arrived"),
    (12, "Hurt",           "Herida",        "Low",    "breach in a relationship, 'how could they'"),
    (13, "Fear",           "Miedo",         "Low",    "anxiety, 'what if,' imposter feelings"),
    (14, "Frustration",    "Frustración",   "Low",    "blocked energy, 'this should be working'"),
    (15, "Desire",         "Deseo",         "Low",    "wanting, craving, reaching, ambition mixed with lack"),
    (16, "Anger",          "Rabia",         "Low",    "directed energy, 'this is wrong,' disrespect"),
    (17, "Contempt",       "Desprecio",     "Low",    "'you are beneath me,' cold dismissal"),
    (18, "Pride",          "Orgullo",       "Low",    "proving something, need for external validation"),
    (19, "Courage",        "Valentía",      "Middle", "taking action despite fear, doing the hard thing"),
    (20, "Hope",           "Esperanza",     "Middle", "future-facing trust, steady forward momentum"),
    (21, "Neutrality",     "Neutralidad",   "Middle", "calm observation, processing without charge"),
    (22, "Willingness",    "Disposición",   "Middle", "optimistic restart, curiosity replaces fear"),
    (23, "Acceptance",     "Aceptación",    "Middle", "making peace with reality (not Resignation)"),
    (24, "Reason",         "Razón",         "Middle", "analytical, strategic, clear-headed"),
    (25, "Trust",          "Confianza",     "High",   "quiet confidence that things hold"),
    (26, "Compassion",     "Compasión",     "High",   "feeling others' pain without collapsing"),
    (27, "Humility",       "Humildad",      "High",   "accurate self-perception, 'I was wrong about'"),
    (28, "Belonging",      "Pertenencia",   "High",   "being received, 'I'm in the right room'"),
    (29, "Love",           "Amor",          "High",   "connection, warmth, giving freely"),
    (30, "Gratitude",      "Gratitud",      "High",   "presence recognizing abundance"),
    (31, "Excitement",     "Entusiasmo",    "High",   "anticipatory joy, body saying yes"),
    (32, "Wonder",         "Asombro",       "High",   "awe at what exists, expansion"),
    (33, "Joy",            "Alegría",       "High",   "delight, fun, laughter, alive"),
    (34, "Peace",          "Paz",           "High",   "stillness, nothing to fix, enough as-is"),
]

ELEVATORS = {
    "Nostalgia":     [(10, "Grief"), (29, "Love")],
    "Awe":           [(13, "Fear"), (32, "Wonder")],
    "Jealousy":      [(13, "Fear"), (15, "Desire"), (16, "Anger")],
    "Schadenfreude": [(18, "Pride"), (33, "Joy (corrupted)")],
    "Vulnerability": [(2, "Shame"), (29, "Love")],
    "Bittersweet":   [(10, "Grief"), (33, "Joy")],
}

SHADOWS = {
    6:  (23, "Acceptance", "'I've given up' vs 'I've made peace'"),
    5:  (21, "Neutrality", "'I don't care' vs 'I'm not attached'"),
    15: (29, "Love",       "'I want from you' vs 'I give to you'"),
    18: (25, "Trust",      "'I need you to see me' vs 'I see myself'"),
}
SHADOW_INVERSE = {high: (low, low_name, tell) for low, (high, _, tell) in SHADOWS.items()
                  for low_name in [next(f[1] for f in FLOORS if f[0] == low)]}

TIER_INDEX = {
    "Low":    ("Low Floors",    "Pisos Bajos",    "Reactive: 1-18. The reactive tier. Where the charge lives.",      1, 18),
    "Middle": ("Middle Floors", "Pisos Medios",   "Transitional: 19-24. The transitional tier. The climb up.",       19, 24),
    "High":   ("High Floors",   "Pisos Altos",    "Generative: 25-34. The generative tier. Where the energy gives.", 25, 34),
}

TIER_LEVEL = {"Low": "Low", "Middle": "Middle", "High": "High"}


def elevators_for(num: int) -> list[tuple[str, list[tuple[int, str]]]]:
    return [(name, members) for name, members in ELEVATORS.items()
            if any(m[0] == num or m[1].startswith(name[:4]) for m in members)
            and any(m[0] == num for m in members)]


def floor_body(num: int, en: str, es: str, tier: str, energy: str) -> str:
    elevators = elevators_for(num)
    shadow_block = ""
    if num in SHADOWS:
        high_num, high_name, tell = SHADOWS[num]
        shadow_block = dedent(f"""
            ## Shadow twin

            **{en} ({num})** is the shadow of **[[{high_name}]] ({high_num})**.

            > {tell}

            When {en} shows up easily, check whether [[{high_name}]] is what you actually mean. The difference is whether you are still bracing.
        """).strip() + "\n\n"
    elif num in SHADOW_INVERSE:
        low_num, low_name, tell = SHADOW_INVERSE[num]
        shadow_block = dedent(f"""
            ## Shadow twin

            **[[{low_name}]] ({low_num})** is the shadow of **{en} ({num})**.

            > {tell}

            Most "{en}" people claim is actually [[{low_name}]]. The difference is whether you are still bracing.
        """).strip() + "\n\n"

    elevator_block = ""
    if elevators:
        lines = []
        for elev_name, members in elevators:
            parts = []
            for m_num, m_name in members:
                if m_num == num:
                    parts.append(f"**{m_name}**")
                else:
                    base_name = m_name.split(" (")[0]
                    parts.append(f"[[{base_name}]]")
            lines.append(f"- **{elev_name}** = " + " + ".join(parts))
        elevator_block = "## Elevators involving this floor\n\n" + "\n".join(lines) + "\n\nThese are movements between floors, not floors themselves. The journal tags the floor you land on; the elevator name describes the trip.\n\n"

    tier_name = TIER_INDEX[tier][0]

    body = dedent(f"""\
        ---
        type: floor
        floor_number: {num}
        floor_name: {en}
        floor_level: {tier}
        aliases: [{es}, "Floor {num}", "Piso {num}"]
        ---

        # {en} · {es}

        **Floor {num} · {tier} tier**

        {energy[0].upper() + energy[1:]}.

        Part of the {tier.lower()} tier: see [[{tier_name}]].

        """)

    if elevator_block:
        body += elevator_block

    if shadow_block:
        body += shadow_block

    body += dedent(f"""\
        ## How to use this floor

        - **Name it.** "I'm on {en}," not "I'm in {en}." The naming reduces the charge.
        - **Look for the elevator.** What carried you here? A conversation, a meal, a meeting, a thought. The elevator is the actual lesson.
        - **Check the shadow twin** (above) if there is one.

        ## Narrative form

        The 34-floor framework started as a writing project. Each floor gets a lived-experience chapter in [[The High-Rise Series]]:

        - English: [{SUBSTACK_EN}]({SUBSTACK_EN})
        - Español: [{SUBSTACK_ES}]({SUBSTACK_ES})

        ## Reference

        See [[floors|All 34 floors]] for the canonical list. The framework is MIT-licensed and lives in the public substrate.
        """)

    return body


def tier_body(tier: str) -> str:
    en, es, blurb, lo, hi = TIER_INDEX[tier]
    rows = [f"- {n}. [[{f_en}]] ({f_es}) — {energy}" for n, f_en, f_es, t, energy in FLOORS if t == tier]
    return dedent(f"""\
        ---
        type: floor-tier
        tier: {tier}
        aliases: [{es}]
        ---

        # {en} · {es}

        {blurb}

        Floors **{lo}-{hi}**:

        """) + "\n".join(rows) + dedent(f"""

        ## Reference

        See [[floors|All 34 floors]] for the full canonical list with energies, Spanish names, elevator emotions, and shadow twins.
        """)


SERIES_BODY = dedent(f"""\
    ---
    type: writing-project
    aliases: ["High-Rise", "The High-Rise", "La Torre"]
    ---

    # The High-Rise Series

    A lived-experience writing project: each of the 34 floors gets its own chapter. Not theory. Not a self-help ladder. One person walking the building she lives in.

    Read the series:

    - English: [{SUBSTACK_EN}]({SUBSTACK_EN})
    - Español: [{SUBSTACK_ES}]({SUBSTACK_ES})

    The framework underneath the chapters (canonical 34-floor list, energies, Spanish names, tiers, elevator emotions, shadow twins) lives at [[floors|floors]]. Every floor note links back here.

    The framework is MIT-licensed and lives in the public substrate. The chapters are the author's writing and live behind their own license on Substack.
    """)


def main():
    OUT.mkdir(exist_ok=True)
    written = []
    for num, en, es, tier, energy in FLOORS:
        path = OUT / f"{en}.md"
        path.write_text(floor_body(num, en, es, tier, energy))
        written.append(str(path.relative_to(ROOT)))
    for tier in ("Low", "Middle", "High"):
        en, _, _, _, _ = TIER_INDEX[tier]
        path = OUT / f"{en}.md"
        path.write_text(tier_body(tier))
        written.append(str(path.relative_to(ROOT)))
    series_path = OUT / "The High-Rise Series.md"
    series_path.write_text(SERIES_BODY)
    written.append(str(series_path.relative_to(ROOT)))
    print(f"Wrote {len(written)} files:")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    # Windows cp1252-console safety (#313): force UTF-8 so a non-ASCII print can't crash.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    main()
