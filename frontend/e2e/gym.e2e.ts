/**
 * The gym helpers on the logging screen, on a phone (390 px): the rest
 * timer between sets. The clock is Playwright's, so minutes pass in an
 * instant and the times are exact.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, deleteEverything, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function tab(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

const restBar = () => page.getByRole('region', { name: 'Rest timer' })

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await page.clock.install()
  await signUp(page)
})

test.afterAll(async () => {
  await deleteEverything(page)
  await page.close()
})

test('the logging screen fits a phone with the rest buttons', async () => {
  await tab('Workouts').click()
  await page.getByRole('button', { name: 'New workout' }).click()

  await expect(page.getByRole('button', { name: 'Start a 1:30 rest' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('a rest counts down from its end time, on every screen', async () => {
  await page.getByRole('button', { name: 'Start a 1:30 rest' }).click()
  await expect(restBar()).toContainText('Rest 1:30')

  await page.clock.fastForward('00:30')
  await expect(restBar()).toContainText('Rest 1:00')
  await page.screenshot({ path: `${SHOTS}/13-rest-phone.png`, fullPage: true })

  // Another screen: the same rest, the same time left
  await tab('Programs').click()
  await expect(restBar()).toContainText('Rest 1:00')
  await page.clock.fastForward('00:15')
  await expect(restBar()).toContainText('Rest 0:45')
})

test('it survives a reload, and says when it is over', async () => {
  await page.reload()
  await expect(restBar()).toContainText(/Rest 0:4[45]/)

  await page.clock.fastForward('01:00')

  await expect(restBar()).toContainText('Rest over')
  await page.getByRole('button', { name: 'OK' }).click()
  await expect(restBar()).toHaveCount(0)
})

test('Stop ends a rest early', async () => {
  await tab('Workouts').click()
  await page.getByRole('button', { name: 'New workout' }).click()
  await page.getByRole('button', { name: 'Start a 1:00 rest' }).click()
  await expect(restBar()).toContainText('Rest 1:00')

  await restBar().getByRole('button', { name: 'Stop' }).click()

  await expect(restBar()).toHaveCount(0)
})

test('the editor shows last time for an exercise, from the history', async () => {
  const { body: bench } = await api(page, 'POST', '/exercises', { name: 'E2E Bench' })
  const exerciseId = (bench as { id: number }).id
  const sets = (pairs: [number, number][]) => pairs.map(([reps, weight_kg]) => ({ reps, weight_kg }))
  for (const [day, pairs] of [
    ['2026-11-05', [[8, 60], [8, 60]]],
    ['2026-11-08', [[5, 70]]],
  ] as const) {
    const { status } = await api(page, 'POST', '/workouts', {
      performed_on: day,
      exercises: [{ exercise_id: exerciseId, sets: sets(pairs as unknown as [number, number][]) }],
    })
    expect(status).toBe(201)
  }

  // Through another tab: the previous test left the editor open
  await tab('Today').click()
  await tab('Workouts').click()
  await page.getByRole('button', { name: 'New workout' }).click()
  await page.locator('fieldset.exercise-block select').first().selectOption({ label: 'E2E Bench' })

  // A new workout: the latest one with the exercise
  await expect(page.getByText(/^Last time \(.*8.*\): 5 × 70 kg$/)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/14-last-time-phone.png`, fullPage: true })
  await page.getByRole('button', { name: 'Cancel' }).click()

  // Editing that latest one: last time is the one before it
  await page.locator('.workout-card').first().click()
  await page.getByRole('button', { name: 'Edit' }).click()
  await expect(page.getByText(/^Last time \(.*5.*\): 8 × 60 kg, 8 × 60 kg$/)).toBeVisible()
})
