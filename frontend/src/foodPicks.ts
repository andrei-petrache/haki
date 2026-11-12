import type { Food } from './api'

export type FoodPicks = { favourites: Food[]; recent: Food[] }

/**
 * Today's one-tap picks: the favourites (in the order of the food list, by
 * name), then the recent foods that are not already among them, so no food
 * shows twice.
 */
export function foodPicks(foods: Food[], recent: Food[]): FoodPicks {
  const favourites = foods.filter((food) => food.favourite)
  const favouriteIds = new Set(favourites.map((food) => food.id))
  return { favourites, recent: recent.filter((food) => !favouriteIds.has(food.id)) }
}
