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
  await expect(yours.getByText('Feta cheese', { exact: true })).toBeVisible()

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
