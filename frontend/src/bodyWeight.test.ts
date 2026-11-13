import { describe, expect, it } from 'vitest'
import type { WeightPoint } from './api'
import {
  bodyFieldText,
  bodyLimits,
  bodyWeightError,
  bodyWeightToKg,
  chartScale,
  formatBodyWeight,
  GOAL_OPTIONS,
  goalAmount,
  knownReasons,
  nearestPoint,
  niceTicks,
  rangeStart,
  weeklyChange,
} from './bodyWeight'

function point(day: string, weight: number, trend = weight, outlier = false): WeightPoint {
  return { measured_on: day, weight_kg: weight, trend_kg: trend, outlier }
}

describe('limits of a weigh-in', () => {
  it('is 20 to 400 kg, and in pounds cut inwards to 2 decimals', () => {
    expect(bodyLimits('kg')).toEqual({ min: 20, max: 400 })
    expect(bodyLimits('lb')).toEqual({ min: 44.1, max: 881.84 })
    // Both pound limits stay inside the API's kilograms once converted
    expect(bodyWeightToKg('44.1', 'lb')).toBeGreaterThanOrEqual(20)
    expect(bodyWeightToKg('881.84', 'lb')).toBeLessThanOrEqual(400)
  })

  it('refuses blank, text and anything outside, and accepts the limits', () => {
    for (const text of ['', ' ', 'abc', '19.99', '400.01']) expect(bodyWeightError(text, 'kg')).not.toBeNull()
    for (const text of ['20', '82.4', '400']) expect(bodyWeightError(text, 'kg')).toBeNull()
    expect(bodyWeightError('44.09', 'lb')).not.toBeNull()
    expect(bodyWeightError('181.5', 'lb')).toBeNull()
  })

  it('sends pounds as kilograms to the gram, kilograms as typed', () => {
    expect(bodyWeightToKg('82.45', 'kg')).toBe(82.45)
    expect(bodyWeightToKg('180', 'lb')).toBe(81.647)
  })
})

describe('showing a body weight', () => {
  it('keeps kilograms to 0.01 and pounds to 0.1, so 180 lb stored as 81.65 kg reads 180', () => {
    expect(formatBodyWeight(81.65, 'kg')).toBe('81.65 kg')
    expect(formatBodyWeight(81.65, 'lb')).toBe('180 lb')
    expect(bodyFieldText(81.65, 'lb')).toBe('180')
    expect(bodyFieldText(81.2, 'lb')).toBe('179')
    expect(bodyFieldText(81.2, 'kg')).toBe('81.2')
  })
})

describe('weeklyChange', () => {
  it('is the trend over the last 28 days, per week', () => {
    const points = [point('2026-10-01', 90), point('2026-10-30', 84, 84.4), point('2026-11-13', 83, 83.2)]
    // 30 Oct to 13 Nov: 14 days, -1.2 kg, so -0.6 kg a week
    expect(weeklyChange(points)).toBeCloseTo(-0.6, 5)
  })

  it('is null under a week, or with one weigh-in', () => {
    expect(weeklyChange([point('2026-11-10', 82)])).toBeNull()
    expect(weeklyChange([point('2026-11-10', 82), point('2026-11-13', 81)])).toBeNull()
  })
})

describe('the chart', () => {
  it('counts a range back from today, today included', () => {
    expect(rangeStart('2026-11-13', 30)).toBe('2026-10-15')
  })

  it('puts round ticks around the values', () => {
    expect(niceTicks(81.3, 84.9)).toEqual([80, 82, 84, 86])
    expect(niceTicks(60, 95)).toEqual([60, 80, 100])
    // One value: still a scale around it
    expect(niceTicks(82, 82)).toEqual([81, 82, 83])
  })

  it('maps the first day to the left edge, the last to the right, low values down', () => {
    const box = { width: 300, height: 200, left: 40, right: 10, top: 10, bottom: 30 }
    const points = [point('2026-11-01', 82, 82.5), point('2026-11-11', 81, 81.6)]
    const scale = chartScale(points, '2026-11-01', '2026-11-11', 'kg', box)
    expect(scale.x('2026-11-01')).toBe(40)
    expect(scale.x('2026-11-11')).toBe(290)
    expect(scale.y(scale.ticks[0])).toBe(170)
    expect(scale.y(scale.ticks[scale.ticks.length - 1])).toBe(10)
  })

  it('finds the weigh-in nearest a day', () => {
    const points = [point('2026-11-01', 82), point('2026-11-05', 81), point('2026-11-12', 80)]
    expect(nearestPoint(points, '2026-11-04')?.measured_on).toBe('2026-11-05')
    expect(nearestPoint([], '2026-11-04')).toBeNull()
  })
})

describe('the goal and the adaptive target', () => {
  it('offers goals inside the API range, and says them in the unit', () => {
    expect(Math.min(...GOAL_OPTIONS)).toBe(-1)
    expect(Math.max(...GOAL_OPTIONS)).toBe(0.5)
    expect(goalAmount(-0.5, 'kg')).toBe('0.5 kg')
    expect(goalAmount(-0.5, 'lb')).toBe('1.1 lb')
  })

  it('keeps known reasons in a fixed order and drops unknown ones', () => {
    expect(knownReasons(['few_weigh_ins', 'something_new', 'few_days'])).toEqual(['few_days', 'few_weigh_ins'])
  })
})
