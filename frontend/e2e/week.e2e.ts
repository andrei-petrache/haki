/**
 * The week at a glance on a 390 px phone: a line on Today opens it; the
 * calories a day against the target (red only over it), training with its
 * volume by muscle, last week for comparison, and the days as a list.
 */
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function localDay(offset = 0): string {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

async function ok(method: string, path: string, data?: unknown) {
  const response = await api(page, method, path, data)
  if (response.status >= 400) throw new Error(`${method} ${path}: ${response.status} ${JSON.stringify(response.body)}`)
  return response.body
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(page)
  await ok('PUT', '/auth/me/target', { daily_calorie_target: 2000 })
  const rice = (await ok('POST', '/foods', {
    name: 'Rice',
    calories_per_100g: 130,
    protein_per_100g: 2.7,
    carbs_per_100g: 28,
    fat_per_100g: 0.3,
  })) as { id: number }
  // Today: 2,600 kcal (over the target); a week ago: 1,300 kcal
  await ok('POST', '/entries', { food_id: rice.id, eaten_on: localDay(), meal_type: 'lunch', grams: 2000 })
  await ok('POST', '/entries', { food_id: rice.id, eaten_on: localDay(-7), meal_type: 'lunch', grams: 1000 })
  // A catalog exercise counts under its muscle, one's own under "other"
  const found = (await ok('GET', '/catalog/exercises?q=bench%20press&language=en&limit=1')) as { id: number }[]
  const bench = (await ok('POST', '/exercises/from-catalog', { catalog_exercise_id: found[0].id, language: 'en' })) as {
    id: number
  }
  const own = (await ok('POST', '/exercises', { name: 'E2E Sled push' })) as { id: number }
  await ok('POST', '/workouts', {
    performed_on: localDay(),
    note: null,
    exercises: [
      { exercise_id: bench.id, sets: [{ reps: 5, weight_kg: 80 }, { reps: 5, weight_kg: 80 }] },
      { exercise_id: own.id, sets: [{ reps: 10, weight_kg: 50 }] },
    ],
  })
  await page.reload()
})

test.afterAll(async () => {
  await page.close()
})

test('a line on Today says the week so far, and opens it', async () => {
  const line = page.locator('button.week-summary')
  await expect(line).toContainText('This week')
  await expect(line).toContainText('workouts: 1')
  await line.click()
  await expect(page.getByRole('heading', { name: 'This week', exact: true })).toBeVisible()
})

test('the week: calories against the target, training by muscle, the days', async () => {
  // One logged day so far this week (today), 2,600 kcal
  await expect(page.locator('.week-hero')).toContainText(/2[,.]?600/)
  await expect(page.getByText('Days logged: 1 of 7')).toBeVisible()
  await expect(page.getByText(/\+1[,.]?300 kcal against last week/)).toBeVisible()
  // Today's column is over the target: red, and the legend says so
  await expect(page.locator('.kcal-bar.over')).toHaveCount(1)
  await expect(page.locator('.chart-legend')).toContainText('Over the target')
  await expect(page.locator('.kcal-target')).toHaveCount(7)

  // Volume: 2 × 5 × 80 + 10 × 50 = 1,300 kg; chest from the catalog, the rest "Your own exercises"
  await expect(page.locator('.week-stats')).toContainText(/1[,.]?300 kg/)
  const muscles = page.getByRole('list', { name: 'Volume by muscle' })
  await expect(muscles.locator('li').first()).toContainText('Chest')
  await expect(muscles.locator('li').last()).toContainText('Your own exercises')

  await expect(page.locator('.week-days li')).toHaveCount(7)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/70-week-phone.png`, fullPage: true })
})

test('last week through the arrow; no week after this one', async () => {
  await expect(page.getByRole('button', { name: 'Next week' })).toBeDisabled()
  await page.getByRole('button', { name: 'Previous week' }).click()
  await expect(page.getByRole('heading', { name: /^\d{1,2}( \w{3})? – \d{1,2} \w{3}$/ })).toBeVisible()
  await expect(page.locator('.week-hero')).toContainText(/1[,.]?300/)
  await expect(page.getByRole('button', { name: 'Next week' })).toBeEnabled()
  await page.getByRole('button', { name: '‹ Back to today' }).click()
  await expect(page.locator('button.week-summary')).toBeVisible()
})
