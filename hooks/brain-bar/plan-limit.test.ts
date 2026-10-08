import { describe, expect, test } from 'claude-code/testing'

import {
  canOfferSwitch,
  durationText,
  familyOf,
  lighterOf,
  minutesUntil,
  switchedEffortFor,
  switchedModelFor,
  switchLabel,
  switchStatusText,
  undoLabel,
  warningText,
  windowToWarn,
} from './plan-limit'

const NOW = Date.parse('2026-10-08T03:00:00Z')
const inMinutes = (minutes: number) => new Date(NOW + minutes * 60_000).toISOString()

describe('which window to warn about', () => {
  test('79.9% is quiet, 80% warns', () => {
    expect(windowToWarn([{ kind: 'five_hour', percentUsed: 79.9 }])).toBeNull()
    expect(windowToWarn([{ kind: 'five_hour', percentUsed: 80 }])?.kind).toBe('five_hour')
  })

  test('the fullest window wins; a tie goes to the one that resets later', () => {
    const five = { kind: 'five_hour', percentUsed: 85, resetsAt: inMinutes(60) }
    const week = { kind: 'seven_day', percentUsed: 91, resetsAt: inMinutes(3 * 24 * 60) }
    expect(windowToWarn([five, week])).toEqual(week)
    expect(windowToWarn([{ ...five, percentUsed: 91 }, week])).toEqual(week)
  })

  test('no readings (an API-key session) means no warning', () => {
    expect(windowToWarn([])).toBeNull()
  })
})

describe('the warning line', () => {
  test('Spanish, with when it resets', () => {
    const window = { kind: 'five_hour', percentUsed: 84.6, resetsAt: inMinutes(80) }
    expect(warningText(window, NOW, 'es')).toBe('Llevas el 84% de tu límite de 5 horas. Se renueva en 1 h 20 min.')
    expect(warningText(window, NOW, 'en')).toBe("You've used 84% of your 5-hour limit. Resets in 1h 20m.")
  })

  test('a weekly window counts days; a spent one says so', () => {
    expect(warningText({ kind: 'seven_day', percentUsed: 92, resetsAt: inMinutes(3 * 24 * 60 + 100) }, NOW, 'es')).toBe(
      'Llevas el 92% de tu límite semanal. Se renueva en 3 días.',
    )
    expect(warningText({ kind: 'spend_limit', percentUsed: 104 }, NOW, 'es')).toBe('Llegaste a tu límite de gasto.')
  })

  test('an unknown window still reads as a plan limit', () => {
    expect(warningText({ kind: 'monthly_thing', percentUsed: 81 }, NOW, 'es')).toBe('Llevas el 81% de uno de tus límites del plan.')
  })

  test('durations', () => {
    expect(durationText(45, 'es')).toBe('45 min')
    expect(durationText(120, 'es')).toBe('2 h')
    expect(durationText(24 * 60, 'es')).toBe('1 día')
    expect(durationText(61, 'en')).toBe('1h 1m')
  })

  test('copy carries no exclamation mark and no em dash', () => {
    const lines = [
      warningText({ kind: 'five_hour', percentUsed: 99, resetsAt: inMinutes(5) }, NOW, 'es'),
      warningText({ kind: 'spend_limit', percentUsed: 120 }, NOW, 'en'),
      switchLabel('claude-sonnet-5-5', 'es'),
      undoLabel('claude-opus-5-5', 'es'),
    ]
    for (const line of lines) expect(line).not.toMatch(/!|—/)
  })
})

describe('the switch button', () => {
  test('hidden when the window resets in under 15 minutes', () => {
    expect(canOfferSwitch({ kind: 'five_hour', percentUsed: 95, resetsAt: inMinutes(14) }, NOW)).toBe(false)
    expect(canOfferSwitch({ kind: 'five_hour', percentUsed: 95, resetsAt: inMinutes(15) }, NOW)).toBe(true)
    expect(canOfferSwitch({ kind: 'spend_limit', percentUsed: 95 }, NOW)).toBe(true)
  })

  test('one step lighter, as a full id, keeping version and context suffix', () => {
    expect(lighterOf('claude-opus-5-5')).toBe('claude-sonnet-5-5')
    expect(lighterOf('claude-opus-5-5[1m]')).toBe('claude-sonnet-5-5[1m]')
    expect(lighterOf('claude-sonnet-5-5')).toBe('claude-haiku-5-5')
    expect(lighterOf('claude-haiku-5-5')).toBeNull()
    expect(lighterOf('claude-fable-5-1')).toBeNull()
    expect(lighterOf('some-gateway-model')).toBeNull()
  })

  test('labels name the outcome', () => {
    expect(switchLabel('claude-sonnet-5-5', 'es')).toBe('Seguir con Sonnet, gasta menos')
    expect(undoLabel('claude-opus-5-5', 'es')).toBe('Volver a Opus')
    expect(undoLabel('claude-opus-5-5', 'en')).toBe('Back to Opus')
  })
})

describe('a switched session never moves a step up', () => {
  test('heavier steps move down to the target tier', () => {
    expect(switchedModelFor('claude-opus-5-5', 'claude-sonnet-5-5')).toBe('claude-sonnet-5-5')
    expect(switchedModelFor('claude-opus-5-5[1m]', 'claude-sonnet-5-5[1m]')).toBe('claude-sonnet-5-5[1m]')
  })

  test('a subagent already on the tier or lighter keeps its model', () => {
    expect(switchedModelFor('claude-sonnet-5-5', 'claude-sonnet-5-5')).toBe('claude-sonnet-5-5')
    expect(switchedModelFor('claude-haiku-5-5', 'claude-sonnet-5-5')).toBe('claude-haiku-5-5')
  })

  test('an unknown model is left alone', () => {
    expect(switchedModelFor('claude-fable-5-1', 'claude-sonnet-5-5')).toBe('claude-fable-5-1')
  })

  test('effort above high comes down to high; the rest is kept', () => {
    expect(switchedEffortFor('max')).toBe('high')
    expect(switchedEffortFor('xhigh')).toBe('high')
    expect(switchedEffortFor('medium')).toBe('medium')
    expect(switchedEffortFor(undefined)).toBeUndefined()
  })

  test('families', () => {
    expect(familyOf('us.anthropic.claude-opus-5-5-v1:0')).toBe('opus')
    expect(familyOf(null)).toBeNull()
  })
})

describe('the status fact reports what answered, never the intent', () => {
  test('before the first switched answer it is still switching', () => {
    expect(switchStatusText('claude-sonnet-5-5', null, 'es')).toBe('Cambiando a Sonnet')
  })

  test('after it, the model the API reported', () => {
    expect(switchStatusText('claude-sonnet-5-5', 'claude-sonnet-5-5', 'es')).toBe('Respondiendo con Sonnet')
    expect(switchStatusText('claude-sonnet-5-5', 'claude-opus-5-5', 'es')).toBe('Respondiendo con Opus')
  })

  test('minutesUntil rounds up and never goes negative', () => {
    expect(minutesUntil(inMinutes(0.5), NOW)).toBe(1)
    expect(minutesUntil(inMinutes(-10), NOW)).toBe(0)
    expect(minutesUntil('not a date', NOW)).toBeNull()
  })
})
