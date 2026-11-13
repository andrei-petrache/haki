/**
 * The workout editor in direction A, on a 390 px phone: a workout started
 * from a program day shows the plan, last time row by row, which set is
 * next, and a tick that starts the rest, which -15 s, +15 s and Skip move.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function tab(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

function localDay(offset = 0): string {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function rows(): Locator {
  return page.locator('fieldset.exercise-block').first().locator('.set-row')
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(page)
  const bench = (await api(page, 'POST', '/exercises', { name: 'E2E Bench' })).body as { id: number }
  // Last week: two sets of 5 x 70
  expect(
    (await api(page, 'POST', '/workouts', {
      performed_on: localDay(-7),
      note: null,
      exercises: [{ exercise_id: bench.id, sets: [{ reps: 5, weight_kg: 70 }, { reps: 5, weight_kg: 70 }] }],
    })).status,
  ).toBe(201)
  const program = (await api(page, 'POST', '/programs', {
    name: 'E2E Push',
    days: [{ position: 1, name: 'Push', exercises: [{ exercise_id: bench.id, sets: 4, reps: 6, weight_kg: 72.5 }] }],
  })).body as { id: number; days: { id: number }[] }
  const started = await api(page, 'POST', `/programs/${program.id}/days/${program.days[0].id}/workouts`, {
    performed_on: localDay(),
  })
  expect(started.status).toBe(201)
  await page.evaluate(() => localStorage.removeItem('haki_rest_last'))
  await page.reload()
})

test.afterAll(async () => {
  await page.close()
})

test('a workout started from a program: the plan, last time per row, and which set is next', async () => {
  await tab('Workouts').click()
  await page.locator('.workout-card').first().click()
  await page.getByRole('button', { name: 'Edit' }).click()

  await expect(page.getByRole('heading', { name: 'Push' })).toBeVisible()
  await expect(rows()).toHaveCount(4)
  await expect(rows().nth(0).locator('.set-last')).toContainText('5 × 70 kg')
  await expect(rows().nth(1).locator('.set-last')).toContainText('5 × 70 kg')
  await expect(rows().nth(2).locator('.set-last')).toContainText('—')
  // Nothing done yet: the first set is next, the others still the plan
  await expect(rows().nth(0)).toContainText('next')
  await expect(rows().nth(1)).toContainText('from the program')
  await expect(rows().nth(3)).toContainText('from the program')
  // 6 x 72.5 would beat last week's 5 x 70, but the plan alone is no record
  await expect(page.locator('.record')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/38-workout-plan-phone.png`, fullPage: true })
})

test('a tick marks a set done and starts the rest; -15 s, +15 s and Skip move it', async () => {
  const tick = page.getByRole('button', { name: 'Set 1 of exercise 1 done' })
  await tick.click()
  await expect(tick).toHaveAttribute('aria-pressed', 'true')
  await expect(rows().nth(1)).toContainText('next')
  // Done as planned: now it is a record
  await expect(page.locator('fieldset.exercise-block').first().locator('.record')).toHaveCount(1)

  const bar = page.getByRole('region', { name: 'Rest timer' })
  const timer = bar.getByRole('timer')
  await expect(timer).toHaveText(/^Rest 1:(2\d|30)$/)
  await bar.getByRole('button', { name: 'Rest 15 s longer' }).click()
  await expect(timer).toHaveText(/^Rest 1:(3\d|4[0-5])$/)
  await bar.getByRole('button', { name: 'Rest 15 s shorter' }).click()
  await bar.getByRole('button', { name: 'Rest 15 s shorter' }).click()
  await expect(timer).toHaveText(/^Rest 1:(0\d|1[0-5])$/)
  await page.screenshot({ path: `${SHOTS}/39-rest-phone.png` })
  await bar.getByRole('button', { name: 'Skip' }).click()
  await expect(bar).toHaveCount(0)

  // Untick: not done any more, next again
  await tick.click()
  await expect(tick).toHaveAttribute('aria-pressed', 'false')
  await expect(rows().nth(0)).toContainText('next')
  await expect(page.locator('.record')).toHaveCount(0)
})

test('a set changed from the plan stops being marked as the plan, and saves as typed', async () => {
  const second = rows().nth(1)
  await second.getByLabel('Reps').fill('7')
  await expect(second).not.toContainText('from the program')

  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.locator('.workout-exercise .sets li').nth(1)).toHaveText(/^7 × 72[.,]5 kg/)
})

test('the day is words under the title, not a native field, and the picker moves it', async () => {
  await page.getByRole('button', { name: 'Edit' }).click()
  const label = page.locator('.editor-head button.day-label')
  await expect(label).toHaveText(/^Today, \d{1,2} [A-Z][a-z]{2}$/)
  // The native input stays invisible under the label
  const field = page.getByLabel('Date', { exact: true })
  expect(await field.evaluate((input) => getComputedStyle(input).opacity)).toBe('0')
  await field.fill(localDay(-1))
  await expect(label).toHaveText(/^Yesterday, /)
  await page.getByRole('button', { name: 'Save' }).click()
  // In the list: weekday, day and month, no year within this one
  await tab('Workouts').click()
  await page.getByRole('button', { name: /Back to workouts/ }).click()
  await expect(page.locator('.workout-card').first()).toContainText(
    new RegExp(`^[A-Z][a-z]{2} ${Number(localDay(-1).slice(8))} [A-Z][a-z]{2}`),
  )
})
