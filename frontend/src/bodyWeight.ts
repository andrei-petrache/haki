/**
 * Body weight without React: the limits a weigh-in must keep, in either
 * unit, how fast the trend moves, and the chart's scales and ticks.
 */
import type { WeightPoint } from './api'
import { parseDay, shiftDate } from './format'
import { formatNumber, tActive } from './i18n/i18n'
import { KG_PER_LB, unitToKg } from './units'
import type { WeightUnit } from './units'

// The API's limits for a weigh-in (WeightIn in backend/app/schemas.py)
export const BODY_MIN_KG = 20
export const BODY_MAX_KG = 400

/**
 * The lightest and heaviest weigh-in that can be typed in the unit. In
 * pounds both are cut inwards to 2 decimals (44.1 to 881.84 lb), so a value
 * shown as allowed never lands outside 20 to 400 kg once converted.
 */
export function bodyLimits(unit: WeightUnit): { min: number; max: number } {
  if (unit === 'kg') return { min: BODY_MIN_KG, max: BODY_MAX_KG }
  return {
    min: Math.ceil((BODY_MIN_KG / KG_PER_LB) * 100) / 100,
    max: Math.floor((BODY_MAX_KG / KG_PER_LB) * 100) / 100,
  }
}

/** What is wrong with a typed weigh-in, or null; checked as typed, before conversion. */
export function bodyWeightError(text: string, unit: WeightUnit): string | null {
  const { min, max } = bodyLimits(unit)
  const value = Number(text)
  if (text.trim() === '' || !Number.isFinite(value) || value < min || value > max) {
    return tActive('weight.range', { min: formatNumber(min), max: formatNumber(max), unit })
  }
  return null
}

/**
 * A body weight as shown: kilograms to 0.01 (as stored), pounds to 0.1.
 * The server keeps 10 g steps, so 180 lb comes back as 180.008 lb: at
 * 0.1 lb it reads back as typed. "81.65 kg", "180 lb".
 */
export function formatBodyWeight(kg: number, unit: WeightUnit): string {
  const value = unit === 'kg' ? Math.round(kg * 100) / 100 : Math.round((kg / KG_PER_LB) * 10) / 10
  return `${formatNumber(value)} ${unit}`
}

/** The same as a number input's text: plain digits and a ".". */
export function bodyFieldText(kg: number, unit: WeightUnit): string {
  return unit === 'kg' ? String(Math.round(kg * 100) / 100) : String(Math.round((kg / KG_PER_LB) * 10) / 10)
}

/** The kilograms to send for a valid typed weigh-in. */
export function bodyWeightToKg(text: string, unit: WeightUnit): number {
  return unitToKg(Number(text), unit)
}

function daysBetween(from: string, to: string): number {
  return Math.round((parseDay(to).getTime() - parseDay(from).getTime()) / 86_400_000)
}

/**
 * How fast the trend moves, in kg a week: from the trend at the first
 * weigh-in of the last 28 days to the latest. Null with less than a week
 * between them, where a number would mostly be noise.
 */
export function weeklyChange(points: WeightPoint[]): number | null {
  if (points.length < 2) return null
  const last = points[points.length - 1]
  const first = points.find((point) => daysBetween(point.measured_on, last.measured_on) <= 28)!
  const days = daysBetween(first.measured_on, last.measured_on)
  if (days < 7) return null
  return ((last.trend_kg - first.trend_kg) / days) * 7
}

/** The first day of a range ending today: the last 30 days include today. */
export function rangeStart(today: string, days: number): string {
  return shiftDate(today, -(days - 1))
}

/**
 * Round numbers for an axis between min and max: steps of 1, 2 or 5 times a
 * power of ten, about `count` of them, covering both ends.
 */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!(max > min)) return [Math.floor(min) - 1, Math.floor(min), Math.floor(min) + 1]
  const raw = (max - min) / Math.max(1, count - 1)
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw)!
  const start = Math.floor(min / step) * step
  const ticks: number[] = []
  for (let value = start; value < max + step - 1e-9; value += step) {
    ticks.push(Math.round(value * 1e6) / 1e6)
  }
  return ticks
}

export type ChartBox = { width: number; height: number; left: number; right: number; top: number; bottom: number }

export type ChartScale = {
  x: (day: string) => number
  y: (value: number) => number
  ticks: number[]
}

/**
 * The scales for the chart: days from `from` to `to` across, the weights
 * (weigh-ins and trend, in the unit) up, on round ticks with some air.
 */
export function chartScale(points: WeightPoint[], from: string, to: string, unit: WeightUnit, box: ChartBox): ChartScale {
  const toUnit = (kg: number) => (unit === 'kg' ? kg : kg / KG_PER_LB)
  const values = points.flatMap((point) => [toUnit(point.weight_kg), toUnit(point.trend_kg)])
  const ticks = niceTicks(Math.min(...values), Math.max(...values))
  const low = ticks[0]
  const high = ticks[ticks.length - 1]
  const span = Math.max(1, daysBetween(from, to))
  const innerWidth = box.width - box.left - box.right
  const innerHeight = box.height - box.top - box.bottom
  return {
    x: (day) => box.left + (daysBetween(from, day) / span) * innerWidth,
    y: (value) => box.top + (1 - (value - low) / (high - low)) * innerHeight,
    ticks,
  }
}

/** The weigh-in nearest a day, for the tooltip under a pointer. */
export function nearestPoint(points: WeightPoint[], day: string): WeightPoint | null {
  let best: WeightPoint | null = null
  let distance = Infinity
  for (const point of points) {
    const d = Math.abs(daysBetween(point.measured_on, day))
    if (d < distance) {
      best = point
      distance = d
    }
  }
  return best
}

/** The goals offered, in kg a week: the API takes -1 to 0.5. */
export const GOAL_OPTIONS = [-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5] as const

/** A goal's amount in the unit, without its sign: "0.5 kg", "1.1 lb". */
export function goalAmount(kgPerWeek: number, unit: WeightUnit): string {
  const value = unit === 'kg' ? Math.abs(kgPerWeek) : Math.round((Math.abs(kgPerWeek) / KG_PER_LB) * 10) / 10
  return `${formatNumber(value)} ${unit}`
}

const REASONS = [
  'few_days',
  'few_weigh_ins',
  'few_logged_days',
  'no_weigh_ins_at_start',
  'no_weigh_ins_at_end',
] as const

/** What the adaptive target still waits for, as known reasons in a fixed order; unknown ones are left out. */
export function knownReasons(reasons: string[]): (typeof REASONS)[number][] {
  return REASONS.filter((reason) => reasons.includes(reason))
}
