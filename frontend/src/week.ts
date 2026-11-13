/**
 * The weekly dashboard without React: which week a day falls in, its
 * label, the change from last week, and the muscles' names.
 */
import { parseDay, shiftDate } from './format'
import { activeLocale } from './i18n/i18n'
import type { MessageKey } from './i18n/i18n'

/** The Monday of a day's week (weeks start on Monday, as on the server). */
export function mondayOf(day: string): string {
  const weekday = parseDay(day).getDay() // 0 = Sunday
  return shiftDate(day, weekday === 0 ? -6 : 1 - weekday)
}

/** "10 – 16 Nov", or "27 Oct – 2 Nov" across months, in the UI language. */
export function weekLabel(monday: string): string {
  const locale = activeLocale() === 'en' ? 'en-GB' : activeLocale()
  const start = parseDay(monday)
  const end = parseDay(shiftDate(monday, 6))
  const dayMonth = (date: Date) => date.toLocaleDateString(locale, { day: 'numeric', month: 'short' })
  return start.getMonth() === end.getMonth()
    ? `${start.getDate()} – ${dayMonth(end)}`
    : `${dayMonth(start)} – ${dayMonth(end)}`
}

/** A weekday's short name, for under a bar: "Mon" / "lun.". */
export function weekdayShort(day: string): string {
  const locale = activeLocale() === 'en' ? 'en-GB' : activeLocale()
  return parseDay(day).toLocaleDateString(locale, { weekday: 'short' })
}

/** This week against the last, as a signed difference; null when either is missing (no logged day). */
export function change(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null) return null
  return current - previous
}

export const MUSCLE_KEYS: Record<string, MessageKey> = {
  abdominals: 'muscle.abdominals',
  abductors: 'muscle.abductors',
  adductors: 'muscle.adductors',
  biceps: 'muscle.biceps',
  calves: 'muscle.calves',
  chest: 'muscle.chest',
  forearms: 'muscle.forearms',
  glutes: 'muscle.glutes',
  hamstrings: 'muscle.hamstrings',
  lats: 'muscle.lats',
  'lower back': 'muscle.lowerBack',
  'middle back': 'muscle.middleBack',
  neck: 'muscle.neck',
  quadriceps: 'muscle.quadriceps',
  shoulders: 'muscle.shoulders',
  traps: 'muscle.traps',
  triceps: 'muscle.triceps',
  other: 'muscle.other',
}

/**
 * The muscles with any volume, largest first, "other" always last: it is
 * not a muscle but the user's own exercises, which have none.
 */
export function muscleRows(byMuscle: Record<string, number>): { muscle: string; volume: number }[] {
  return Object.entries(byMuscle)
    .filter(([, volume]) => volume > 0)
    .map(([muscle, volume]) => ({ muscle, volume }))
    .sort((a, b) => {
      if (a.muscle === 'other') return 1
      if (b.muscle === 'other') return -1
      return b.volume - a.volume
    })
}
