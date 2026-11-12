import { describe, expect, it } from 'vitest'
import { defaultCopyDay } from './copyTarget'

describe('defaultCopyDay', () => {
  it('copies an earlier or later day to today', () => {
    expect(defaultCopyDay('2026-11-11', '2026-11-12')).toBe('2026-11-12')
    expect(defaultCopyDay('2026-11-20', '2026-11-12')).toBe('2026-11-12')
  })

  it('copies today to tomorrow, across a month end', () => {
    expect(defaultCopyDay('2026-11-12', '2026-11-12')).toBe('2026-11-13')
    expect(defaultCopyDay('2026-11-30', '2026-11-30')).toBe('2026-12-01')
  })
})
