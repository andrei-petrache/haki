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
