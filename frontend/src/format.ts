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

const kcalFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })
const decimalFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })

export function formatKcal(value: number): string {
  return kcalFormat.format(value)
}

export function formatDecimal(value: number): string {
  return decimalFormat.format(value)
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

export function formatDay(day: string): string {
  return parseDay(day).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

// Two decimals: plates go down to 1.25 kg, so 61.25 must not become 61.3
const weightFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })

export function formatWeight(kg: number): string {
  return weightFormat.format(kg)
}

/** One set as "8 × 60 kg"; weight 0 means a bodyweight set. */
export function formatSet(reps: number, weightKg: number): string {
  return weightKg === 0
    ? `${reps} × bodyweight`
    : `${reps} × ${formatWeight(weightKg)} kg`
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

/** "3 exercises · 12 sets", for a workout in the list. */
export function formatCounts(exercises: number, sets: number): string {
  return `${plural(exercises, 'exercise')} · ${plural(sets, 'set')}`
}

/** The text on one line, cut to at most max characters with an ellipsis. */
export function shorten(text: string, max: number): string {
  const line = text.replace(/\s+/g, ' ').trim()
  return line.length <= max ? line : `${line.slice(0, max - 1).trimEnd()}…`
}
