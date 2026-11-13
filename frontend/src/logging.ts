/**
 * The rules of logging food on Today, without React: which meal a new
 * entry goes to, how a food is named in the UI language, the quantity a
 * pick starts from, the stepper, and the day's headline number.
 */
import type { DailySummary, MealType } from './api'
import type { Locale, MessageKey } from './i18n/i18n'

export const MEAL_LABELS: Record<MealType, MessageKey> = {
  breakfast: 'meal.breakfast',
  lunch: 'meal.lunch',
  dinner: 'meal.dinner',
  snack: 'meal.snack',
}

/** The meal an entry made now most likely belongs to, by the local hour. */
export function mealForHour(hour: number): MealType {
  if (hour < 11) return 'breakfast'
  if (hour < 16) return 'lunch'
  if (hour < 21) return 'dinner'
  return 'snack'
}

type Named = { name: string; catalog_name?: string | null; catalog_name_ro?: string | null }

/**
 * A food's name in the UI language. A copy from the catalog shows the
 * catalog's name in that language, unless the user renamed it: then their
 * name differs from both catalog names, and it wins. Typed by hand: as is.
 */
export function displayName(food: Named, locale: Locale): string {
  const en = food.catalog_name ?? null
  const ro = food.catalog_name_ro ?? null
  if (en === null && ro === null) return food.name
  if (food.name !== en && food.name !== ro) return food.name
  if (locale === 'ro') return ro ?? en ?? food.name
  return en ?? food.name
}

/** The same, for an entry: its food's name is food_name. */
export function entryName(
  entry: { food_name: string; catalog_name?: string | null; catalog_name_ro?: string | null },
  locale: Locale,
): string {
  return displayName({ ...entry, name: entry.food_name }, locale)
}

/** Text compared loosely: case, accents and Romanian diacritics ignored. */
function folded(text: string): string {
  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim()
}

/** Whether a name holds every word of a filter, in any order ("iaurt gre" finds "Iaurt grecesc"). */
export function matchesFilter(name: string, filter: string): boolean {
  const words = folded(filter).split(/\s+/).filter(Boolean)
  const haystack = folded(name)
  return words.every((word) => haystack.includes(word))
}

/**
 * Keep a list in the order first seen: items already known keep their
 * place, new ones go to the end. Today's chips use it, so the chip just
 * used does not jump to the front while the user is on the page.
 */
export function keepOrder<T extends { id: number }>(list: T[], order: number[]): T[] {
  const place = new Map(order.map((id, index) => [id, index]))
  const known = list.filter((item) => place.has(item.id)).sort((a, b) => place.get(a.id)! - place.get(b.id)!)
  return [...known, ...list.filter((item) => !place.has(item.id))]
}

/** Grams a pick starts from: as last time, else 100 g. */
export function startGrams(last: { grams: number } | null | undefined): number {
  return last ? last.grams : 100
}

export const GRAMS_STEP = 10
export const MAX_GRAMS = 5000

/** The stepper: to the next multiple of 10 g up or down, never below 10 g. */
export function stepGrams(grams: number, direction: 1 | -1): number {
  const next =
    direction > 0
      ? Math.floor(grams / GRAMS_STEP) * GRAMS_STEP + GRAMS_STEP
      : Math.ceil(grams / GRAMS_STEP) * GRAMS_STEP - GRAMS_STEP
  return Math.min(MAX_GRAMS, Math.max(GRAMS_STEP, next))
}

/** kcal of some grams of a food, from its kcal per 100 g. */
export function kcalFor(caloriesPer100g: number, grams: number): number {
  return (caloriesPer100g * grams) / 100
}

export type Headline =
  | { kind: 'left'; kcal: number }
  | { kind: 'over'; kcal: number }
  | { kind: 'eaten'; kcal: number }

/**
 * The day's big number: kcal left while under the target, how many over
 * once past it (never a negative "left"), or kcal eaten without a target.
 */
export function headline(summary: Pick<DailySummary, 'totals' | 'calories_remaining'>): Headline {
  const remaining = summary.calories_remaining
  if (remaining === null) return { kind: 'eaten', kcal: summary.totals.calories }
  return remaining < 0 ? { kind: 'over', kcal: -remaining } : { kind: 'left', kcal: remaining }
}
