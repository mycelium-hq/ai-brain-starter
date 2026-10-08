import { describe, expect, test } from 'claude-code/testing'

import {
  entriesFromIndex,
  entryFromNote,
  floorOf,
  journalDayOf,
  journalText,
  parseFrontmatter,
  shiftDay,
  summarizeNights,
} from './journal'
import { NIGHTS_CASES } from './journal-nights.cases'

describe('journal nights (cases shared with the Studio journal line)', () => {
  for (const each of NIGHTS_CASES) {
    test(each.name, () => {
      const summary = summarizeNights(each.entries, {
        today: each.today ?? '2026-10-08',
        coveredFrom: each.coveredFrom ?? null,
      })
      expect(summary).toEqual(each.summary)
      expect(summary === null ? null : journalText(summary, 'es', true)).toBe(each.es)
      expect(summary === null ? null : journalText(summary, 'en', true)).toBe(each.en)
      if (each.esHidden !== undefined) {
        expect(summary === null ? null : journalText(summary, 'es', false)).toBe(each.esHidden)
      }
    })
  }

  test('the floor is never shown with its level, arc or a color word', () => {
    for (const each of NIGHTS_CASES) {
      for (const text of [each.es, each.en, each.esHidden]) {
        if (typeof text !== 'string') continue
        expect(text).not.toMatch(/Low|Middle|High|Bajo|Medio|Alto|!|—/)
      }
    }
  })
})

describe('reading a journal note the way build-journal-index.py does', () => {
  const note = (frontmatter: string, body = 'Hoy fue un día largo.') => `---\n${frontmatter}\n---\n\n${body}\n`

  test('a journal entry: night, time and floor', () => {
    const text = note('type: journal\ncreationDate: 2026-10-08T21:40\nfloor: "[[Courage|Valentía]]"\nfloor_level: Middle')
    expect(entryFromNote('October 2026/x.md', text)).toEqual({
      file: 'October 2026/x.md',
      day: '2026-10-08',
      at: '1300',
      floor: 'Valentía',
    })
  })

  test('an entry with no type still counts (written before the template had one)', () => {
    expect(entryFromNote('a.md', note('creationDate: 2026-04-11\nfloor: Fear'))?.day).toBe('2026-04-11')
  })

  test('a /rise entry or a report is not a journal night', () => {
    expect(entryFromNote('r.md', note('type: rise\ncreationDate: 2026-10-08T07:00\nfloor: Hope'))).toBeNull()
    expect(entryFromNote('w.md', note('type: insight\ncreationDate: 2026-10-05'))).toBeNull()
  })

  test('no creationDate, or frontmatter that never closes, is not an entry', () => {
    expect(entryFromNote('a.md', note('type: journal\nfloor: Fear'))).toBeNull()
    expect(entryFromNote('a.md', '---\ntype: journal\ncreationDate: 2026-10-08\nfloor: Fear\n')).toBeNull()
    expect(entryFromNote('a.md', 'creationDate: 2026-10-08\n')).toBeNull()
  })

  test('an indented key never overrides the top-level floor', () => {
    const text = note('creationDate: 2026-10-08\nfloor: Calma\nbody_check:\n  floor: no')
    expect(entryFromNote('a.md', text)?.floor).toBe('Calma')
    expect(parseFrontmatter(text).floor).toBe('Calma')
  })

  test('floor spellings: plain, wikilink, alias, quoted, legacy list, empty', () => {
    expect(floorOf('Courage')).toBe('Courage')
    expect(floorOf('[[Fear]]')).toBe('Fear')
    expect(floorOf('"[[Acceptance|Aceptación]]"')).toBe('Aceptación')
    expect(floorOf("'Hope'")).toBe('Hope')
    expect(floorOf('[Fear, [[Frustration]], Hope]')).toBe('Hope')
    expect(floorOf('')).toBeNull()
    expect(floorOf(undefined)).toBeNull()
  })

  test('journal-index.json rows become nights; malformed rows are skipped', () => {
    const json = JSON.stringify({
      total: 3,
      entries: [
        { file: 'September 2026/a.md', date: '2026-09-30', floor: 'Fear' },
        { file: 'October 2026/b.md', date: '2026-10-01' },
        { date: '2026-10-02', floor: 'Hope' },
        'not a row',
      ],
    })
    expect(entriesFromIndex(json)).toEqual([
      { file: 'September 2026/a.md', day: '2026-09-30', at: '', floor: 'Fear' },
      { file: 'October 2026/b.md', day: '2026-10-01', at: '', floor: null },
    ])
    expect(entriesFromIndex('{ not json')).toEqual([])
    expect(entriesFromIndex('{"entries": 4}')).toEqual([])
  })
})

describe('the journal night follows the skill: 3:45 a.m. starts a new day', () => {
  test('before 3:45 a.m. it is still last night', () => {
    expect(journalDayOf(new Date(2026, 9, 8, 2, 0))).toBe('2026-10-07')
    expect(journalDayOf(new Date(2026, 9, 8, 3, 44))).toBe('2026-10-07')
  })

  test('from 3:45 a.m. it is the new day', () => {
    expect(journalDayOf(new Date(2026, 9, 8, 3, 45))).toBe('2026-10-08')
    expect(journalDayOf(new Date(2026, 9, 8, 23, 59))).toBe('2026-10-08')
  })

  test('days step across months, years and a leap day', () => {
    expect(shiftDay('2026-10-01', -1)).toBe('2026-09-30')
    expect(shiftDay('2027-01-01', -1)).toBe('2026-12-31')
    expect(shiftDay('2028-03-01', -1)).toBe('2028-02-29')
  })
})
