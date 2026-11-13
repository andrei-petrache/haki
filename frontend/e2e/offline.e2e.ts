/**
 * Offline logging on a 390 px phone: with no connection, a one-tap chip
 * and a quick entry wait on the device ("Waiting for a connection"), and
 * go by themselves once the connection is back, each saved once.
 */
import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let context: BrowserContext
let page: Page

function localDay(): string {
  const date = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'en-US' })
  page = await context.newPage()
  await signUp(page)
  const food = await api(page, 'POST', '/foods', {
    name: 'Oats',
    calories_per_100g: 379,
    protein_per_100g: 13,
    carbs_per_100g: 68,
    fat_per_100g: 7,
  })
  // Logged once, yesterday: a recent chip with 60 g
  const yesterday = new Date(Date.now() - 86_400_000)
  const pad = (n: number) => String(n).padStart(2, '0')
  const day = `${yesterday.getFullYear()}-${pad(yesterday.getMonth() + 1)}-${pad(yesterday.getDate())}`
  await api(page, 'POST', '/entries', { food_id: (food.body as { id: number }).id, eaten_on: day, meal_type: 'breakfast', grams: 60 })
  await page.reload()
})

test.afterAll(async () => {
  await context.close()
})

async function todayEntries(): Promise<number> {
  const { body } = await api(page, 'GET', `/entries?date=${localDay()}`)
  return (body as unknown[]).length
}

test('with no connection, a chip and a quick entry wait on the device', async () => {
  const chip = page.getByRole('group', { name: 'Recent foods' }).getByRole('button', { name: /Oats/ })
  await expect(chip).toBeVisible()
  await context.setOffline(true)

  await chip.click()
  await expect(page.locator('.toast')).toContainText('No connection: Oats is saved on this device')

  await page.getByRole('button', { name: 'Just kcal' }).click()
  const quick = page.getByRole('form', { name: 'Quick add' })
  await quick.getByLabel('What (optional)').fill('Coffee')
  await quick.getByLabel('Calories (kcal)').fill('40')
  await quick.getByRole('button', { name: /^Add/ }).click()

  const pending = page.getByRole('region', { name: 'Waiting for a connection' })
  await expect(pending.locator('li')).toHaveCount(2)
  await expect(pending).toContainText('Oats')
  await expect(pending).toContainText('60 g')
  await expect(pending).toContainText('Coffee')
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('haki_outbox') ?? '[]').length)).toBe(2)
  await page.screenshot({ path: `${SHOTS}/55-offline-pending-phone.png`, fullPage: true })
})

test('back online, both go by themselves, each once', async () => {
  await context.setOffline(false)
  await expect(page.locator('.toast')).toContainText('Back online: what you logged offline is saved (2).')
  await expect(page.getByRole('region', { name: 'Waiting for a connection' })).toHaveCount(0)
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('haki_outbox') ?? '[]').length)).toBe(0)
  expect(await todayEntries()).toBe(2)

  // A reload sends nothing again
  await page.reload()
  await expect(page.getByRole('navigation').getByRole('button').first()).toBeVisible()
  await page.waitForTimeout(500)
  expect(await todayEntries()).toBe(2)
})
