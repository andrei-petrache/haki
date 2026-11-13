/**
 * The catalog, loaded into the throwaway stack by the backend's import
 * command (scripts/e2e.sh): credits here; searching and picking follow.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, deleteEverything, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function tab(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(page)
})

test.afterAll(async () => {
  await deleteEverything(page)
  await page.close()
})

test('Credits lists the catalog sources with licence and version', async () => {
  await tab('Profile').click()
  await page.getByRole('button', { name: 'Credits: where the catalog comes from' }).click()

  await expect(page.getByRole('heading', { name: 'Credits' })).toBeVisible()
  const usda = page.locator('.credit', { hasText: 'USDA FoodData Central' })
  await expect(usda).toContainText('CC0-1.0')
  await expect(usda).toContainText('2018-04')
  const exercises = page.locator('.credit', { hasText: 'Free Exercise DB' })
  await expect(exercises).toContainText('Unlicense')
  await expect(page.getByRole('link', { name: 'Free Exercise DB' })).toHaveAttribute(
    'href',
    'https://github.com/yuhonas/free-exercise-db',
  )
  // Neither licence requires an on-screen attribution today
  await expect(page.locator('.attribution')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/16-credits-phone.png`, fullPage: true })

  await page.getByRole('button', { name: '‹ Back to profile' }).click()
  await expect(page.getByLabel('Weights in')).toBeVisible()
})

test('a food from the catalog: search, add, add again, and a name taken by hand', async () => {
  await tab('Foods').click()
  await page.getByRole('button', { name: 'From the catalog' }).click()
  const search = page.getByLabel('Search the catalog')

  // Romanian name without diacritics, on an English screen: the API matches either name
  await search.fill('branza feta')
  await expect(page.getByRole('button', { name: 'Add Feta cheese', exact: true })).toBeVisible()
  await expect(page.locator('.catalog-picker li', { hasText: 'Feta cheese' })).toContainText(
    'USDA FoodData Central',
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/17-catalog-foods-phone.png`, fullPage: true })

  await page.getByRole('button', { name: 'Add Feta cheese', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Added "Feta cheese" to your foods.')
  const yours = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Your foods' }) })
  await expect(yours.locator('.food-list').getByText('Feta cheese', { exact: true })).toBeVisible()

  // Asking twice is harmless: the same copy, nothing duplicated
  await page.getByRole('button', { name: 'Add Feta cheese', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('"Feta cheese" is already in your foods.')
  const { body: foods } = await api(page, 'GET', '/foods')
  const copies = (foods as { name: string; catalog_food_id: number | null }[]).filter(
    (food) => food.name === 'Feta cheese',
  )
  expect(copies).toHaveLength(1)
  expect(copies[0].catalog_food_id).not.toBeNull()

  // A food typed by hand with a catalog food's name: 409, said plainly
  const { status } = await api(page, 'POST', '/foods', {
    name: 'Cream cheese',
    calories_per_100g: 300,
    protein_per_100g: 6,
    carbs_per_100g: 4,
    fat_per_100g: 30,
  })
  expect(status).toBe(201)
  await search.fill('cream cheese')
  await page.getByRole('button', { name: 'Add Cream cheese', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText(
    'You already have a food called "Cream cheese". Rename yours to add this one from the catalog.',
  )

  await search.fill('zzzz')
  await expect(page.getByText('Nothing in the catalog matches "zzzz"')).toBeVisible()
})

test('a catalog food over 900 kcal (lard, 902) can be edited and saved', async () => {
  await tab('Foods').click()
  // Still open from the test before: Foods keeps its panel while the tab shows
  if ((await page.getByLabel('Search the catalog').count()) === 0) {
    await page.getByRole('button', { name: 'From the catalog' }).click()
  }
  await page.getByLabel('Search the catalog').fill('lard')
  await page.getByRole('button', { name: 'Add Lard', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Added "Lard" to your foods.')

  // Saving the copy unchanged: with the old 900 the browser refused the form
  const yours = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Your foods' }) })
  await yours.locator('.food-list li', { hasText: 'Lard' }).getByRole('button', { name: 'Edit' }).click()
  const calories = yours.getByLabel('Calories')
  await expect(calories).toHaveValue('902')
  expect(await calories.evaluate((input: HTMLInputElement) => input.checkValidity())).toBe(true)
  await yours.getByRole('button', { name: 'Save' }).click()
  await expect(yours.getByLabel('Calories')).toHaveCount(0)
  await expect(yours.locator('.food-list li', { hasText: 'Lard' })).toContainText('902 kcal')

  // Over the backend's 950 the browser still says no, before any request
  await yours.locator('.food-list li', { hasText: 'Lard' }).getByRole('button', { name: 'Edit' }).click()
  await yours.getByLabel('Calories').fill('951')
  expect(
    await yours.getByLabel('Calories').evaluate((input: HTMLInputElement) => input.validity.rangeOverflow),
  ).toBe(true)
  await yours.getByRole('button', { name: 'Cancel' }).click()
})

test('an exercise from the catalog in the workout editor: new, again, and a name taken', async () => {
  await tab('Workouts').click()
  await page.getByRole('button', { name: 'New workout' }).click()
  const blocks = page.locator('fieldset.exercise-block')

  await blocks.nth(0).getByRole('button', { name: 'From the catalog' }).click()
  await blocks.nth(0).getByLabel('Search the catalog').fill('bench press barbell medium')
  await blocks.nth(0).getByRole('button', { name: 'Use Barbell Bench Press - Medium Grip', exact: true }).click()

  await expect(blocks.nth(0).getByRole('status')).toHaveText(
    'Added "Barbell Bench Press - Medium Grip" to your exercises.',
  )
  await expect(blocks.nth(0).locator('select').first().locator('option:checked')).toHaveText(
    'Barbell Bench Press - Medium Grip',
  )

  // The same pick on a second row reuses the copy
  await page.getByRole('button', { name: 'Add exercise' }).click()
  await blocks.nth(1).getByRole('button', { name: 'From the catalog' }).click()
  await blocks.nth(1).getByLabel('Search the catalog').fill('bench press barbell medium')
  await blocks.nth(1).getByRole('button', { name: 'Use Barbell Bench Press - Medium Grip', exact: true }).click()
  await expect(blocks.nth(1).getByRole('status')).toHaveText(
    'Using "Barbell Bench Press - Medium Grip", already in your exercises.',
  )

  // One of the user's own, typed by hand after the editor opened: 409, and theirs is used
  const { status } = await api(page, 'POST', '/exercises', { name: 'Dumbbell Bench Press' })
  expect(status).toBe(201)
  await blocks.nth(1).getByRole('button', { name: 'From the catalog' }).click()
  await blocks.nth(1).getByLabel('Search the catalog').fill('dumbbell bench')
  await blocks.nth(1).getByRole('button', { name: 'Use Dumbbell Bench Press', exact: true }).click()
  await expect(blocks.nth(1).getByRole('status')).toHaveText(
    'You already have an exercise called "Dumbbell Bench Press": using yours.',
  )
  await expect(blocks.nth(1).locator('select').first().locator('option:checked')).toHaveText(
    'Dumbbell Bench Press',
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/18-catalog-exercises-phone.png`, fullPage: true })

  const { body: exercises } = await api(page, 'GET', '/exercises')
  const names = (exercises as { name: string }[]).map((exercise) => exercise.name).sort()
  expect(names).toEqual(['Barbell Bench Press - Medium Grip', 'Dumbbell Bench Press'])
  await page.getByRole('button', { name: 'Cancel' }).click()
})

test('an exercise from the catalog in the program editor', async () => {
  await tab('Programs').click()
  await page.getByRole('button', { name: 'New program' }).click()
  const row = page.locator('.planned').first()

  await row.getByRole('button', { name: 'From the catalog' }).click()
  await row.getByLabel('Search the catalog').fill('bench press barbell medium')
  await row.getByRole('button', { name: 'Use Barbell Bench Press - Medium Grip', exact: true }).click()

  await expect(row.getByRole('status')).toHaveText(
    'Using "Barbell Bench Press - Medium Grip", already in your exercises.',
  )
  await expect(row.locator('select').first().locator('option:checked')).toHaveText(
    'Barbell Bench Press - Medium Grip',
  )
  await page.getByRole('button', { name: 'Cancel' }).click()
})
