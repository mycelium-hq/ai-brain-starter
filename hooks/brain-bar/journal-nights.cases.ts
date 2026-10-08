// The journal-night cases every surface that counts nights must pass: the
// brain-bar band here and the Studio journal line (mycelium-studio ports this
// file unchanged). Today is Thursday 2026-10-08 unless a case says otherwise.

import { sortableTime } from './journal'
import type { JournalEntry, JournalSummary } from './journal'

export type NightsCase = {
  name: string
  today?: string
  coveredFrom?: string | null
  entries: JournalEntry[]
  summary: JournalSummary | null
  es: string | null
  en: string | null
  // The same summary with the floor hidden by the person's setting.
  esHidden?: string | null
}

// `time` is the clock time in creationDate; 01:30 belongs to the night before.
const night = (day: string, floor: string | null, time = '22:00', file = `${day}.md`): JournalEntry => ({
  file,
  day,
  at: sortableTime(`${day}T${time}`),
  floor,
})

export const NIGHTS_CASES: NightsCase[] = [
  {
    name: 'no journal at all hides the row',
    entries: [],
    summary: null,
    es: null,
    en: null,
  },
  {
    name: 'tonight only: the floor, no count',
    entries: [night('2026-10-08', 'Valentía')],
    summary: { kind: 'today', floor: 'Valentía', nights: 1, isLowerBound: false },
    es: 'Hoy: Valentía',
    en: 'Today: Valentía',
    esHidden: 'Diario de hoy listo',
  },
  {
    name: 'three nights ending tonight',
    entries: [night('2026-10-06', 'Miedo'), night('2026-10-07', 'Frustración'), night('2026-10-08', 'Valentía')],
    summary: { kind: 'today', floor: 'Valentía', nights: 3, isLowerBound: false },
    es: 'Hoy: Valentía · 3 noches seguidas',
    en: 'Today: Valentía · 3 nights in a row',
    esHidden: '3 noches seguidas con tu diario',
  },
  {
    name: 'not yet tonight: the run is still alive through last night',
    entries: [night('2026-10-05', 'Miedo'), night('2026-10-06', 'Calma'), night('2026-10-07', 'Calma')],
    summary: { kind: 'last-night', floor: 'Calma', nights: 3, isLowerBound: false },
    es: 'Anoche: Calma · 3 noches seguidas',
    en: 'Last night: Calma · 3 nights in a row',
    esHidden: '3 noches seguidas con tu diario',
  },
  {
    name: 'last night alone',
    entries: [night('2026-10-07', 'Esperanza')],
    summary: { kind: 'last-night', floor: 'Esperanza', nights: 1, isLowerBound: false },
    es: 'Anoche: Esperanza',
    en: 'Last night: Esperanza',
    esHidden: 'Anoche escribiste tu diario',
  },
  {
    name: 'a break shows the last night by name, never a zero',
    entries: [night('2026-10-04', 'Miedo'), night('2026-10-05', 'Miedo')],
    summary: { kind: 'earlier', floor: 'Miedo', day: '2026-10-05', daysAgo: 3 },
    es: 'Tu último diario fue el lunes: Miedo',
    en: 'Your last journal was on Monday: Miedo',
    esHidden: 'Tu último diario fue el lunes',
  },
  {
    name: 'two days ago reads as anteayer',
    entries: [night('2026-10-06', 'Duelo')],
    summary: { kind: 'earlier', floor: 'Duelo', day: '2026-10-06', daysAgo: 2 },
    es: 'Tu último diario fue anteayer: Duelo',
    en: 'Your last journal was on Tuesday: Duelo',
  },
  {
    name: 'a week or more ago counts days',
    entries: [night('2026-09-29', 'Orgullo')],
    summary: { kind: 'earlier', floor: 'Orgullo', day: '2026-09-29', daysAgo: 9 },
    es: 'Tu último diario fue hace 9 días: Orgullo',
    en: 'Your last journal was 9 days ago: Orgullo',
  },
  {
    name: 'fourteen quiet days is the last the row shows',
    entries: [night('2026-09-24', 'Paz')],
    summary: { kind: 'earlier', floor: 'Paz', day: '2026-09-24', daysAgo: 14 },
    es: 'Tu último diario fue hace 14 días: Paz',
    en: 'Your last journal was 14 days ago: Paz',
  },
  {
    name: 'after fourteen quiet days the row goes away',
    entries: [night('2026-09-23', 'Paz')],
    summary: null,
    es: null,
    en: null,
  },
  {
    name: 'two entries in one night: the later one is the floor',
    entries: [night('2026-10-08', 'Esperanza', '21:30', 'b.md'), night('2026-10-08', 'Miedo', '09:00', 'a.md')],
    summary: { kind: 'today', floor: 'Esperanza', nights: 1, isLowerBound: false },
    es: 'Hoy: Esperanza',
    en: 'Today: Esperanza',
  },
  {
    name: 'an entry after midnight closes the night it belongs to',
    // The skill files 01:30 on the 8th under the 7th; it was written last.
    entries: [night('2026-10-07', 'Calma', '01:30', 'b.md'), night('2026-10-07', 'Miedo', '22:00', 'a.md')],
    summary: { kind: 'last-night', floor: 'Calma', nights: 1, isLowerBound: false },
    es: 'Anoche: Calma',
    en: 'Last night: Calma',
  },
  {
    name: 'a future-dated entry is ignored',
    entries: [night('2026-10-07', 'Calma'), night('2026-10-09', 'Alegría')],
    summary: { kind: 'last-night', floor: 'Calma', nights: 1, isLowerBound: false },
    es: 'Anoche: Calma',
    en: 'Last night: Calma',
  },
  {
    name: 'a fresh read of a file replaces the index copy',
    entries: [
      { file: 'October 2026/x.md', day: '2026-10-08', at: '', floor: 'Miedo' },
      { file: 'October 2026/x.md', day: '2026-10-08', at: sortableTime('2026-10-08T22:10'), floor: 'Esperanza' },
    ],
    summary: { kind: 'today', floor: 'Esperanza', nights: 1, isLowerBound: false },
    es: 'Hoy: Esperanza',
    en: 'Today: Esperanza',
  },
  {
    name: 'a run that reaches past what was read is a lower bound',
    coveredFrom: '2026-10-06',
    entries: [night('2026-10-05', 'Calma'), night('2026-10-06', 'Calma'), night('2026-10-07', 'Calma'), night('2026-10-08', 'Calma')],
    summary: { kind: 'today', floor: 'Calma', nights: 4, isLowerBound: true },
    es: 'Hoy: Calma · al menos 4 noches seguidas',
    en: 'Today: Calma · at least 4 nights in a row',
  },
  {
    name: 'a gap inside what was read is a real end',
    coveredFrom: '2026-10-01',
    entries: [night('2026-10-03', 'Calma'), night('2026-10-05', 'Calma'), night('2026-10-06', 'Calma'), night('2026-10-07', 'Calma'), night('2026-10-08', 'Calma')],
    summary: { kind: 'today', floor: 'Calma', nights: 4, isLowerBound: false },
    es: 'Hoy: Calma · 4 noches seguidas',
    en: 'Today: Calma · 4 nights in a row',
  },
  {
    name: 'an entry with no floor still counts as a night',
    entries: [night('2026-10-07', null), night('2026-10-08', null)],
    summary: { kind: 'today', floor: null, nights: 2, isLowerBound: false },
    es: '2 noches seguidas con tu diario',
    en: '2 nights in a row with your journal',
  },
  {
    name: 'the run crosses a month and a year',
    today: '2027-01-01',
    entries: [night('2026-12-30', 'Calma'), night('2026-12-31', 'Alegría'), night('2027-01-01', 'Gratitud')],
    summary: { kind: 'today', floor: 'Gratitud', nights: 3, isLowerBound: false },
    es: 'Hoy: Gratitud · 3 noches seguidas',
    en: 'Today: Gratitud · 3 nights in a row',
  },
]
