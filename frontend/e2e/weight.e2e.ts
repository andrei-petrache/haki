/**
 * Body weight on a 390 px phone (the e2e stack switches it on with
 * BODY_WEIGHT_ENABLED): the card on Today logs the shown day's weight in
 * the user's unit, the trend view charts it with a tooltip under a finger,
 * and a weigh-in is deleted with Undo. With the server's switch off
 * (every /weights answer 404) nothing of it shows.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function localDay(offset = 0): string {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function card(): Locator {
  return page.locator('section.weight-card')
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true })
  await signUp(page)
  // Three weeks of weigh-ins, slowly down, one far off the line
  for (let offset = -20; offset <= -1; offset++) {
    if (offset % 2 !== 0) continue
    const kg = offset === -10 ? 86 : 82 + offset * -0.05
    const saved = await api(page, 'PUT', `/weights/${localDay(offset)}`, { weight_kg: kg })
    expect(saved.status).toBe(201)
  }
  await page.reload()
})

test.afterAll(async () => {
  await page.close()
})

test('the card on Today logs the day in kg, and replaces it', async () => {
  await expect(card()).toBeVisible()
  // Under the meals: the search still starts the screen
  const search = await page.getByPlaceholder('Search a food').boundingBox()
  const box = await card().boundingBox()
  expect(box!.y).toBeGreaterThan(search!.y)
  await expect(card().locator('.weight-trend')).toContainText(/kg trend · −\d[.,]\d kg a week/)

  const field = card().getByLabel('Weight (kg)')
  await field.fill('19')
  await card().getByRole('button', { name: 'Save weight' }).click()
  await expect(card()).toContainText('Weight must be from 20 to 400 kg')

  await field.fill('81.4')
  await card().getByRole('button', { name: 'Save weight' }).click()
  await expect(card().getByRole('status')).toHaveText(/^Saved 81[.,]4 kg for Today, /)
  const today = (await api(page, 'GET', `/weights?from=${localDay()}&to=${localDay()}`)).body as { weight_kg: number }[]
  expect(today.map((w) => w.weight_kg)).toEqual([81.4])

  // The same day again: replaced, not added
  await card().getByLabel('Weight (kg)').fill('81.2')
  await card().getByRole('button', { name: 'Save weight' }).click()
  await expect(card().getByRole('status')).toHaveText(/^Saved 81[.,]2 kg/)
  await expect(card().getByLabel('Weight (kg)')).toHaveValue('81.2')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await card().scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}/45-weight-card-phone.png` })
})

test('the trend: a chart with a legend, a tooltip under a finger, every weigh-in listed', async () => {
  await card().getByRole('button', { name: 'Trend ›' }).click()
  const chart = page.locator('.weight-chart')
  await expect(chart.locator('svg[role="img"]')).toHaveAttribute('aria-label', /11 weigh-ins/)
  await expect(chart.locator('.chart-legend')).toContainText('Weigh-in')
  await expect(chart.locator('.chart-legend')).toContainText('Trend')
  // The weigh-in far off the line is marked, and the legend says how
  await expect(chart.locator('svg[role="img"] circle.dot.outlier')).toHaveCount(1)
  await expect(chart.locator('.chart-legend')).toContainText('Far from the trend')
  await expect(page.locator('.weight-list li')).toHaveCount(11)

  const svg = await chart.locator('svg[role="img"]').boundingBox()
  await page.touchscreen.tap(svg!.x + svg!.width - 12, svg!.y + svg!.height / 2)
  await expect(chart.locator('.chart-tooltip')).toHaveText(/^\w{3} \d{1,2} \w{3}: 81[.,]2 kg, trend /)
  // Still there once the finger is up
  await page.waitForTimeout(300)
  await expect(chart.locator('.chart-tooltip')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/46-weight-trend-phone.png`, fullPage: true })

  await page.getByRole('group', { name: 'Period' }).getByRole('button', { name: '30 days' }).click()
  await expect(page.getByRole('group', { name: 'Period' }).getByRole('button', { name: '30 days' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
})

test('a weigh-in is deleted at once, with Undo', async () => {
  const first = page.locator('.weight-list li').first()
  await first.getByRole('button', { name: /^Delete the weigh-in of / }).click()
  await expect(page.locator('.weight-list li')).toHaveCount(10)
  await page.locator('.toast').getByRole('button', { name: 'Undo' }).click()
  await expect(page.locator('.weight-list li')).toHaveCount(11)
  await page.getByRole('button', { name: '‹ Back to today' }).click()
  await expect(card()).toBeVisible()
})

test('in pounds: typed and shown in lb, stored in kg', async () => {
  await page.getByRole('navigation').getByRole('button', { name: 'Profile', exact: true }).click()
  await page.getByLabel('Weights in').selectOption('lb')
  await page.getByRole('navigation').getByRole('button', { name: 'Today', exact: true }).click()
  // Today's 81.2 kg, shown in pounds
  await expect(card().getByLabel('Weight (lb)')).toHaveValue('179')
  await card().getByLabel('Weight (lb)').fill('180')
  await card().getByRole('button', { name: 'Save weight' }).click()
  await expect(card().getByRole('status')).toHaveText(/^Saved 180 lb/)
  const today = (await api(page, 'GET', `/weights?from=${localDay()}&to=${localDay()}`)).body as { weight_kg: number }[]
  expect(today[0].weight_kg).toBeCloseTo(81.65, 2)
  await page.getByRole('navigation').getByRole('button', { name: 'Profile', exact: true }).click()
  await page.getByLabel('Weights in').selectOption('kg')
})

test('with the server switch off (404), Today shows no weight at all', async () => {
  await page.route('**/api/weights**', (route) =>
    route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not Found","code":"not_found"}' }),
  )
  await page.getByRole('navigation').getByRole('button', { name: 'Today', exact: true }).click()
  await page.reload()
  await expect(page.getByPlaceholder('Search a food')).toBeVisible()
  await expect(card()).toHaveCount(0)
  await expect(page.locator('.error')).toHaveCount(0)
  await page.unroute('**/api/weights**')
})
