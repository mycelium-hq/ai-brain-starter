# Floors

The journal tags every entry with a Floor: the emotional consciousness level you were on when you wrote it. Over time the tag becomes infrastructure. Patterns surface, loops get named, and you stop being surprised by your own weather.

This file is the reference. What the floors are, how they work, how to use them.

Each floor also has its own note at [`floors/<Name>.md`](floors/) — graphify uses those so journal entries tagged `[[Fear]]` resolve to a node with body content, elevator-emotion edges, shadow-twin links, and a pointer to the writing series. Regenerate them from this table with `scripts/generate_floor_stubs.py` if you change the canonical list below.

---

## The framework, in one paragraph

Thirty-four floors of emotional consciousness, low to high. Hawkins-derived (Power vs. Force, 1995), expanded from the original sixteen as the work asked for more resolution. Floor 1 is Disgust. Floor 34 is Peace. Three tiers: Low (1-18, reactive), Middle (19-24, transitional), High (25-34, generative). Every floor is real. Every floor is workable. None of them is bad. The journal does not ask you to climb. It asks you to know where you are.

---

## The 34 floors

| # | English | Español | Tier | Energy |
|---|---|---|---|---|
| 1 | Disgust | Asco | Low | outward rejection, visceral "get it away from me" |
| 2 | Shame | Vergüenza | Low | "I'm such an idiot," self-disgust, hiding |
| 3 | Embarrassment | Bochorno | Low | social exposure, temporary, recoverable |
| 4 | Guilt | Culpa | Low | "I should be doing more," letting people down |
| 5 | Apathy | Apatía | Low | "nothing matters," checked out, numb |
| 6 | Resignation | Resignación | Low | defeated "it is what it is" (NOT making peace) |
| 7 | Confusion | Confusión | Low | mind reaching and failing, contradictory thoughts |
| 8 | Loneliness | Soledad | Low | surrounded but unfound, no one gets it |
| 9 | Boredom | Aburrimiento | Low | restless, understimulated, the trampoline floor |
| 10 | Grief | Duelo | Low | loss, sadness, missing someone or something |
| 11 | Disappointment | Decepción | Low | gap between hope and what arrived |
| 12 | Hurt | Herida | Low | breach in a relationship, "how could they" |
| 13 | Fear | Miedo | Low | anxiety, "what if," imposter feelings |
| 14 | Frustration | Frustración | Low | blocked energy, "this should be working" |
| 15 | Desire | Deseo | Low | wanting, craving, reaching, ambition mixed with lack |
| 16 | Anger | Rabia | Low | directed energy, "this is wrong," disrespect |
| 17 | Contempt | Desprecio | Low | "you are beneath me," cold dismissal |
| 18 | Pride | Orgullo | Low | proving something, need for external validation |
| 19 | Courage | Valentía | Middle | taking action despite fear, doing the hard thing |
| 20 | Hope | Esperanza | Middle | future-facing trust, steady forward momentum |
| 21 | Neutrality | Neutralidad | Middle | calm observation, processing without charge |
| 22 | Willingness | Disposición | Middle | optimistic restart, curiosity replaces fear |
| 23 | Acceptance | Aceptación | Middle | making peace with reality (NOT Resignation) |
| 24 | Reason | Razón | Middle | analytical, strategic, clear-headed |
| 25 | Trust | Confianza | High | quiet confidence that things hold |
| 26 | Compassion | Compasión | High | feeling others' pain without collapsing |
| 27 | Humility | Humildad | High | accurate self-perception, "I was wrong about" |
| 28 | Belonging | Pertenencia | High | being received, "I'm in the right room" |
| 29 | Love | Amor | High | connection, warmth, giving freely |
| 30 | Gratitude | Gratitud | High | presence recognizing abundance |
| 31 | Excitement | Entusiasmo | High | anticipatory joy, body saying yes |
| 32 | Wonder | Asombro | High | awe at what exists, expansion |
| 33 | Joy | Alegría | High | delight, fun, laughter, alive |
| 34 | Peace | Paz | High | stillness, nothing to fix, enough as-is |

Three tiers: **Low** = 1-18 (Reactive). **Middle** = 19-24 (Transitional). **High** = 25-34 (Generative).

---

## Elevator emotions

Some emotions are not floors but movements between them. The journal tags the floor you land on; these names describe the trip.

- **Nostalgia** = Grief (10) + Love (29)
- **Awe** = Fear (13) + Wonder (32)
- **Jealousy** = Fear (13) + Desire (15) + Anger (16)
- **Schadenfreude** = Pride (18) + corrupted Joy (33)
- **Vulnerability** = Shame (2) climbing to Love (29), a staircase taken step by step
- **Bittersweet** = Grief (10) + Joy (33)
- **Overwhelm** = any floor flooding (capacity failure)

---

## Shadow twins

A low floor pretending to be its high twin. The journal asks you to name which one you're actually on. The mistake is the lesson.

| Shadow (Low) | True floor (High) | Tell |
|---|---|---|
| Resignation (6) | Acceptance (23) | "I've given up" vs. "I've made peace" |
| Apathy (5) | Neutrality (21) | "I don't care" vs. "I'm not attached" |
| Desire (15) | Love (29) | "I want from you" vs. "I give to you" |
| Pride (18) | Confidence | "I need you to see me" vs. "I see myself" |

---

## How the journal uses the floor

The `daily-journal` skill asks one question at the end of each entry: where were you today? The answer becomes a frontmatter field on the saved entry:

```yaml
floor: Hope
floor_level: Middle
```

That tag is the seed. Over weeks, it tells you which floors you spend most time on, which ones you cycle through, which loops you are stuck in. The `patterns` skill reads it. The `insights` skill reads it. The `coaching` skill reads it. The `rise` morning skill reads yesterday's tag to choose today's body movement.

You can backfill past entries by running the journal skill with a date range.

---

## How to use the framework if you do not journal

You do not need the install for the floors to be useful. Three reps that work on their own:

1. **Name the floor before reacting.** When you feel something hard, the first move is to name which floor it is. The naming itself reduces the charge. You are on Frustration, not in Frustration.
2. **Check for shadow twins.** When a high floor shows up easily, ask whether the shadow is in costume. Most "Acceptance" is Resignation. Most "Confidence" is Pride. The difference is whether you are still bracing.
3. **Watch elevators, not just floors.** What carried you from one floor to another? A walk. A conversation. A meal. A meeting. The elevators are the actual lesson; the floors are where the elevator opens.

---

## The narrative form

These floors started as a writing project, where each one gets a chapter of lived experience instead of a one-line definition. If you want the floors as stories rather than as a table, a companion read lives at [adelaidadiazroa.substack.com](https://adelaidadiazroa.substack.com) (English) and [perspectivasblog.substack.com](https://perspectivasblog.substack.com) (Spanish).

---

## Reference

The canonical floor data is in this file. Skills inside the substrate read this table, not their own copies. If you fork the substrate and want to change the floor list, change it here once.

License: MIT. Use the framework. Translate it. Teach it. Ship it. The point is people moving through their own buildings.

---

## Pisos (Español)

El journal etiqueta cada entrada con un Piso: el nivel de consciencia emocional en el que estabas cuando escribiste. Con el tiempo la etiqueta se vuelve infraestructura. Aparecen patrones, los loops reciben nombre, y dejás de sorprenderte con tu propio clima.

### El marco, en un párrafo

Treinta y cuatro pisos de consciencia emocional, de bajo a alto. Derivado de Hawkins (Power vs. Force, 1995), expandido de los dieciséis originales cuando el trabajo pidió más resolución. Piso 1 es Asco. Piso 34 es Paz. Tres tiers: Bajo (1-18, reactivo), Medio (19-24, transicional), Alto (25-34, generativo). Cada piso es real. Cada piso es trabajable. Ninguno es malo. El journal no te pide subir. Te pide saber dónde estás.

### Los 34 pisos

Ver la tabla en inglés arriba (todas las traducciones de los pisos están en la columna Español).

### Emociones-ascensor

Algunas emociones no son pisos sino movimientos entre ellos. El journal etiqueta el piso donde aterrizás; estos nombres describen el viaje.

- **Nostalgia** = Duelo + Amor
- **Asombro mezclado** = Miedo + Asombro
- **Celos** = Miedo + Deseo + Rabia
- **Vulnerabilidad** = Vergüenza subiendo hacia Amor, una escalera tomada paso a paso
- **Agridulce** = Duelo + Alegría
- **Sobrecarga** = cualquier piso inundándose (falla de capacidad)

### Gemelos sombra

Un piso bajo disfrazado de su gemelo alto. El journal te pide nombrar cuál es. El error es la lección.

| Sombra (Bajo) | Piso verdadero (Alto) | Cómo se distingue |
|---|---|---|
| Resignación (6) | Aceptación (23) | "Me rendí" vs. "Hice las paces" |
| Apatía (5) | Neutralidad (21) | "No me importa" vs. "No estoy enganchada" |
| Deseo (15) | Amor (29) | "Quiero de vos" vs. "Te doy" |
| Orgullo (18) | Confianza | "Necesito que me veas" vs. "Yo me veo" |

### Cómo lo usa el journal

La skill `daily-journal` hace una pregunta al final de cada entrada: ¿dónde estuviste hoy? La respuesta se guarda en el frontmatter:

```yaml
floor: Esperanza
floor_level: Middle
```

Esa etiqueta es la semilla. Con el tiempo te dice en qué pisos pasás más tiempo, cuáles ciclás, en qué loops estás. La skill `patterns` lo lee. La skill `insights` lo lee. La skill `coaching` lo lee. La skill `rise` lee el piso de ayer para elegir el movimiento corporal de hoy.

### Si no usás el journal

No necesitás la instalación para que los pisos sean útiles. Tres ejercicios que funcionan solos:

1. **Nombrá el piso antes de reaccionar.** Cuando sentís algo duro, primero nombrá qué piso es. El nombrarlo ya reduce la carga. Estás en Frustración, no sos Frustración.
2. **Chequeá los gemelos sombra.** Cuando un piso alto aparece muy fácil, preguntá si la sombra está disfrazada. La mayoría de "Aceptación" es Resignación. La mayoría de "Confianza" es Orgullo. La diferencia es si todavía estás tensa.
3. **Mirá ascensores, no sólo pisos.** ¿Qué te llevó de un piso a otro? Una caminata. Una conversación. Una comida. Una reunión. Los ascensores son la verdadera lección; los pisos son donde el ascensor abre la puerta.

### Forma narrativa

Estos pisos empezaron como un proyecto de escritura, donde cada uno tiene un capítulo de experiencia vivida en vez de una definición de una línea. Si querés los pisos como historias en vez de como tabla, una lectura complementaria vive en [perspectivasblog.substack.com](https://perspectivasblog.substack.com) (español) y [adelaidadiazroa.substack.com](https://adelaidadiazroa.substack.com) (inglés).
