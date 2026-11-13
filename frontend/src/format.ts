import { activeLocale, tActive } from './i18n/i18n'
import { kgToUnit } from './units'
import type { WeightUnit } from './units'

/**
 * The local calendar day as YYYY-MM-DD.
 *
 * Not toISOString(): that gives the UTC day, which in Romania is still
 * "yesterday" between midnight and 02:00/03:00.
 */
export function localDateString(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Move a YYYY-MM-DD day by a number of days, in local time. */
export function shiftDate(day: string, days: number): string {
  const [year, month, date] = day.split('-').map(Number)
  // new Date(y, m, d) is local time and rolls over months and years for us
  return localDateString(new Date(year, month - 1, date + days))
}

/** Numbers in the active language: "61.25" in English, "61,25" in Romanian. */
function numberFormat(maximumFractionDigits: number): Intl.NumberFormat {
  return new Intl.NumberFormat(activeLocale(), { maximumFractionDigits })
}

export function formatKcal(value: number): string {
  return numberFormat(0).format(value)
}

export function formatDecimal(value: number): string {
  return numberFormat(1).format(value)
}

/**
 * A YYYY-MM-DD day as a local Date, at local midnight.
 *
 * Not new Date(day): that reads a bare date as UTC midnight, which west of
 * UTC is still the previous local day.
 */
export function parseDay(day: string): Date {
  const [year, month, date] = day.split('-').map(Number)
  return new Date(year, month - 1, date)
}

/**
 * The day between Today's arrows: "Today, 12 Nov", "Yesterday, 11 Nov",
 * "Tomorrow, 13 Nov", else "Tue, 10 Nov"; in Romanian "Azi, 12 nov.".
 * Day before month in English too (en-GB), as in the rest of the app.
 */
export function formatDayLabel(
  day: string,
  today: string,
  words: { today: string; yesterday: string; tomorrow: string },
): string {
  const locale = activeLocale() === 'en' ? 'en-GB' : activeLocale()
  const date = parseDay(day)
  const dayMonth = date.toLocaleDateString(locale, { day: 'numeric', month: 'short' })
  const word =
    day === today
      ? words.today
      : day === shiftDate(today, -1)
        ? words.yesterday
        : day === shiftDate(today, 1)
          ? words.tomorrow
          : date.toLocaleDateString(locale, { weekday: 'short' })
  return `${word}, ${dayMonth}`
}

/**
 * A day in a list: "Wed 11 Nov" / "mie. 11 nov.", with the year only
 * when it is not the current one ("Fri 6 Dec 2025").
 */
export function formatShortDay(day: string, today: string = localDateString()): string {
  const locale = activeLocale() === 'en' ? 'en-GB' : activeLocale()
  const date = parseDay(day)
  const sameYear = day.slice(0, 4) === today.slice(0, 4)
  // Weekday and date apart: ICU adds a comma before them only with a year
  const weekday = date.toLocaleDateString(locale, { weekday: 'short' })
  const dayMonth = date.toLocaleDateString(locale, {
    day: 'numeric',
    month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
  })
  return `${weekday} ${dayMonth}`
}

export function formatDay(day: string): string {
  return parseDay(day).toLocaleDateString(activeLocale(), {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function formatWeight(kg: number): string {
  // Two decimals: plates go down to 1.25 kg, so 61.25 must not become 61.3
  return numberFormat(2).format(kg)
}

/** A weight stored in kilograms, shown in the unit: "60 kg" or "132.28 lb". */
export function formatWeightIn(kg: number, unit: WeightUnit): string {
  return `${formatWeight(kgToUnit(kg, unit))} ${unit}`
}

/** One set as "8 × 60 kg" (or in lb); weight 0 means a bodyweight set. */
export function formatSet(reps: number, weightKg: number, unit: WeightUnit = 'kg'): string {
  return weightKg === 0
    ? `${reps} × ${tActive('common.bodyweight')}`
    : `${reps} × ${formatWeightIn(weightKg, unit)}`
}

/** One planned exercise as "3 × 8 × 60 kg": sets × reps × weight. */
export function formatPlanned(
  sets: number,
  reps: number,
  weightKg: number,
  unit: WeightUnit = 'kg',
): string {
  return `${sets} × ${formatSet(reps, weightKg, unit)}`
}

/** The text on one line, cut to at most max characters with an ellipsis. */
export function shorten(text: string, max: number): string {
  const line = text.replace(/\s+/g, ' ').trim()
  return line.length <= max ? line : `${line.slice(0, max - 1).trimEnd()}…`
}
