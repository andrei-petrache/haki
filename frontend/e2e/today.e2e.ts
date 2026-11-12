/**
 * Today in direction A, end to end on a 390 px phone: one search over
 * your foods and the catalog, chips that log as much as last time with
 * Undo, the headline under and over the target, meals other than the
 * open one on a line each, copying a meal, quick add, and names in the
 * UI language.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page
const foodIds: Record<string, number> = {}

function logger(): Locator {
  return page.locator('section.logger')
}

function toast(): Locator {
  return page.locator('.toast')
}

async function chooseMeal(name: string) {
  await logger().getByRole('group', { name: 'Add to' }).getByRole('button', { name, exact: true }).click()
}

async function search(q: string) {
  await logger().getByPlaceholder('Search a food').fill(q)
}

function result(text: string | RegExp): Locator {
  return logger().locator('li.result', { hasText: text }).first()
}

async function day(): Promise<string> {
  return page.getByLabel('Day', { exact: true }).inputValue()
}

async function entriesToday(): Promise<{ food_name: string; meal_type: string; grams: number | null }[]> {
  const { body } = await api(page, 'GET', `/entries?date=${await day()}`)
  return body as { food_name: string; meal_type: string; grams: number | null }[]
}

async function box(locator: Locator) {
  const found = await locator.boundingBox()
  expect(found).not.toBeNull()
  return found!
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

test('search: your foods first, then the catalog; Add logs what the stepper says', async () => {
  await chooseMeal('Breakfast')
  await expect(page.getByRole('group', { name: 'Recent foods' })).toHaveCount(0)

  await search('milk')
  await expect(logger().getByRole('heading', { name: 'Yours' })).toBeVisible()
  await expect(logger().getByRole('heading', { name: 'Catalog' })).toBeVisible()
  await expect(logger()).toContainText('Values from USDA FoodData Central')
  const milk = result(/^Milk/)
  await milk.locator('.result-head').click()
  await expect(milk.locator('input[type="number"]')).toHaveValue('100')
  await milk.getByRole('button', { name: 'More of Milk' }).click()
  await expect(milk.locator('input[type="number"]')).toHaveValue('110')
  await milk.getByRole('button', { name: 'Add 70 kcal' }).click()

  await expect(toast()).toContainText('Added Milk, 110 g, to Breakfast.')
  await expect(page.locator('section.meal li', { hasText: 'Milk' })).toContainText('110 g')
  // Done with this search: the field is empty and the results closed
  await expect(logger().getByPlaceholder('Search a food')).toHaveValue('')
  await expect(logger().locator('li.result')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/30-search-phone.png`, fullPage: true })
})

test('a catalog food is copied into yours and logged by the same Add', async () => {
  await search('feta')
  const feta = result('Feta cheese')
  await feta.locator('.result-head').click()
  await feta.getByRole('button', { name: /^Add \d+ kcal$/ }).click()
  await expect(toast()).toContainText('Added Feta cheese, 100 g, to Breakfast.')

  const { body } = await api(page, 'GET', '/foods')
  expect((body as { name: string }[]).map((food) => food.name)).toContain('Feta cheese')
  // Searched again, it is among yours, with last time, and not twice
  await search('')
  await search('feta')
  const yours = logger().locator('ul.results').first()
  await expect(yours.locator('li.result', { hasText: 'Feta cheese' })).toContainText('last time 100 g')
  await expect(logger().locator('li.result', { hasText: /^Feta cheese/ })).toHaveCount(1)
  await search('')
})

test('a chip logs as much as last time in one tap, and Undo takes it back', async () => {
  const recent = page.getByRole('group', { name: 'Recent foods' })
  const chip = recent.getByRole('button', { name: 'Log Milk, 110 g' })
  await expect(chip).toContainText('110 g')
  const before = (await entriesToday()).length
  const order = await page.locator('.chip-row button.chip').allTextContents()

  await chip.click()
  await expect(toast()).toContainText('Added Milk, 110 g, to Breakfast.')
  await expect.poll(async () => (await entriesToday()).length).toBe(before + 1)
  // The chip just used keeps its place while the user stays on the page
  await expect.poll(async () => page.locator('.chip-row button.chip').allTextContents()).toEqual(order)
  await page.screenshot({ path: `${SHOTS}/31-chip-undo-phone.png`, fullPage: true })

  await toast().getByRole('button', { name: 'Undo' }).click()
  await expect(toast()).toHaveCount(0)
  await expect.poll(async () => (await entriesToday()).length).toBe(before)
})

test('a favourite never logged opens its stepper instead', async () => {
  expect((await api(page, 'PUT', `/foods/${foodIds.Oats}/favourite`)).status).toBe(200)
  await page.reload()
  await chooseMeal('Breakfast')
  const favourites = page.getByRole('group', { name: 'Favourite foods' })
  await favourites.getByRole('button', { name: 'Oats', exact: true }).click()

  const oats = result(/^Oats/)
  await expect(oats.locator('input[type="number"]')).toHaveValue('100')
  await oats.getByRole('button', { name: 'Add 389 kcal' }).click()
  await expect(toast()).toContainText('Added Oats, 100 g, to Breakfast.')
  await expect(favourites.getByRole('button', { name: 'Log Oats, 100 g' })).toBeVisible()
})

test('deleting an entry: at once, no dialog, Undo for 8 seconds above the bottom bar', async () => {
  let dialogs = 0
  const count = () => {
    dialogs += 1
  }
  page.on('dialog', (dialog) => {
    count()
    void dialog.dismiss()
  })
  await chooseMeal('Breakfast')
  const before = (await entriesToday()).length
  const row = page.locator('section.meal li', { hasText: 'Oats' }).first()
  await row.getByRole('button', { name: 'Delete Oats' }).click()

  await expect(toast()).toContainText('Removed Oats, 100 g, from Breakfast.')
  await expect.poll(async () => (await entriesToday()).length).toBe(before - 1)
  expect(dialogs).toBe(0)
  const message = await box(toast())
  const bar = await box(page.getByRole('navigation'))
  expect(message.y + message.height, 'Undo above the bottom bar').toBeLessThanOrEqual(bar.y)
  await page.screenshot({ path: `${SHOTS}/37-delete-undo-phone.png` })

  // Still there after 6.5 s (it stays 8 s)
  await page.waitForTimeout(6500)
  await expect(toast()).toBeVisible()
  await toast().getByRole('button', { name: 'Undo' }).click()
  await expect.poll(async () => (await entriesToday()).filter((e) => e.food_name === 'Oats')).toHaveLength(1)
  await expect.poll(async () => (await entriesToday()).length).toBe(before)
  page.removeAllListeners('dialog')
})

test('on a 390 px phone: search and the first meal show without scrolling; one chip row', async () => {
  await page.reload()
  await page.evaluate(() => window.scrollTo(0, 0))
  const bar = await box(page.getByRole('navigation'))
  const field = await box(logger().getByPlaceholder('Search a food'))
  expect(field.y).toBeGreaterThanOrEqual(0)
  expect(field.y + field.height, 'search above the bottom bar').toBeLessThanOrEqual(bar.y)
  const firstMeal = page.locator('section.meal h3, button.meal-line').first()
  const meal = await box(firstMeal)
  expect(meal.y + meal.height, 'first meal above the bottom bar').toBeLessThanOrEqual(bar.y)

  // The chips: one row (scrolled sideways), favourites first
  const chips = page.locator('.chip-row button.chip')
  expect(await chips.count()).toBeGreaterThan(1)
  const tops = new Set<number>()
  for (const chip of await chips.all()) tops.add(Math.round((await box(chip)).y))
  expect(tops.size, 'chips on one row').toBe(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/36-today-fold-phone.png` })

  // While searching, no chips: results start under the field
  await search('mi')
  await expect(page.locator('.chip-row')).toHaveCount(0)
  await search('')
  await expect(page.locator('.chip-row')).toHaveCount(1)
})

test('the headline: kcal left under the target, kcal over past it, and red only then', async () => {
  expect((await api(page, 'PUT', '/auth/me/target', { daily_calorie_target: 2000 })).status).toBe(200)
  await page.reload()
  const summary = page.locator('section.summary')
  await expect(summary.locator('.calories')).toContainText('kcal left')
  await expect(summary.getByRole('progressbar')).not.toHaveClass(/over/)
  await expect(summary).toContainText('eaten · of 2,000 kcal')
  await page.screenshot({ path: `${SHOTS}/32-under-target-phone.png`, fullPage: true })

  expect(
    (await api(page, 'POST', '/entries/quick', {
      eaten_on: await day(),
      meal_type: 'dinner',
      name: 'Feast',
      calories: 2500,
    })).status,
  ).toBe(201)
  await page.reload()
  const { body } = await api(page, 'GET', `/summary?date=${await day()}`)
  const over = -(body as { calories_remaining: number }).calories_remaining
  await expect(summary.locator('.calories')).toContainText('kcal over')
  await expect(summary.locator('.big')).toHaveText(Math.round(over).toLocaleString('en-US'))
  await expect(summary.getByRole('progressbar')).toHaveClass(/over/)
  await page.screenshot({ path: `${SHOTS}/33-over-target-phone.png`, fullPage: true })
})

test('only the open meal in full; the others on a line, a tap opens one', async () => {
  await chooseMeal('Breakfast')
  await expect(page.locator('section.meal h3', { hasText: 'Breakfast' })).toBeVisible()
  const dinnerLine = page.getByRole('button', { name: 'Open Dinner' })
  await expect(dinnerLine).toContainText('1 item')

  await dinnerLine.click()
  await expect(page.locator('section.meal h3', { hasText: 'Dinner' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open Breakfast' })).toBeVisible()
  // New entries now go to dinner
  await expect(
    logger().getByRole('group', { name: 'Add to' }).getByRole('button', { name: 'Dinner', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
})

test('copy a meal: to another meal of the same day', async () => {
  await chooseMeal('Breakfast')
  const rows = await page.locator('section.meal li').count()
  expect(rows).toBeGreaterThan(0)

  await page.getByRole('button', { name: 'Copy Breakfast to another day or meal' }).click()
  const copyForm = page.getByRole('form', { name: 'Copy Breakfast to another day or meal' })
  await copyForm.getByLabel('To day').fill(await day())
  await expect(copyForm.getByRole('button', { name: 'Copy', exact: true })).toBeDisabled()
  await copyForm.locator('select').selectOption({ label: 'Lunch' })
  await copyForm.getByRole('button', { name: 'Copy', exact: true }).click()

  await expect(page.locator('p[role="status"]')).toContainText(`Copied ${rows} items to Lunch`)
  expect((await entriesToday()).filter((entry) => entry.meal_type === 'lunch')).toHaveLength(rows)
})

test('quick add: kcal without a food, under its short name', async () => {
  await page.getByRole('button', { name: 'Just kcal' }).click()
  const quick = page.getByRole('form', { name: 'Quick add' })
  await quick.getByLabel('What (optional)').fill('Restaurant soup')
  await quick.getByLabel('Calories (kcal)').fill('320')
  await quick.locator('select').selectOption({ label: 'Snacks' })
  await quick.getByRole('button', { name: 'Add', exact: true }).click()

  await expect.poll(async () => (await entriesToday()).filter((e) => e.food_name === 'Restaurant soup')).toHaveLength(1)
  await page.getByRole('button', { name: 'Open Snacks' }).click()
  await expect(page.locator('section.meal li', { hasText: 'Restaurant soup' })).toContainText('quick add')
  await quick.getByRole('button', { name: 'Cancel' }).click()
})

test('names in the UI language: a catalog copy shows its Romanian name in Romanian', async () => {
  await page.evaluate(() => localStorage.setItem('haki_locale', 'ro'))
  await page.reload()
  await page.getByRole('group', { name: 'Adaugă la' }).getByRole('button', { name: 'Mic dejun', exact: true }).click()
  await expect(page.getByRole('group', { name: 'Alimente recente' })).toContainText('Brânză feta')
  await expect(page.locator('section.meal li', { hasText: 'Brânză feta' })).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/34-names-ro-phone.png`, fullPage: true })
  await page.evaluate(() => localStorage.setItem('haki_locale', 'auto'))
  await page.reload()
})

test('long food names keep their room: Your foods on a phone, Today on a desktop', async () => {
  const name = 'Greek yogurt, plain, whole milk'
  const created = await api(page, 'POST', '/foods', {
    name,
    calories_per_100g: 97,
    protein_per_100g: 9,
    carbs_per_100g: 4,
    fat_per_100g: 5,
  })
  expect(created.status).toBe(201)
  const id = (created.body as { id: number }).id
  expect((await api(page, 'PUT', `/foods/${id}/favourite`)).status).toBe(200)

  // Your foods at 390 px: the name gets most of the row, the buttons wrap under it
  await page.getByRole('navigation').getByRole('button', { name: 'Foods', exact: true }).click()
  const row = page.locator('.food-list li', { hasText: name })
  const nameBox = await box(row.locator('.grow'))
  const rowBox = await box(row)
  expect(nameBox.width).toBeGreaterThan(rowBox.width * 0.75)
  const editBox = await box(row.getByRole('button', { name: 'Edit' }))
  expect(editBox.y).toBeGreaterThanOrEqual(nameBox.y + nameBox.height - 1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

  // Today on a desktop: the long favourite stays inside the logger's card
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.getByRole('navigation').getByRole('button', { name: 'Today', exact: true }).click()
  const card = await box(logger())
  const chip = await box(page.getByRole('group', { name: 'Favourite foods' }).getByRole('button', { name }))
  expect(chip.x + chip.width).toBeLessThanOrEqual(card.x + card.width)
  await page.screenshot({ path: `${SHOTS}/35-today-desktop.png`, fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
})
