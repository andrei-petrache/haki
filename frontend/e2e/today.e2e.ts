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

test('copy a meal: to tomorrow by default, or to another meal of the same day', async () => {
  const day = await page.getByLabel('Day', { exact: true }).inputValue()
  const breakfast = page.locator('section.meal', { has: page.getByRole('heading', { name: /^Breakfast/ }) })
  const rows = await breakfast.locator('li').count()
  expect(rows).toBeGreaterThan(0)

  await page.getByRole('button', { name: 'Copy Breakfast to another day or meal' }).click()
  const copyForm = page.getByRole('form', { name: 'Copy Breakfast to another day or meal' })
  const toDay = copyForm.getByLabel('To day')
  const tomorrow = await toDay.inputValue()
  expect(tomorrow > day).toBe(true)

  // Onto itself is not offered: the server would refuse it (422)
  await toDay.fill(day)
  await expect(copyForm.getByRole('button', { name: 'Copy', exact: true })).toBeDisabled()
  await expect(copyForm).toContainText('Choose another day or meal.')

  await copyForm.locator('select').selectOption({ label: 'Lunch' })
  await copyForm.getByRole('button', { name: 'Copy', exact: true }).click()
  await expect(page.getByRole('status')).toContainText(`Copied ${rows} items to Lunch`)
  const lunch = page.locator('section.meal', { has: page.getByRole('heading', { name: /^Lunch/ }) })
  await expect(lunch.locator('li')).toHaveCount(rows)
  await expect(breakfast.locator('li')).toHaveCount(rows)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/23-copy-meal-phone.png`, fullPage: true })

  // The default target, tomorrow: the copy is there, not on the shown day
  await page.getByRole('button', { name: 'Copy Lunch to another day or meal' }).click()
  await page
    .getByRole('form', { name: 'Copy Lunch to another day or meal' })
    .getByRole('button', { name: 'Copy', exact: true })
    .click()
  await expect(page.getByRole('status')).toContainText(`Copied ${rows} items to Lunch`)
  await expect(lunch.locator('li')).toHaveCount(rows)
  const { body } = await api(page, 'GET', `/entries?date=${tomorrow}`)
  expect((body as { meal_type: string }[]).filter((entry) => entry.meal_type === 'lunch')).toHaveLength(rows)
})

test('quick add: kcal without a food, a default name, and deleting it', async () => {
  const dinner = page.locator('section.meal', { has: page.getByRole('heading', { name: /^Dinner/ }) })
  await expect(dinner).toHaveCount(0)

  await page.getByRole('button', { name: 'Quick add: just the kcal' }).click()
  const quick = page.getByRole('form', { name: 'Quick add' })
  await quick.getByLabel('What (optional)').fill('Restaurant soup')
  await quick.getByLabel('Calories (kcal)').fill('320')
  await quick.getByLabel('Protein (g)').fill('12')
  await quick.locator('select').selectOption({ label: 'Dinner' })
  await quick.getByRole('button', { name: 'Add', exact: true }).click()

  const soup = dinner.locator('li', { hasText: 'Restaurant soup' })
  await expect(soup).toContainText('quick add')
  await expect(soup).toContainText('320 kcal')
  // Fields cleared, the meal kept for the next one
  await expect(quick.getByLabel('Calories (kcal)')).toHaveValue('')
  await expect(quick.locator('select')).toHaveValue('dinner')

  await quick.getByLabel('Calories (kcal)').fill('150')
  await quick.getByRole('button', { name: 'Add', exact: true }).click()
  // Every quick row says "quick add"; the unnamed one, added last, also has it as its name
  const unnamed = dinner.locator('li').nth(1)
  await expect(unnamed).toContainText(/^Quick add quick add/)
  await expect(unnamed).toContainText('150 kcal')
  await expect(dinner.locator('h3')).toContainText('470 kcal')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/24-quick-add-phone.png`, fullPage: true })

  // Deleted through its own path; the food entries of the day stay
  const foodRows = await page.locator('section.meal li').count()
  page.once('dialog', (dialog) => void dialog.accept())
  await page.getByRole('button', { name: 'Delete Restaurant soup' }).click()
  await expect(soup).toHaveCount(0)
  await expect(page.locator('section.meal li')).toHaveCount(foodRows - 1)
  const day = await page.getByLabel('Day', { exact: true }).inputValue()
  const { body } = await api(page, 'GET', `/entries?date=${day}`)
  expect((body as { quick?: boolean }[]).filter((entry) => entry.quick)).toHaveLength(1)
})
