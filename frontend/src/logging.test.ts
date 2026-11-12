import { describe, expect, it } from 'vitest'
import { displayName, entryName, headline, kcalFor, keepOrder, mealForHour, startGrams, stepGrams } from './logging'

describe('mealForHour', () => {
  it('follows the day: breakfast, lunch, dinner, then snacks late', () => {
    expect([6, 10, 11, 15, 16, 20, 21, 2].map(mealForHour)).toEqual([
      'breakfast',
      'breakfast',
      'lunch',
      'lunch',
      'dinner',
      'dinner',
      'snack',
      'breakfast',
    ])
  })
})

describe('displayName', () => {
  const copy = { name: 'Feta cheese', catalog_name: 'Feta cheese', catalog_name_ro: 'Brânză feta' }

  it('shows a catalog copy in the UI language, whichever name it was copied with', () => {
    expect(displayName(copy, 'ro')).toBe('Brânză feta')
    expect(displayName(copy, 'en')).toBe('Feta cheese')
    expect(displayName({ ...copy, name: 'Brânză feta' }, 'en')).toBe('Feta cheese')
  })

  it('keeps a renamed copy, a food typed by hand, and English where there is no Romanian', () => {
    expect(displayName({ ...copy, name: 'Feta from the market' }, 'ro')).toBe('Feta from the market')
    expect(displayName({ name: 'Sarmale' }, 'en')).toBe('Sarmale')
    expect(displayName({ name: 'Oats', catalog_name: 'Oats', catalog_name_ro: null }, 'ro')).toBe('Oats')
  })

  it('works for entries too, by their food_name', () => {
    expect(entryName({ food_name: 'Feta cheese', catalog_name: 'Feta cheese', catalog_name_ro: 'Brânză feta' }, 'ro')).toBe(
      'Brânză feta',
    )
    expect(entryName({ food_name: 'Pizza slice', catalog_name: null, catalog_name_ro: null }, 'ro')).toBe('Pizza slice')
  })
})

describe('quantities', () => {
  it('starts from last time, else 100 g', () => {
    expect(startGrams({ grams: 250 })).toBe(250)
    expect(startGrams(null)).toBe(100)
    expect(startGrams(undefined)).toBe(100)
  })

  it('steps by 10 g to round numbers, never below 10 g or above 5 kg', () => {
    expect(stepGrams(150, 1)).toBe(160)
    expect(stepGrams(150, -1)).toBe(140)
    expect(stepGrams(155, 1)).toBe(160)
    expect(stepGrams(155, -1)).toBe(150)
    expect(stepGrams(10, -1)).toBe(10)
    expect(stepGrams(4995, 1)).toBe(5000)
  })

  it('counts kcal from kcal per 100 g', () => {
    expect(kcalFor(81, 150)).toBeCloseTo(121.5)
  })
})

describe('headline', () => {
  const totals = { calories: 1511, protein: 0, carbs: 0, fat: 0 }

  it('is kcal left under the target, kcal over past it, kcal eaten without one', () => {
    expect(headline({ totals, calories_remaining: 689 })).toEqual({ kind: 'left', kcal: 689 })
    expect(headline({ totals, calories_remaining: 0 })).toEqual({ kind: 'left', kcal: 0 })
    expect(headline({ totals, calories_remaining: -120 })).toEqual({ kind: 'over', kcal: 120 })
    expect(headline({ totals, calories_remaining: null })).toEqual({ kind: 'eaten', kcal: 1511 })
  })
})

describe('keepOrder', () => {
  it('keeps known items where they were and puts new ones at the end', () => {
    const now = [{ id: 3 }, { id: 1 }, { id: 9 }, { id: 2 }]
    expect(keepOrder(now, [1, 2, 3]).map((x) => x.id)).toEqual([1, 2, 3, 9])
  })

  it('drops nothing and keeps the list as is without an order', () => {
    expect(keepOrder([{ id: 2 }, { id: 1 }], []).map((x) => x.id)).toEqual([2, 1])
  })
})
