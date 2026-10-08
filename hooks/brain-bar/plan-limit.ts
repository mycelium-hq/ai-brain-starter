// Plan-limit facts for the brain-bar band: the warning at 80% of a plan
// window, and the person's own switch to a lighter model for the rest of the
// session. Pure: hooks/register.tsx reads `session.measure` and `turn.step`
// and hands the values in here. Nothing here switches a model; the switch is
// state that only the button's press writes.

export const WARN_AT_PERCENT = 80

// The first request on another model re-reads the whole conversation
// uncached (each model keeps its own prompt cache), so with this little time
// left before the window resets, switching costs more than it saves: the
// warning stays, the button does not.
export const MIN_MINUTES_TO_SWITCH = 15

export type Locale = 'es' | 'en'
export type Family = 'opus' | 'sonnet' | 'haiku'

export type RateWindow = { kind: string; percentUsed: number; resetsAt?: string }

const RANK: Record<Family, number> = { haiku: 1, sonnet: 2, opus: 3 }
const LIGHTER: Partial<Record<Family, Family>> = { opus: 'sonnet', sonnet: 'haiku' }
const LABEL: Record<Family, string> = { opus: 'Opus', sonnet: 'Sonnet', haiku: 'Haiku' }

export const familyOf = (model: string | null | undefined): Family | null => {
  const id = (model ?? '').toLowerCase()
  if (id.includes('opus')) return 'opus'
  if (id.includes('sonnet')) return 'sonnet'
  if (id.includes('haiku')) return 'haiku'
  return null
}

export const familyLabel = (model: string | null | undefined): string | null => {
  const family = familyOf(model)
  return family ? LABEL[family] : null
}

// The lighter sibling of the model a request names, as a full id: a request
// refuses an alias ("sonnet" fails as an unrecognized model), so the family
// word is swapped inside the id the engine resolved, keeping its version and
// any context suffix (claude-opus-5-5[1m] -> claude-sonnet-5-5[1m]). That is
// how this build resolves the aliases itself. An id with no known family has
// no lighter sibling.
export const lighterOf = (model: string): string | null => {
  const family = familyOf(model)
  const target = family ? LIGHTER[family] : undefined
  if (!family || !target) return null
  return model.replace(new RegExp(family, 'i'), target)
}

// The model a step of the switched session is sent to: never a heavier one.
// A subagent already on the target's tier or lighter keeps its own model, and
// an id with no known family is left alone.
export const switchedModelFor = (stepModel: string, target: string): string => {
  const from = familyOf(stepModel)
  const to = familyOf(target)
  if (!from || !to || RANK[from] <= RANK[to]) return stepModel
  return stepModel.replace(new RegExp(from, 'i'), to)
}

type Effort = 'low' | 'medium' | 'high' | 'xhigh' | 'max' | number

// A switched step asks for at most `high`: the lighter tier is chosen to
// spend less of the plan, and the top effort levels are where that spend is.
export const switchedEffortFor = (effort: Effort | undefined): Effort | undefined =>
  effort === 'xhigh' || effort === 'max' ? 'high' : effort

// The window to warn about: the fullest one at or past the line, a tie going
// to the one that resets later (it binds longer).
export const windowToWarn = (windows: readonly RateWindow[]): RateWindow | null => {
  let pick: RateWindow | null = null
  for (const window of windows) {
    if (!(window.percentUsed >= WARN_AT_PERCENT)) continue
    const isFuller = pick === null || window.percentUsed > pick.percentUsed
    const isTieLater = pick !== null && window.percentUsed === pick.percentUsed && (window.resetsAt ?? '') > (pick.resetsAt ?? '')
    if (isFuller || isTieLater) pick = window
  }
  return pick
}

export const minutesUntil = (resetsAt: string | undefined, nowMs: number): number | null => {
  if (resetsAt === undefined) return null
  const at = Date.parse(resetsAt)
  return Number.isNaN(at) ? null : Math.max(0, Math.ceil((at - nowMs) / 60_000))
}

export const canOfferSwitch = (window: RateWindow, nowMs: number): boolean => {
  const minutes = minutesUntil(window.resetsAt, nowMs)
  return minutes === null || minutes >= MIN_MINUTES_TO_SWITCH
}

const windowName = (kind: string, locale: Locale): string => {
  const es: Record<string, string> = {
    five_hour: 'tu límite de 5 horas',
    seven_day: 'tu límite semanal',
    seven_day_opus: 'tu límite semanal de Opus',
    seven_day_sonnet: 'tu límite semanal de Sonnet',
    spend_limit: 'tu límite de gasto',
  }
  const en: Record<string, string> = {
    five_hour: 'your 5-hour limit',
    seven_day: 'your weekly limit',
    seven_day_opus: 'your weekly Opus limit',
    seven_day_sonnet: 'your weekly Sonnet limit',
    spend_limit: 'your spend limit',
  }
  return (locale === 'es' ? es : en)[kind] ?? (locale === 'es' ? 'uno de tus límites del plan' : 'one of your plan limits')
}

// "1 h 20 min", "45 min", "3 días" / "1h 20m", "45m", "3 days".
export const durationText = (minutes: number, locale: Locale): string => {
  if (minutes >= 24 * 60) {
    const days = Math.round(minutes / (24 * 60))
    if (locale === 'es') return days === 1 ? '1 día' : `${days} días`
    return days === 1 ? '1 day' : `${days} days`
  }
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (locale === 'es') return hours === 0 ? `${rest} min` : rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
  return hours === 0 ? `${rest}m` : rest === 0 ? `${hours}h` : `${hours}h ${rest}m`
}

const percentText = (percent: number): string => `${Math.floor(percent)}%`

export const warningText = (window: RateWindow, nowMs: number, locale: Locale): string => {
  const name = windowName(window.kind, locale)
  const isOut = window.percentUsed >= 100
  const minutes = minutesUntil(window.resetsAt, nowMs)
  const head =
    locale === 'es'
      ? isOut ? `Llegaste a ${name}.` : `Llevas el ${percentText(window.percentUsed)} de ${name}.`
      : isOut ? `You reached ${name}.` : `You've used ${percentText(window.percentUsed)} of ${name}.`
  if (minutes === null) return head
  const when = durationText(minutes, locale)
  return `${head} ${locale === 'es' ? `Se renueva en ${when}.` : `Resets in ${when}.`}`
}

export const switchLabel = (target: string, locale: Locale): string => {
  const name = familyLabel(target) ?? target
  return locale === 'es' ? `Seguir con ${name}, gasta menos` : `Continue with ${name}, uses less`
}

export const undoLabel = (from: string, locale: Locale): string => {
  const name = familyLabel(from) ?? from
  return locale === 'es' ? `Volver a ${name}` : `Back to ${name}`
}

// The status fact while the switch is on, from what the API reported, never
// from the intent: before the first switched answer it is still changing.
export const switchStatusText = (target: string, answeredModel: string | null, locale: Locale): string => {
  const wanted = familyLabel(target) ?? target
  if (answeredModel === null) return locale === 'es' ? `Cambiando a ${wanted}` : `Switching to ${wanted}`
  const actual = familyLabel(answeredModel) ?? answeredModel
  return locale === 'es' ? `Respondiendo con ${actual}` : `Answering with ${actual}`
}

export const revertNotice = (target: string, from: string, locale: Locale): string => {
  const wanted = familyLabel(target) ?? target
  const back = familyLabel(from) ?? from
  return locale === 'es'
    ? `${wanted} no respondió en esta sesión. Seguimos con ${back}.`
    : `${wanted} did not answer in this session. Back on ${back}.`
}
