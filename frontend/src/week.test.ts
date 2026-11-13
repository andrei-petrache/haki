import { describe, expect, it } from 'vitest'
import { change, mondayOf, muscleRows, weekLabel } from './week'

describe('the week of a day', () => {
  it('starts on Monday, Sunday included in the week before it', () => {
    expect(mondayOf('2026-11-13')).toBe('2026-11-09') // Friday
    expect(mondayOf('2026-11-09')).toBe('2026-11-09') // Monday
    expect(mondayOf('2026-11-15')).toBe('2026-11-09') // Sunday
    expect(mondayOf('2026-11-02')).toBe('2026-11-02')
  })

  it('reads "9 – 15 Nov", the month on both ends across two months', () => {
    expect(weekLabel('2026-11-09')).toBe('9 – 15 Nov')
    expect(weekLabel('2026-10-26')).toBe('26 Oct – 1 Nov')
  })
})

describe('change from last week', () => {
  it('is the difference, or null without both weeks', () => {
    expect(change(2100, 1950)).toBe(150)
    expect(change(1800, null)).toBeNull()
    expect(change(null, 1800)).toBeNull()
  })
})

describe('muscleRows', () => {
  it('drops empty muscles, sorts the rest, keeps "other" last', () => {
    expect(muscleRows({ other: 5000, chest: 1200, lats: 3400, calves: 0 }).map((r) => r.muscle)).toEqual([
      'lats',
      'chest',
      'other',
    ])
  })
})
