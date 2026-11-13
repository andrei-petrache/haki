/**
 * Barcodes on Foods, 390 px. The lookup itself is the backend's and Open
 * Food Facts', so it is mocked here (as /features): the product shows with
 * its ODbL credit, fills the new food form (credited there too, gaps left
 * empty), and the user's own save creates the food; with the switch off
 * there is no button at all.
 */
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import { api, SHOTS, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

const SOURCE = {
  key: 'off',
  license: 'ODbL-1.0',
  attribution: 'Open Food Facts contributors',
  url: 'https://world.openfoodfacts.org/product/5941234567892',
}

const PRODUCT = {
  barcode: '5941234567892',
  name: 'Iaurt grecesc 10%',
  name_ro: null,
  brand: 'Lăptăria',
  quantity: '400 g',
  calories_per_100g: 120,
  protein_per_100g: null,
  carbs_per_100g: 4,
  fat_per_100g: 10,
  complete: false,
  out_of_range: [],
  stale: false,
  fetched_at: '2026-11-13T20:00:00Z',
  source: SOURCE,
}

async function features(barcode: boolean) {
  await page.route('**/api/features', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ password_reset: false, body_weight: true, export: true, barcode }),
    }),
  )
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(page)
})

test.afterAll(async () => {
  await page.close()
})

test('with barcodes off on the server, no button', async () => {
  await features(false)
  await page.getByRole('navigation').getByRole('button', { name: 'Foods', exact: true }).click()
  await expect(page.getByRole('button', { name: 'From the catalog' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Scan a barcode' })).toHaveCount(0)
  await page.unroute('**/api/features')
})

test('a product found: credited, then the form filled and credited, the user saves', async () => {
  await features(true)
  await page.route('**/api/barcode/**', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PRODUCT) }),
  )
  await page.reload()
  await page.getByRole('navigation').getByRole('button', { name: 'Foods', exact: true }).click()
  await page.getByRole('button', { name: 'Scan a barcode' }).click()
  await page.getByLabel('Barcode (the digits under the bars)').fill('5941234567892')
  await page.getByRole('button', { name: 'Look it up' }).click()

  const result = page.locator('.barcode-result')
  await expect(result).toContainText('Iaurt grecesc 10%')
  await expect(result).toContainText('Lăptăria · 400 g')
  await expect(result).toContainText('Per 100 g: 120 kcal · P — · C 4 · F 10')
  await expect(result).toContainText('Data from Open Food Facts contributors, under the ODbL-1.0 licence.')
  await expect(result.getByRole('link', { name: 'See the product' })).toHaveAttribute('href', SOURCE.url)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/85-barcode-result-phone.png`, fullPage: true })

  await result.getByRole('button', { name: 'Use these values' }).click()
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Add a food' }) })
  await expect(panel).toContainText('Data from Open Food Facts contributors')
  await expect(panel.getByRole('link', { name: 'See the product' })).toHaveAttribute('href', SOURCE.url)
  await expect(panel.getByLabel('Name')).toHaveValue('Iaurt grecesc 10%')
  await expect(panel.getByLabel('Calories (kcal)')).toHaveValue('120')
  // Unknown to Open Food Facts: left empty for the user
  await expect(panel.getByLabel('Protein (g)')).toHaveValue('')
  await panel.getByLabel('Protein (g)').fill('9')
  await panel.getByRole('button', { name: 'Add food' }).click()

  await expect(page.locator('.food-list li', { hasText: 'Iaurt grecesc 10%' })).toBeVisible()
  const foods = (await api(page, 'GET', '/foods')).body as { name: string; protein_per_100g: number; catalog_food_id: number | null }[]
  const saved = foods.find((food) => food.name === 'Iaurt grecesc 10%')!
  expect(saved.protein_per_100g).toBe(9)
  // The user's own food: nothing in the catalog
  expect(saved.catalog_food_id ?? null).toBeNull()
})

test('a product Open Food Facts does not know: said so, in the UI language', async () => {
  await page.unroute('**/api/barcode/**')
  await page.route('**/api/barcode/**', (route: Route) =>
    route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Product not found', code: 'product_not_found' }),
    }),
  )
  await page.getByRole('button', { name: 'Scan a barcode' }).click()
  await page.getByLabel('Barcode (the digits under the bars)').fill('4006381333931')
  await page.getByRole('button', { name: 'Look it up' }).click()
  await expect(page.locator('.barcode .error')).toHaveText('Open Food Facts does not know this product: add it by hand.')
})
