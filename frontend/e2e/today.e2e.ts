/**
 * Fast logging on Today: the foods logged most recently come back as
 * one-tap picks above the form, newest first, after the favourites.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page
const foodIds: Record<string, number> = {}

function form(): Locator {
  return page.locator('form.entry-form')
}

function picks(): Locator {
  return page.getByRole('group', { name: 'Recent foods' })
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(page)
  for (const [name, kcal] of [
    ['Apple', 52],
    ['Milk', 64],
    ['Oats', 389],
  ] as const) {
    const { status, body } = await api(page, 'POST', '/foods', {
      name,
      calories_per_100g: kcal,
      protein_per_100g: 1,
      carbs_per_100g: 1,
      fat_per_100g: 1,
    })
    expect(status).toBe(201)
    foodIds[name] = (body as { id: number }).id
  }
  await page.reload()
})

test.afterAll(async () => {
  // Foods with entries cannot be deleted; the account goes with the stack
  await page.close()
})

test('nothing logged yet: no picks; a food logged becomes one', async () => {
  await expect(form().getByRole('heading', { name: 'Add to this day' })).toBeVisible()
  await expect(picks()).toHaveCount(0)

  await form().locator('.food-field select').selectOption({ label: 'Milk' })
  await form().getByLabel('Grams').fill('200')
  await form().getByRole('button', { name: 'Add', exact: true }).click()

  await expect(picks().getByRole('button')).toHaveText(['Milk'])
  // Milk is still the chosen food, so its pick shows as pressed
  await expect(picks().getByRole('button', { name: 'Milk' })).toHaveAttribute('aria-pressed', 'true')
})

test('newest first; one tap picks the food and moves on to the grams', async () => {
  const day = await page.getByLabel('Day', { exact: true }).inputValue()
  const { status } = await api(page, 'POST', '/entries', {
    food_id: foodIds.Oats,
    eaten_on: day,
    meal_type: 'breakfast',
    grams: 50,
  })
  expect(status).toBe(201)
  await page.reload()

  await expect(picks().getByRole('button')).toHaveText(['Oats', 'Milk'])
  // Apple, first by name, is chosen by default and was never logged
  await expect(form().locator('.food-field select')).toHaveValue(String(foodIds.Apple))

  await picks().getByRole('button', { name: 'Milk' }).click()
  await expect(form().locator('.food-field select')).toHaveValue(String(foodIds.Milk))
  await expect(form().getByLabel('Grams')).toBeFocused()
  await page.keyboard.type('150')
  await page.keyboard.press('Enter')

  await expect(page.locator('.meal li', { hasText: 'Milk' })).toHaveCount(2)
  await expect(picks().getByRole('button')).toHaveText(['Milk', 'Oats'])
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/21-recent-foods-phone.png`, fullPage: true })
})

test('a starred food comes first on Today, once, and unstarring removes it', async () => {
  const tab = (name: string) =>
    page.getByRole('navigation').getByRole('button', { name, exact: true })
  await tab('Foods').click()
  const star = page.getByRole('button', { name: 'Favourite: Oats' })
  await expect(star).toHaveAttribute('aria-pressed', 'false')
  await star.click()
  await expect(star).toHaveAttribute('aria-pressed', 'true')
  const { body } = await api(page, 'GET', '/foods?favourite=true')
  expect((body as { name: string }[]).map((food) => food.name)).toEqual(['Oats'])
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

  await tab('Today').click()
  const favourites = page.getByRole('group', { name: 'Favourite foods' })
  await expect(favourites.getByRole('button')).toHaveText(['Oats'])
  // Oats was logged recently too, but shows only among the favourites
  await expect(picks().getByRole('button')).toHaveText(['Milk'])
  await favourites.getByRole('button', { name: 'Oats' }).click()
  await expect(form().locator('.food-field select')).toHaveValue(String(foodIds.Oats))
  await expect(form().getByLabel('Grams')).toBeFocused()
  await page.screenshot({ path: `${SHOTS}/22-favourite-foods-phone.png`, fullPage: true })

  await tab('Foods').click()
  await page.getByRole('button', { name: 'Favourite: Oats' }).click()
  await expect(page.getByRole('button', { name: 'Favourite: Oats' })).toHaveAttribute(
    'aria-pressed',
    'false',
  )
  await tab('Today').click()
  await expect(picks().getByRole('button')).toHaveText(['Milk', 'Oats'])
  await expect(page.getByRole('group', { name: 'Favourite foods' })).toHaveCount(0)
})
