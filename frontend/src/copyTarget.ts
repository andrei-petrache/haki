import { shiftDate } from './format'

/**
 * Where a meal is copied by default. Seen on another day, the usual wish
 * is to eat it again today; seen on today, to log it ahead for tomorrow.
 * The meal stays the same: breakfast is copied to breakfast.
 */
export function defaultCopyDay(day: string, today: string): string {
  return day === today ? shiftDate(today, 1) : today
}
