import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  formatDayLabel,
  formatPlanned,
  formatSet,
  formatWeight,
  formatWeightIn,
  parseDay,
  shorten,
} from './format'
import { setActiveLocale } from './i18n/i18n'

afterEach(() => {
  vi.unstubAllEnvs()
})

// Numbers follow the active language, English unless a test sets another

describe('formatWeight', () => {
  it('keeps two decimals, so 1.25 kg plates show', () => {
    expect(formatWeight(61.25)).toMatch(/^61[.,]25$/)
  })

  it('rounds away float noise', () => {
    expect(formatWeight(22.499999)).toMatch(/^22[.,]5$/)
  })

  it('shows whole kilograms without decimals', () => {
    expect(formatWeight(60)).toBe('60')
  })
})

describe('formatSet', () => {
  it('shows reps and weight', () => {
    expect(formatSet(8, 60)).toBe('8 × 60 kg')
  })

  it('shows weight 0 as bodyweight', () => {
    expect(formatSet(12, 0)).toBe('12 × bodyweight')
  })
})

describe('parseDay', () => {
  it('keeps the same day west of UTC, unlike new Date(day)', () => {
    vi.stubEnv('TZ', 'America/New_York')

    const date = parseDay('2026-11-02')

    expect(new Date('2026-11-02').getDate()).toBe(1) // the bug it avoids
    expect([date.getFullYear(), date.getMonth(), date.getDate()]).toEqual([2026, 10, 2])
  })
})

describe('shorten', () => {
  it('leaves short text alone', () => {
    expect(shorten('Leg day', 10)).toBe('Leg day')
  })

  it('cuts long text to max characters with an ellipsis', () => {
    const result = shorten('Heavy squats then accessories', 12)

    expect(result).toBe('Heavy squat…')
    expect(result).toHaveLength(12)
  })

  it('puts a multi-line note on one line', () => {
    expect(shorten('Push day\n\nfelt strong', 40)).toBe('Push day felt strong')
  })
})

describe('formatPlanned', () => {
  it('writes sets × reps × weight, or bodyweight for 0 kg', () => {
    expect(formatPlanned(3, 8, 60)).toBe('3 × 8 × 60 kg')
    expect(formatPlanned(3, 10, 0)).toBe('3 × 10 × bodyweight')
  })
})

describe('weights in the chosen unit', () => {
  it('shows a weight stored in kg as kg or lb, with up to 2 decimals', () => {
    expect(formatWeightIn(60, 'kg')).toBe('60 kg')
    expect(formatWeightIn(60, 'lb')).toMatch(/^132[.,]28 lb$/)
    expect(formatWeightIn(27.669, 'lb')).toBe('61 lb')
  })

  it('shows sets and planned exercises in lb, bodyweight staying bodyweight', () => {
    expect(formatSet(5, 61.235, 'lb')).toBe('5 × 135 lb')
    expect(formatSet(10, 0, 'lb')).toBe('10 × bodyweight')
    expect(formatPlanned(3, 5, 61.235, 'lb')).toBe('3 × 5 × 135 lb')
  })

  it('stays in kg when no unit is given', () => {
    expect(formatSet(8, 60)).toBe('8 × 60 kg')
    expect(formatPlanned(3, 8, 60)).toBe('3 × 8 × 60 kg')
  })
})

describe('formatDayLabel', () => {
  const words = { today: 'Today', yesterday: 'Yesterday', tomorrow: 'Tomorrow' }

  it('names today, yesterday and tomorrow, day before month', () => {
    setActiveLocale('en')
    expect(formatDayLabel('2026-11-12', '2026-11-12', words)).toBe('Today, 12 Nov')
    expect(formatDayLabel('2026-11-11', '2026-11-12', words)).toBe('Yesterday, 11 Nov')
    expect(formatDayLabel('2026-11-13', '2026-11-12', words)).toBe('Tomorrow, 13 Nov')
    expect(formatDayLabel('2026-11-10', '2026-11-12', words)).toBe('Tue, 10 Nov')
  })

  it('in Romanian', () => {
    setActiveLocale('ro')
    expect(formatDayLabel('2026-11-12', '2026-11-12', { today: 'Azi', yesterday: 'Ieri', tomorrow: 'Mâine' })).toBe(
      'Azi, 12 nov.',
    )
    setActiveLocale('en')
  })
})
