import { describe, expect, it } from 'vitest'
import type { Food } from './api'
import { foodPicks } from './foodPicks'

function food(id: number, name: string, favourite = false): Food {
  return {
    id,
    name,
    calories_per_100g: 100,
    protein_per_100g: 1,
    carbs_per_100g: 1,
    fat_per_100g: 1,
    favourite,
  }
}

describe('foodPicks', () => {
  it('keeps the favourites in list order and recent ones in theirs', () => {
    const foods = [food(1, 'Apple', true), food(2, 'Milk'), food(3, 'Oats', true)]
    const recent = [food(2, 'Milk')]

    const picks = foodPicks(foods, recent)

    expect(picks.favourites.map((f) => f.name)).toEqual(['Apple', 'Oats'])
    expect(picks.recent.map((f) => f.name)).toEqual(['Milk'])
  })

  it('shows a favourite once, among the favourites, even when recent', () => {
    const foods = [food(1, 'Apple', true), food(2, 'Milk')]
    const recent = [food(1, 'Apple', true), food(2, 'Milk')]

    const picks = foodPicks(foods, recent)

    expect(picks.favourites.map((f) => f.name)).toEqual(['Apple'])
    expect(picks.recent.map((f) => f.name)).toEqual(['Milk'])
  })

  it('gives nothing when there are no favourites and nothing logged', () => {
    expect(foodPicks([food(1, 'Apple')], [])).toEqual({ favourites: [], recent: [] })
  })
})
