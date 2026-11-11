import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  formatCounts,
  formatDayCount,
  formatPlanned,
  formatSet,
  formatWeight,
  parseDay,
  shorten,
} from './format'

afterEach(() => {
  vi.unstubAllEnvs()
})

// Decimal separators depend on the locale the tests run in: "." or ","

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

describe('formatCounts', () => {
  it('uses singular for one and plural otherwise', () => {
    expect(formatCounts(1, 1)).toBe('1 exercise · 1 set')
    expect(formatCounts(3, 0)).toBe('3 exercises · 0 sets')
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

describe('formatDayCount', () => {
  it('says day for one and days otherwise', () => {
    expect(formatDayCount(1)).toBe('1 day')
    expect(formatDayCount(3)).toBe('3 days')
  })
})

describe('formatPlanned', () => {
  it('writes sets × reps × weight, or bodyweight for 0 kg', () => {
    expect(formatPlanned(3, 8, 60)).toBe('3 × 8 × 60 kg')
    expect(formatPlanned(3, 10, 0)).toBe('3 × 10 × bodyweight')
  })
})
