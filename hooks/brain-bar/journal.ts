// Journal facts for the brain-bar band: today's Floor and the run of
// consecutive nights with a journal entry. Pure: the band hook in
// hooks/register.tsx reads the vault with `$.fs` and hands text in here.
//
// Every rule mirrors what the daily-journal skill writes and what
// scripts/build-journal-index.py reads, so the band never disagrees with the
// journal it summarizes:
//   - the folder is one of build-journal-index.py's JOURNAL_DIR_CANDIDATES,
//     report subfolders (DEFAULT_EXCLUDE_DIRS) skipped, never a fixed path;
//   - a note is an entry when its frontmatter has `creationDate` and its
//     `type` is absent or `journal` (a /rise entry is `type: rise`);
//   - its night is the date part of `creationDate`: the skill already files an
//     entry written before 3:45 a.m. under the previous day;
//   - its floor is `floor:`, plain or a wikilink (alias wins), and a legacy
//     list `[A, B]` reads as its last element, where the day landed.
// The Studio journal line (mycelium-studio) ports this file and runs the same
// cases in journal-nights.cases.json, so the two surfaces count nights alike.

export const JOURNAL_DIR_CANDIDATES = [
  '📓 Journals', 'Journals',
  '📔 Journal', 'Journal',
  '📓 Diarios', 'Diarios',
  '📓 Diario', 'Diario',
  '📓 Diário', 'Diário',
] as const

export const EXCLUDE_DIRS = ['Resúmenes', 'Resumenes', 'Summaries', 'Reports', 'Resumos'] as const

// The skill's day boundary: before 3:45 a.m. it is still the previous night.
export const DAY_START_MINUTES = 3 * 60 + 45

// Without journal-index.json the band reads only notes changed this recently,
// so a run that reaches back further is shown as "at least", never guessed.
export const HORIZON_DAYS = 62

// After this many quiet days the row goes away: a reminder of an old lapse
// does not bring anyone back (Silverman & Barasch, JCR 2023), it only nags.
export const DORMANT_AFTER_DAYS = 14

export type Locale = 'es' | 'en'

export type JournalEntry = {
  // Where it came from, so a fresh read replaces the index's copy of the file.
  file: string
  // The journal night, YYYY-MM-DD.
  day: string
  // Sortable time within the night ('' when the note gives none).
  at: string
  floor: string | null
}

export type JournalSummary =
  | { kind: 'today'; floor: string | null; nights: number; isLowerBound: boolean }
  | { kind: 'last-night'; floor: string | null; nights: number; isLowerBound: boolean }
  | { kind: 'earlier'; floor: string | null; day: string; daysAgo: number }

const WIKILINK = /^\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]$/

const unquote = (value: string): string => value.trim().replace(/^["']|["']$/g, '').trim()

export const stripWikilink = (value: string): string => {
  const clean = unquote(value)
  const match = WIKILINK.exec(clean)
  return match ? (match[2] ?? match[1]).trim() : clean
}

// `floor:` as the skill writes it, or a legacy flow list read by its last item.
export const floorOf = (raw: string | undefined): string | null => {
  if (raw === undefined) return null
  const value = raw.trim()
  if (value.startsWith('[') && value.endsWith(']') && !value.startsWith('[[')) {
    const items = value.slice(1, -1).split(',').map(stripWikilink).filter(item => item !== '')
    return items.length > 0 ? items[items.length - 1] : null
  }
  const floor = stripWikilink(value)
  return floor === '' ? null : floor
}

// The frontmatter block as `key: value` lines, the way build-journal-index.py
// reads it (no YAML library; nested values are not needed here).
export const parseFrontmatter = (text: string): Record<string, string> => {
  const lines = text.split(/\r?\n/)
  const fields: Record<string, string> = {}
  if (lines[0]?.trim() !== '---') return fields
  for (const line of lines.slice(1)) {
    if (line.trim() === '---') return fields
    const cut = line.indexOf(': ')
    if (cut > 0 && !line.startsWith(' ')) fields[line.slice(0, cut).trim()] = unquote(line.slice(cut + 2))
  }
  return {}
}

const DAY = /^(\d{4})-(\d{2})-(\d{2})/
const TIME = /T(\d{2}):(\d{2})/

// An entry before 3:45 a.m. belongs at the end of its night, not the start.
export const sortableTime = (creationDate: string): string => {
  const time = TIME.exec(creationDate)
  if (!time) return ''
  const minutes = Number(time[1]) * 60 + Number(time[2])
  const late = minutes < DAY_START_MINUTES ? minutes + 24 * 60 : minutes
  return String(late).padStart(4, '0')
}

export const entryFromNote = (file: string, text: string): JournalEntry | null => {
  const fields = parseFrontmatter(text)
  if (fields.type !== undefined && fields.type !== 'journal') return null
  const created = fields.creationDate
  if (created === undefined || !DAY.test(created)) return null
  return { file, day: created.slice(0, 10), at: sortableTime(created), floor: floorOf(fields.floor) }
}

// journal-index.json as build-journal-index.py writes it.
export const entriesFromIndex = (json: string): JournalEntry[] => {
  let parsed: unknown
  try {
    parsed = JSON.parse(json)
  } catch {
    return []
  }
  const rows = (parsed as { entries?: unknown }).entries
  if (!Array.isArray(rows)) return []
  const entries: JournalEntry[] = []
  for (const row of rows) {
    if (typeof row !== 'object' || row === null) continue
    const { file, date, floor } = row as { file?: unknown; date?: unknown; floor?: unknown }
    if (typeof file !== 'string' || typeof date !== 'string' || !DAY.test(date)) continue
    entries.push({ file, day: date.slice(0, 10), at: '', floor: typeof floor === 'string' ? floorOf(floor) : null })
  }
  return entries
}

const pad = (n: number): string => String(n).padStart(2, '0')

// The journal night `now` falls in, in local time.
export const journalDayOf = (now: Date): string => {
  const shifted = new Date(now.getTime() - DAY_START_MINUTES * 60_000)
  return `${shifted.getFullYear()}-${pad(shifted.getMonth() + 1)}-${pad(shifted.getDate())}`
}

const utcOf = (day: string): number => {
  const [, y, m, d] = DAY.exec(day) ?? []
  return Date.UTC(Number(y), Number(m) - 1, Number(d))
}

export const shiftDay = (day: string, by: number): string => {
  const date = new Date(utcOf(day) + by * 86_400_000)
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`
}

export const daysBetween = (from: string, to: string): number => Math.round((utcOf(to) - utcOf(from)) / 86_400_000)

export type SummaryOptions = {
  // The night it is now (journalDayOf).
  today: string
  // The first night fully covered; null when journal-index.json covers all.
  coveredFrom: string | null
}

// Fresh reads replace the index's copy of the same file; then one floor per
// night, the last one written that night.
export const summarizeNights = (entries: readonly JournalEntry[], options: SummaryOptions): JournalSummary | null => {
  const byFile = new Map<string, JournalEntry>()
  for (const entry of entries) byFile.set(entry.file, entry)
  const byDay = new Map<string, JournalEntry>()
  for (const entry of byFile.values()) {
    if (entry.day > options.today) continue
    const held = byDay.get(entry.day)
    if (!held || entry.at >= held.at) byDay.set(entry.day, entry)
  }
  if (byDay.size === 0) return null

  const yesterday = shiftDay(options.today, -1)
  const anchor = byDay.has(options.today) ? options.today : byDay.has(yesterday) ? yesterday : null
  if (anchor === null) {
    const last = [...byDay.keys()].sort().at(-1)!
    const daysAgo = daysBetween(last, options.today)
    if (daysAgo > DORMANT_AFTER_DAYS) return null
    return { kind: 'earlier', floor: byDay.get(last)!.floor, day: last, daysAgo }
  }

  let nights = 0
  let day = anchor
  while (byDay.has(day)) {
    nights += 1
    day = shiftDay(day, -1)
  }
  const isLowerBound = options.coveredFrom !== null && day < options.coveredFrom
  const kind = anchor === options.today ? 'today' : 'last-night'
  return { kind, floor: byDay.get(anchor)!.floor, nights, isLowerBound }
}

const WEEKDAYS: Record<Locale, readonly string[]> = {
  es: ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'],
  en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
}

const weekdayOf = (day: string, locale: Locale): string => WEEKDAYS[locale][new Date(utcOf(day)).getUTCDay()]

const nightsText = (nights: number, isLowerBound: boolean, locale: Locale): string | null => {
  if (isLowerBound) return locale === 'es' ? `al menos ${nights} noches seguidas` : `at least ${nights} nights in a row`
  if (nights < 2) return null
  return locale === 'es' ? `${nights} noches seguidas` : `${nights} nights in a row`
}

const whenText = (daysAgo: number, day: string, locale: Locale): string => {
  if (locale === 'es') {
    if (daysAgo === 2) return 'anteayer'
    return daysAgo < 7 ? `el ${weekdayOf(day, locale)}` : `hace ${daysAgo} días`
  }
  return daysAgo < 7 ? `on ${weekdayOf(day, locale)}` : `${daysAgo} days ago`
}

// One status fact. The floor shows by name only (never its level or arc), in
// the same quiet style for every floor; `showFloor: false` leaves it out.
export const journalText = (summary: JournalSummary, locale: Locale, showFloor: boolean): string => {
  const floor = showFloor ? summary.floor : null
  if (summary.kind === 'earlier') {
    const when = whenText(summary.daysAgo, summary.day, locale)
    if (locale === 'es') return floor ? `Tu último diario fue ${when}: ${floor}` : `Tu último diario fue ${when}`
    return floor ? `Your last journal was ${when}: ${floor}` : `Your last journal was ${when}`
  }
  const nights = nightsText(summary.nights, summary.isLowerBound, locale)
  const isToday = summary.kind === 'today'
  let head: string
  if (floor) head = locale === 'es' ? `${isToday ? 'Hoy' : 'Anoche'}: ${floor}` : `${isToday ? 'Today' : 'Last night'}: ${floor}`
  else if (nights) return locale === 'es' ? `${nights} con tu diario` : `${nights} with your journal`
  else head = locale === 'es' ? (isToday ? 'Diario de hoy listo' : 'Anoche escribiste tu diario') : isToday ? "Today's journal is in" : 'You journaled last night'
  return nights ? `${head} · ${nights}` : head
}
